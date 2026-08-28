"""Live YouTube matrix — every quality and audio format the apps offer.

Excluded from the default run: YouTube rate-limits and bot-checks CI ranges, so
gating every push on it would make the suite flaky. Run deliberately:

    pytest -m network
    pytest -m network --url "https://www.youtube.com/watch?v=..."

Downloads are capped to a few seconds per combination via download_ranges, which
still exercises format selection, stream merging and audio transcoding in full.
"""
import os
import subprocess

import pytest

import ytd
import ytd_audio
import ytd_core


# The GUI download workers live in ytd_core now, so that is where they
# resolve yt_dlp; the TUI still owns its own.
def _ydl(mod):
    return getattr(mod, "yt_dlp", None) or ytd_core.yt_dlp

pytestmark = [pytest.mark.network, pytest.mark.integration]

SECONDS = 6


@pytest.fixture(scope="module")
def url(pytestconfig):
    return pytestconfig.getoption("--url")


@pytest.fixture
def capped(monkeypatch):
    """Run a worker with its download limited to the first few seconds."""
    from yt_dlp.utils import download_range_func

    def _apply(mod):
        real = _ydl(mod).YoutubeDL

        class Capped(real):
            def __init__(self, opts, *a, **k):
                opts = {**opts, "quiet": True, "no_warnings": True,
                        "download_ranges": download_range_func(None, [(0, SECONDS)])}
                super().__init__(opts, *a, **k)

        monkeypatch.setattr(_ydl(mod), "YoutubeDL", Capped)
    return _apply


def _run(worker):
    errors, done = [], []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda: done.append(True))
    worker.run()
    return errors, done


def _streams(path):
    out = subprocess.run(
        ["ffprobe", "-hide_banner", "-loglevel", "error", "-show_entries",
         "stream=codec_type,codec_name,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return out.stdout.split()


def _only_file(d):
    files = [os.path.join(d, f) for f in os.listdir(d) if not f.startswith(".ytdl")]
    assert files, f"no file produced in {d}"
    return max(files, key=os.path.getsize)


@pytest.mark.parametrize("quality,max_height", [
    ("Best", None), ("1080p", 1080), ("720p", 720), ("480p", 480),
])
def test_video_quality(url, tmp_path, capped, quality, max_height):
    capped(ytd)
    errors, done = _run(ytd.DownloadWorker(url, str(tmp_path), quality))
    assert not errors, errors
    assert done
    streams = _streams(_only_file(str(tmp_path)))
    assert any("video" in s for s in streams), streams
    assert any("audio" in s for s in streams), "video must be merged with audio"
    if max_height:
        heights = [int(x) for s in streams for x in s.split(",") if x.isdigit()]
        assert heights and max(heights) <= max_height, (
            f"{quality} produced height {heights}, above the cap")


@pytest.mark.parametrize("fmt,expected", [
    ("mp3", "mp3"), ("aac", "aac"), ("m4a", "aac"),
    ("opus", "opus"), ("flac", "flac"), ("wav", "pcm_s16le"),
])
@pytest.mark.parametrize("bitrate", ["320", "128"])
def test_audio_format(url, tmp_path, capped, fmt, expected, bitrate):
    capped(ytd_audio)
    errors, done = _run(
        ytd_audio.DownloadWorker(url, str(tmp_path), fmt, bitrate))
    assert not errors, errors
    assert done
    streams = _streams(_only_file(str(tmp_path)))
    assert any(expected in s for s in streams), f"expected {expected}, got {streams}"
    assert not any("video" in s for s in streams), "audio output must have no video"


def test_metadata_fetch(url):
    """The apps show title/duration before downloading; a stale yt-dlp breaks this."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    assert info.get("title")
    assert info.get("duration")
