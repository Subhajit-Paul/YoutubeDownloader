"""Core download behaviour: format selection, yt-dlp options, progress parsing.

run() is exercised with yt_dlp.YoutubeDL swapped for a recorder, so the options
dict the app actually hands to yt-dlp is asserted without any network access.
"""
import pytest

import ytd
import ytd_audio
import ytd_tui


# ── duration formatting (duplicated in both GUI apps) ────────────────────────

@pytest.mark.parametrize("mod", [ytd, ytd_audio], ids=["video", "audio"])
@pytest.mark.parametrize("secs,expected", [
    (0, ""), (None, ""),
    (5, "0:05"), (59, "0:59"), (60, "1:00"), (61, "1:01"),
    (599, "9:59"), (600, "10:00"),
    (3600, "1:00:00"), (3661, "1:01:01"), (86399, "23:59:59"),
])
def test_fmt_dur(mod, secs, expected):
    assert mod._fmt_dur(secs) == expected


def test_fmt_dur_is_identical_across_apps():
    """Both GUI apps carry their own copy — they must not drift apart."""
    for s in (0, 7, 61, 3600, 3661, 86399):
        assert ytd._fmt_dur(s) == ytd_audio._fmt_dur(s)


# ── quality map (duplicated in the video app and the TUI) ────────────────────

def _video_quality_map():
    recorder = _Recorder()
    _run_video(recorder, quality="Best")
    return recorder.opts["format"]


def test_quality_map_identical_between_gui_and_tui():
    """ytd.py and ytd_tui.py each define the map — drift changes what users get."""
    gui_map = {}
    for q in ("Best", "1080p", "720p", "480p"):
        r = _Recorder()
        _run_video(r, quality=q)
        gui_map[q] = r.opts["format"]
    assert gui_map == ytd_tui._QUALITY_MAP


@pytest.mark.parametrize("quality,height", [("1080p", "1080"), ("720p", "720"), ("480p", "480")])
def test_quality_caps_height(quality, height):
    r = _Recorder()
    _run_video(r, quality=quality)
    assert f"height<={height}" in r.opts["format"]


def test_unknown_quality_falls_back_to_best():
    r = _Recorder()
    _run_video(r, quality="4320p-ultra")
    assert r.opts["format"] == ytd_tui._QUALITY_MAP["Best"]


# ── yt-dlp option construction ───────────────────────────────────────────────

class _Recorder:
    """Stands in for yt_dlp.YoutubeDL, capturing the options it was built with."""
    def __init__(self):
        self.opts = None
        self.urls = None

    def __call__(self, opts):
        self.opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        self.urls = urls


def _run_video(recorder, monkeypatch=None, **kw):
    import unittest.mock as m
    params = dict(url="https://y/1", save_path="/tmp/dl", quality="Best")
    params.update(kw)
    w = ytd.DownloadWorker(**params)
    with m.patch.object(ytd.yt_dlp, "YoutubeDL", recorder):
        w.run()
    return w


def _run_audio(recorder, **kw):
    import unittest.mock as m
    params = dict(url="https://y/1", save_path="/tmp/dl",
                  audio_format="mp3", audio_quality="192")
    params.update(kw)
    w = ytd_audio.DownloadWorker(**params)
    with m.patch.object(ytd_audio.yt_dlp, "YoutubeDL", recorder):
        w.run()
    return w


def test_video_merges_to_mp4_and_downloads_the_url():
    r = _Recorder()
    _run_video(r)
    assert r.opts["merge_output_format"] == "mp4"
    assert r.urls == ["https://y/1"]


def test_audio_extracts_with_requested_codec_and_bitrate():
    r = _Recorder()
    _run_audio(r, audio_format="opus", audio_quality="320")
    pp = r.opts["postprocessors"][0]
    assert pp["key"] == "FFmpegExtractAudio"
    assert pp["preferredcodec"] == "opus"
    assert pp["preferredquality"] == "320"
    assert r.opts["format"] == "bestaudio/best"


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_resumability_and_archive_are_enabled(runner):
    r = _Recorder()
    runner(r)
    assert r.opts["continuedl"] is True
    assert r.opts["download_archive"].endswith(".ytdl-archive")


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_no_cookies_option_when_browser_is_none(runner):
    r = _Recorder()
    runner(r, browser="None")
    assert "cookiesfrombrowser" not in r.opts


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_browser_cookies_use_lowercase_key_yt_dlp_expects(runner):
    r = _Recorder()
    runner(r, browser="Firefox")
    assert r.opts["cookiesfrombrowser"] == ("firefox",)


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_aria2c_wiring_is_off_by_default(runner):
    r = _Recorder()
    runner(r)
    assert "external_downloader" not in r.opts


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_aria2c_wiring_when_enabled(runner):
    r = _Recorder()
    runner(r, use_aria2c=True)
    assert r.opts["external_downloader"] == "aria2c"
    assert "-x" in r.opts["external_downloader_args"]["aria2c"]


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_performance_options_are_passed_through(runner):
    r = _Recorder()
    runner(r, concurrent_fragments=16, buffersize=4096,
           http_chunk_size=8192, socket_timeout=60)
    assert r.opts["concurrent_fragment_downloads"] == 16
    assert r.opts["buffersize"] == 4096
    assert r.opts["http_chunk_size"] == 8192
    assert r.opts["socket_timeout"] == 60


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_playlists_go_into_a_subfolder(runner):
    r = _Recorder()
    runner(r)
    assert "playlist_title" in r.opts["outtmpl"]


# ── output template ──────────────────────────────────────────────────────────
# The template is fed to yt-dlp, not to Python's % operator. A template that is
# merely wrong raises KeyError at download time, which is how all three apps
# shipped unable to download anything at all.

def _outtmpl(runner):
    r = _Recorder()
    runner(r)
    return r.opts["outtmpl"]


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_outtmpl_is_accepted_by_yt_dlp(runner):
    import yt_dlp
    ydl = yt_dlp.YoutubeDL({"outtmpl": _outtmpl(runner), "quiet": True})
    ydl.prepare_filename({"title": "Song", "ext": "mp4", "id": "x"})


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_single_video_lands_directly_in_the_save_folder(runner):
    import os
    import yt_dlp
    ydl = yt_dlp.YoutubeDL({"outtmpl": _outtmpl(runner), "quiet": True})
    got = os.path.normpath(ydl.prepare_filename({"title": "Song", "ext": "mp4", "id": "x"}))
    assert os.path.basename(got) == "Song.mp4"
    assert os.path.dirname(got) == os.path.normpath("/tmp/dl")


@pytest.mark.parametrize("runner", [_run_video, _run_audio], ids=["video", "audio"])
def test_playlist_item_lands_in_a_real_subfolder(runner):
    import os
    import yt_dlp
    ydl = yt_dlp.YoutubeDL({"outtmpl": _outtmpl(runner), "quiet": True})
    got = os.path.normpath(ydl.prepare_filename(
        {"title": "Song", "ext": "mp4", "id": "x", "playlist_title": "My Mix"}))
    assert os.path.basename(got) == "Song.mp4"
    assert os.path.basename(os.path.dirname(got)) == "My Mix", (
        f"playlist must nest in its own directory, got {got!r}")


def test_tui_uses_the_same_template_as_the_gui():
    """All three apps must agree; the TUI keeps its own copy."""
    import re
    src = (ROOT_TUI := __import__("pathlib").Path(ytd_tui.__file__)).read_text(encoding="utf-8")
    assert '"%(playlist_title&{}|)s/%(title)s.%(ext)s"' in src
