"""The minimal ffmpeg build must cover every format the apps offer.

BtbN's general-purpose build carried every codec ffmpeg has, so the apps could
never outgrow it. A build configured with --disable-everything can, silently:
add 'alac' to the audio format list and the app offers a conversion that the
bundled binary cannot perform, with the failure only appearing at runtime on a
user's machine.

These tests read the format lists out of the apps and the encoder list out of
the build script, and fail when they disagree.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "packaging" / "ffmpeg" / "build-ffmpeg.sh"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _configured(kind):
    """Values passed to --enable-<kind>=a,b,c in the build script."""
    m = re.search(rf"--enable-{kind}=([\w,]+)", BUILD.read_text(encoding="utf-8"))
    assert m, f"build script has no --enable-{kind}"
    return set(m.group(1).split(","))


def _audio_formats():
    """The codecs the apps let a user pick, from all three front-ends."""
    audio = re.search(r"self\.fmt_combo\.addItems\(\[([^\]]+)\]\)", _read("ytd_audio.py"))
    assert audio, "could not find the audio format list in ytd_audio.py"
    gui = set(re.findall(r"'(\w+)'", audio.group(1)))

    tui = re.search(r"_FORMAT_OPTS = \[\(f, f\) for f in \(([^)]+)\)\]", _read("ytd_tui.py"))
    assert tui, "could not find the audio format list in ytd_tui.py"
    return gui | set(re.findall(r'"(\w+)"', tui.group(1)))


def test_the_two_front_ends_offer_the_same_audio_formats():
    audio = re.search(r"self\.fmt_combo\.addItems\(\[([^\]]+)\]\)", _read("ytd_audio.py"))
    gui = set(re.findall(r"'(\w+)'", audio.group(1)))
    tui = re.search(r"_FORMAT_OPTS = \[\(f, f\) for f in \(([^)]+)\)\]", _read("ytd_tui.py"))
    assert gui == set(re.findall(r'"(\w+)"', tui.group(1)))


@pytest.mark.parametrize("fmt", sorted(_audio_formats()))
def test_every_offered_audio_format_has_its_encoder_built(fmt):
    """yt-dlp's own ACODECS table says which encoder each format needs."""
    from yt_dlp.postprocessor.ffmpeg import ACODECS

    assert fmt in ACODECS, f"yt-dlp cannot produce {fmt!r} at all"
    _ext, encoder, extra = ACODECS[fmt]
    if encoder is None:
        # Some formats name their encoder in the extra args instead (alac), and
        # one leaves it to ffmpeg's default for the container (wav -> pcm_s16le).
        # Returning early here let 'alac' through a mutation test.
        encoder = dict(zip(extra[::2], extra[1::2])).get("-acodec", "pcm_s16le")
    assert encoder in _configured("encoder"), (
        f"the apps offer {fmt!r}, which needs the {encoder!r} encoder, but the "
        f"ffmpeg build script does not enable it")


@pytest.mark.parametrize("fmt", sorted(_audio_formats()))
def test_every_offered_audio_format_has_its_muxer_built(fmt):
    from yt_dlp.postprocessor.ffmpeg import ACODECS

    # ffmpeg picks the muxer from the extension, except where yt-dlp forces one
    ext_muxer = {"mp3": "mp3", "m4a": "ipod", "opus": "opus", "flac": "flac",
                 "ogg": "ogg", "wav": "wav"}
    ext, _encoder, extra = ACODECS[fmt]
    forced = dict(zip(extra[::2], extra[1::2])).get("-f")
    muxer = forced or ext_muxer[ext]
    assert muxer in _configured("muxer"), (
        f"the apps offer {fmt!r}, which is written by the {muxer!r} muxer, but "
        f"the ffmpeg build script does not enable it")


def test_merging_video_needs_the_mp4_muxer():
    """The video app merges the separate streams YouTube serves into one mp4."""
    assert "merge_output_format" in _read("ytd.py")
    assert "mp4" in _configured("muxer")
    assert "mov" in _configured("demuxer"), "reading the mp4 it just downloaded"
    assert "matroska" in _configured("demuxer"), "YouTube also serves webm"


def test_m4a_bitstream_filter_is_built():
    """yt-dlp passes -bsf:a aac_adtstoasc for m4a; without it the file is unplayable."""
    assert "aac_adtstoasc" in _configured("bsf")


def test_the_build_script_is_executable_and_pinned():
    import os
    import stat

    assert BUILD.exists(), "the ffmpeg build script is missing"
    assert os.stat(BUILD).st_mode & stat.S_IXUSR, "build script is not executable"
    src = BUILD.read_text(encoding="utf-8")
    for var in ("FFMPEG_VERSION", "LAME_VERSION", "OPUS_VERSION"):
        assert re.search(rf'{var}:-[\d.]+', src), f"{var} is not pinned"
    # every source is fetched by checksum, not by trusting the URL
    calls = re.findall(r'^\s*fetch "([^"]+)" \\\n\s*"([0-9a-f]{64})"', src, re.M)
    assert len(calls) == 3, f"expected 3 checksummed downloads, found {len(calls)}"
    for url, _sum in calls:
        assert url.startswith("https://"), f"{url} is not https"


# ── the apps must be able to find an ffmpeg at all ───────────────────────────

@pytest.mark.parametrize("spec", ["youtube-downloader.spec",
                                  "youtube-audio-downloader.spec",
                                  "youtube-tui.spec"])
def test_every_spec_bundles_ffmpeg(spec):
    """This became load-bearing when the .deb stopped depending on the system one.

    The bundle is now the only ffmpeg these apps have: get_ffmpeg_location()
    points yt-dlp at _MEIPASS, and nothing falls back to PATH when frozen.
    """
    src = _read(spec)
    assert "ffmpeg_binaries" in src, f"{spec} does not stage ffmpeg"
    assert 'binaries=ffmpeg_binaries' in src.replace(" ", "") or \
           "ffmpeg_binaries +" in src, f"{spec} never passes ffmpeg to Analysis"


def test_the_deb_does_not_ask_for_an_ffmpeg_it_already_ships():
    """It declared Depends: ffmpeg and bundled a private copy — installing both.

    Now that the bundled build is 3.8 MB rather than 140 MB, the private copy is
    the cheap one and the system dependency was costing users a ~100 MB install
    they never used.
    """
    deb = _read("packaging/linux/make-deb.sh")
    assert "Depends: ffmpeg" not in deb
    assert "ffmpeg_binaries" in _read("youtube-downloader.spec")


def test_the_workflow_verifies_the_build_before_shipping_it():
    """A --disable-everything build that is missing a codec fails at the user's
    machine, not at build time, unless something checks."""
    wf = _read(".github/workflows/build-release.yml")
    assert "check_ffmpeg.py" in wf, "CI never verifies the ffmpeg it just built"
    assert "build-ffmpeg.sh" in wf, "CI no longer builds the minimal ffmpeg"
    assert "FFmpeg-Builds/releases/download" not in wf, (
        "CI went back to downloading a prebuilt general-purpose ffmpeg")
    assert "brew install ffmpeg" not in wf, (
        "the macOS job went back to Homebrew's general-purpose ffmpeg")
    # the check reads yt-dlp's codec table, so it must run after the install
    assert wf.index("pip install -r requirements-build.txt") < wf.index("check_ffmpeg.py")
