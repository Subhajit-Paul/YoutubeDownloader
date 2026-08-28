#!/usr/bin/env python3
"""Verify a built ffmpeg can do everything these apps ask of it.

The bundled ffmpeg is built with --disable-everything and a named list of
codecs (packaging/ffmpeg/build-ffmpeg.sh). tests/test_ffmpeg_build.py checks
that list against the formats the apps offer, but that is only the recipe. This
runs the binary: it asks what it can do, and then makes it do it.

    python tools/check_ffmpeg.py ./ffmpeg
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# The formats the audio app offers, and what yt-dlp invokes for each.
from yt_dlp.postprocessor.ffmpeg import ACODECS  # noqa: E402

FORMATS = ["mp3", "aac", "m4a", "opus", "flac", "wav"]
EXT_MUXER = {"mp3": "mp3", "m4a": "ipod", "opus": "opus", "flac": "flac",
             "ogg": "ogg", "wav": "wav"}


def run(*args):
    return subprocess.run(args, capture_output=True, text=True)


def capabilities(ffmpeg, what):
    """Names ffmpeg reports for -encoders/-muxers/-demuxers.

    Some are comma-joined aliases for one entry — the mp4 demuxer is listed as
    'mov,mp4,m4a,3gp,3g2,mj2' — so each alias is recorded separately.
    """
    out = run(ffmpeg, "-hide_banner", f"-{what}").stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].strip(".DEVASIL") == "":
            names.update(parts[1].split(","))
    return names


def main():
    ffmpeg = sys.argv[1] if len(sys.argv) > 1 else "ffmpeg"
    # On Windows the binary is ffmpeg.exe. shutil.which("./ffmpeg") finds it
    # through PATHEXT and returns truthy, so a bare existence check passes and
    # the literal "./ffmpeg" then fails to execute — which is exactly how the
    # first v1.5.0 Windows job died, after building the binary correctly.
    # Take the resolved path, not the argument.
    if pathlib.Path(ffmpeg).exists():
        ffmpeg = str(pathlib.Path(ffmpeg).resolve())
    else:
        found = shutil.which(ffmpeg)
        if not found:
            sys.exit(f"no such ffmpeg: {ffmpeg}")
        ffmpeg = found

    ver = run(ffmpeg, "-version").stdout.splitlines()[0]
    size = pathlib.Path(ffmpeg).stat().st_size / 1048576
    print(f"{ver}\n  {ffmpeg}  {size:.1f} MiB\n")

    encoders = capabilities(ffmpeg, "encoders")
    muxers = capabilities(ffmpeg, "muxers")
    bsfs = set(run(ffmpeg, "-hide_banner", "-bsfs").stdout.split())

    failures = []
    for fmt in FORMATS:
        ext, encoder, extra = ACODECS[fmt]
        pairs = dict(zip(extra[::2], extra[1::2]))
        if encoder is None:
            encoder = pairs.get("-acodec", "pcm_s16le")
        muxer = pairs.get("-f") or EXT_MUXER[ext]
        ok_e, ok_m = encoder in encoders, muxer in muxers
        bsf = pairs.get("-bsf:a")
        ok_b = bsf is None or bsf in bsfs
        status = "ok" if (ok_e and ok_m and ok_b) else "MISSING"
        print(f"  {fmt:5s} encoder={encoder:12s} {'ok' if ok_e else 'MISSING':8s}"
              f" muxer={muxer:8s} {'ok' if ok_m else 'MISSING':8s}"
              + (f" bsf={bsf} {'ok' if ok_b else 'MISSING'}" if bsf else ""))
        if status == "MISSING":
            failures.append(fmt)

    for name, present, why in (("mp4", "mp4" in muxers, "merging video+audio"),
                               ("mov", "mov" in capabilities(ffmpeg, "demuxers"),
                                "reading the downloaded mp4"),
                               ("matroska", "matroska" in capabilities(ffmpeg, "demuxers"),
                                "reading webm from YouTube")):
        print(f"  {name:5s} {'ok' if present else 'MISSING':8s} ({why})")
        if not present:
            failures.append(name)

    # ── and now actually do it ────────────────────────────────────────────────
    system = shutil.which("ffmpeg")
    if system and pathlib.Path(system).resolve() != pathlib.Path(ffmpeg).resolve():
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "src.mp4"
            gen = run(system, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                      "-i", "testsrc=duration=1:size=128x96:rate=10", "-f", "lavfi",
                      "-i", "sine=frequency=440:duration=1", "-c:v", "libx264",
                      "-c:a", "aac", "-shortest", "-y", str(src))
            if gen.returncode == 0:
                print("\n  real conversions:")
                for fmt in FORMATS:
                    ext, encoder, extra = ACODECS[fmt]
                    pairs = dict(zip(extra[::2], extra[1::2]))
                    out = pathlib.Path(d) / f"out.{ext}"
                    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(src), "-vn"]
                    if encoder:
                        args += ["-acodec", encoder]
                    args += list(extra) + [str(out)]
                    r = run(*args)
                    good = r.returncode == 0 and out.exists() and out.stat().st_size > 0
                    print(f"    {fmt:5s} {'ok' if good else 'FAILED'}"
                          f"  {out.stat().st_size if out.exists() else 0} bytes")
                    if not good:
                        failures.append(f"{fmt} (conversion)")
                        print("      " + r.stderr.strip().splitlines()[-1][:160]
                              if r.stderr.strip() else "")
            else:
                print("\n  (no system ffmpeg fixture; capability check only)")
    else:
        print("\n  (no separate system ffmpeg; capability check only)")

    if failures:
        sys.exit(f"\nffmpeg build cannot serve: {', '.join(failures)}")
    print("\nall good")


if __name__ == "__main__":
    main()
