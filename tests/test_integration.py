"""End-to-end downloads: real yt-dlp, real ffmpeg, real HTTP.

Nothing here is mocked. A tiny mp4 is served over localhost and pulled through
the same DownloadWorker the app uses, so format selection, the archive, the
post-processors and the progress hooks are exercised together rather than
asserted on in isolation.
"""
import os
import subprocess

import pytest

import ytd
import ytd_audio

pytestmark = pytest.mark.integration


def _probe(path, entries="stream=codec_type"):
    out = subprocess.run(
        ["ffprobe", "-hide_banner", "-loglevel", "error",
         "-show_entries", entries, "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True)
    return out.stdout.split()


def _run(worker):
    """Run a worker to completion, collecting its signals."""
    events = {"progress": [], "error": [], "finished": [], "postprocess": []}
    worker.progress.connect(lambda d: events["progress"].append(d))
    worker.error.connect(lambda m: events["error"].append(m))
    worker.finished.connect(lambda: events["finished"].append(True))
    worker.postprocess.connect(lambda m: events["postprocess"].append(m))
    worker.run()
    return events


# ── video ─────────────────────────────────────────────────────────────────────

def test_video_download_produces_a_playable_file(media_server, tmp_path):
    w = ytd.DownloadWorker(f"{media_server}/clip.mp4", str(tmp_path), "Best")
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert events["finished"] == [True]
    files = [p for p in tmp_path.iterdir() if p.suffix == ".mp4"]
    assert files, list(tmp_path.iterdir())
    assert "video" in _probe(files[0])


def test_video_download_reports_progress(media_server, tmp_path):
    w = ytd.DownloadWorker(f"{media_server}/clip.mp4", str(tmp_path), "Best")
    events = _run(w)
    assert events["error"] == []
    # the file is small, but any progress emitted must be well-formed
    for d in events["progress"]:
        assert 0 <= d["percent"] <= 100
        assert d["speed"] >= 0


def test_download_archive_prevents_a_second_fetch(media_server, tmp_path):
    """Resumability feature: the archive must make a repeat run a no-op."""
    url = f"{media_server}/clip.mp4"
    _run(ytd.DownloadWorker(url, str(tmp_path), "Best"))
    archive = tmp_path / ".ytdl-archive"
    assert archive.exists(), "archive file should be written"
    first = {p.name: p.stat().st_mtime_ns for p in tmp_path.glob("*.mp4")}

    _run(ytd.DownloadWorker(url, str(tmp_path), "Best"))
    second = {p.name: p.stat().st_mtime_ns for p in tmp_path.glob("*.mp4")}
    assert first == second, "archived item was downloaded again"


def test_cancellation_stops_the_download(media_server, tmp_path):
    w = ytd.DownloadWorker(f"{media_server}/clip.mp4", str(tmp_path), "Best")
    w.cancel()
    events = _run(w)
    assert events["error"] == ["cancelled"]
    assert events["finished"] == []


def test_bad_url_surfaces_an_error_and_does_not_crash(media_server, tmp_path):
    w = ytd.DownloadWorker(f"{media_server}/does-not-exist.mp4", str(tmp_path), "Best")
    events = _run(w)
    assert events["finished"] == [], "a 404 must not be reported as success"
    assert events["error"], "the failure must reach the user"
    assert not list(tmp_path.glob("*.mp4"))


def test_unreachable_host_surfaces_an_error(tmp_path):
    w = ytd.DownloadWorker("http://127.0.0.1:1/nothing.mp4", str(tmp_path), "Best")
    events = _run(w)
    assert events["finished"] == []
    assert events["error"]
    assert not list(tmp_path.glob("*.mp4"))


# ── audio ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("codec,expected", [("mp3", "mp3"), ("opus", "opus")])
def test_audio_extraction_really_transcodes(media_server, tmp_path, codec, expected):
    w = ytd_audio.DownloadWorker(
        f"{media_server}/clip.mp4", str(tmp_path), codec, "128")
    events = _run(w)
    assert events["error"] == [], events["error"]
    out = [p for p in tmp_path.iterdir() if p.suffix == f".{codec}"]
    assert out, list(tmp_path.iterdir())
    codecs = _probe(out[0], "stream=codec_name")
    assert expected in codecs
    assert "video" not in _probe(out[0]), "audio-only output must have no video stream"


def test_audio_postprocessor_hook_fires(media_server, tmp_path):
    w = ytd_audio.DownloadWorker(f"{media_server}/clip.mp4", str(tmp_path), "mp3", "128")
    events = _run(w)
    assert events["error"] == []
    assert any("Converting" in m for m in events["postprocess"] if m)


# ── options that must survive a real run ─────────────────────────────────────

def test_quality_cap_still_downloads_when_source_is_smaller(media_server, tmp_path):
    """A 128x96 clip requested at 480p must still succeed, not select nothing."""
    w = ytd.DownloadWorker(f"{media_server}/clip.mp4", str(tmp_path), "480p")
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert list(tmp_path.glob("*.mp4"))


def test_save_path_with_spaces_and_unicode(media_server, tmp_path):
    target = tmp_path / "My Videos ünïcode 日本語"
    target.mkdir()
    w = ytd.DownloadWorker(f"{media_server}/clip.mp4", str(target), "Best")
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert list(target.glob("*.mp4"))


# ── TUI download path ────────────────────────────────────────────────────────
# test_tui.py stubs _run_download, and the tests above drive the Qt workers, so
# the TUI's own download path had no coverage at all.

async def test_tui_really_downloads(media_server, tmp_path):
    import asyncio

    import dep_check
    import ytd_tui
    from textual.widgets import Input

    real_check = dep_check.check_deps
    dep_check.check_deps = lambda **kw: []
    errors = []
    real_err = ytd_tui.YTDApp._ui_error
    ytd_tui.YTDApp._ui_error = lambda self, msg: errors.append(msg)
    try:
        app = ytd_tui.YTDApp()
        async with app.run_test(size=(110, 34)) as pilot:
            app.query_one("#url-input", Input).value = f"{media_server}/clip.mp4"
            app.query_one("#save-input", Input).value = str(tmp_path)
            await pilot.press("ctrl+d")
            for _ in range(60):
                await pilot.pause()
                await asyncio.sleep(0.25)
                if any(p.suffix == ".mp4" for p in tmp_path.iterdir()):
                    break
    finally:
        dep_check.check_deps = real_check
        ytd_tui.YTDApp._ui_error = real_err

    assert not errors, errors
    assert [p.name for p in tmp_path.glob("*.mp4")] == ["clip.mp4"]
    assert (tmp_path / ".ytdl-archive").exists(), "resumability archive missing"


# ── reusing the metadata already fetched for the preview ─────────────────────
# Pressing Download used to trigger a second full extraction: measured at 2.0 s
# on YouTube before a single byte moved. These run against the local server, so
# they assert the wiring and the fallback, not the saving.

def _meta(url):
    """Extract exactly as the preview path does."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True,
            "extract_flat": "in_playlist", "noprogress": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def test_reused_info_downloads_the_same_file(media_server, tmp_path):
    url = f"{media_server}/clip.mp4"
    info = _meta(url)
    w = ytd.DownloadWorker(url, str(tmp_path), "Best", info=info)
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert events["finished"] == [True]
    assert [p.name for p in tmp_path.glob("*.mp4")] == ["clip.mp4"]


def test_reused_info_is_byte_identical_to_extracting_again(media_server, tmp_path):
    url = f"{media_server}/clip.mp4"
    plain, reused = tmp_path / "plain", tmp_path / "reused"
    plain.mkdir(); reused.mkdir()
    assert _run(ytd.DownloadWorker(url, str(plain), "Best"))["error"] == []
    assert _run(ytd.DownloadWorker(url, str(reused), "Best", info=_meta(url)))["error"] == []
    a = (plain / "clip.mp4").read_bytes()
    b = (reused / "clip.mp4").read_bytes()
    assert a == b and len(a) > 0


def test_stale_info_falls_back_to_a_fresh_extraction(media_server, tmp_path):
    """The safety property the whole feature rests on.

    Format URLs expire. If reusing info ever fails, yt-dlp must re-extract from
    webpage_url rather than report a download that produced no file.
    """
    url = f"{media_server}/clip.mp4"
    info = _meta(url)
    dead = "http://127.0.0.1:1/gone.mp4"
    info["url"] = dead
    for f in info.get("formats") or []:
        f["url"] = dead
    assert info.get("webpage_url"), "fallback needs webpage_url in the info"

    w = ytd.DownloadWorker(url, str(tmp_path), "Best", info=info)
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert [p.name for p in tmp_path.glob("*.mp4")] == ["clip.mp4"], (
        "stale info must fall back, not silently produce nothing")


def test_cancellation_still_works_with_reused_info(media_server, tmp_path):
    url = f"{media_server}/clip.mp4"
    w = ytd.DownloadWorker(url, str(tmp_path), "Best", info=_meta(url))
    w.cancel()
    events = _run(w)
    assert events["error"] == ["cancelled"]
    assert events["finished"] == []


def test_audio_worker_also_reuses_info(media_server, tmp_path):
    url = f"{media_server}/clip.mp4"
    w = ytd_audio.DownloadWorker(url, str(tmp_path), "mp3", "128", info=_meta(url))
    events = _run(w)
    assert events["error"] == [], events["error"]
    assert [p.suffix for p in tmp_path.iterdir() if p.suffix == ".mp3"] == [".mp3"]


def test_no_info_leaves_a_temp_file_behind(media_server, tmp_path):
    """The info json is written to the system temp dir; it must not accumulate."""
    import glob, os, tempfile
    url = f"{media_server}/clip.mp4"
    before = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.info.json")))
    _run(ytd.DownloadWorker(url, str(tmp_path), "Best", info=_meta(url)))
    after = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.info.json")))
    assert after == before, f"leaked {after - before}"
