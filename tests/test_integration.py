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
