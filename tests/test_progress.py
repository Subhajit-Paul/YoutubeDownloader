"""Progress and post-processing hooks — the path yt-dlp calls on every chunk."""
import pytest
import yt_dlp

import ytd
import ytd_audio


def _worker(mod):
    if mod is ytd:
        return mod.DownloadWorker("u", "/tmp", "Best")
    return mod.DownloadWorker("u", "/tmp", "mp3", "192")


MODS = [ytd, ytd_audio]
IDS = ["video", "audio"]


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_cancel_raises_so_yt_dlp_aborts(mod):
    """Cancellation only works if the hook raises — returning would keep downloading."""
    w = _worker(mod)
    w.cancel()
    with pytest.raises(yt_dlp.utils.DownloadCancelled):
        w.progress_hook({"status": "downloading"})


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_non_downloading_status_emits_nothing(mod):
    w = _worker(mod)
    seen = []
    w.progress.connect(seen.append)
    w.progress_hook({"status": "finished"})
    assert seen == []


@pytest.mark.parametrize("mod", MODS, ids=IDS)
@pytest.mark.parametrize("payload", [
    {"status": "downloading"},                                  # nothing known yet
    {"status": "downloading", "total_bytes": 0, "speed": 5},     # size unknown
    {"status": "downloading", "total_bytes": 100, "speed": None},  # speed unknown
])
def test_incomplete_payloads_emit_nothing(mod, payload):
    w = _worker(mod)
    seen = []
    w.progress.connect(seen.append)
    w.progress_hook(payload)
    assert seen == []


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_percent_and_speed_are_computed(mod):
    w = _worker(mod)
    seen = []
    w.progress.connect(seen.append)
    w.progress_hook({
        "status": "downloading",
        "total_bytes": 1000, "downloaded_bytes": 250,
        "speed": 2 * 1_048_576, "eta": 42, "filename": "v.mp4",
    })
    assert len(seen) == 1
    assert seen[0]["percent"] == 25.0
    assert seen[0]["speed"] == pytest.approx(2.0)
    assert seen[0]["eta"] == 42


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_estimated_size_is_used_when_exact_is_absent(mod):
    w = _worker(mod)
    seen = []
    w.progress.connect(seen.append)
    w.progress_hook({
        "status": "downloading",
        "total_bytes_estimate": 2000, "downloaded_bytes": 1000,
        "speed": 1_048_576,
    })
    assert seen[0]["percent"] == 50.0


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_playlist_count_is_remembered_across_items(mod):
    """yt-dlp only sends playlist_count on some callbacks; it must persist."""
    w = _worker(mod)
    seen = []
    w.progress.connect(seen.append)
    base = {"status": "downloading", "total_bytes": 10,
            "downloaded_bytes": 5, "speed": 1_048_576}
    w.progress_hook({**base, "playlist_count": 7})
    w.progress_hook(base)  # no count this time
    assert seen[0]["playlist_count"] == 7
    assert seen[1]["playlist_count"] == 7


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_postprocessor_reports_conversion_then_counts_completion(mod):
    w = _worker(mod)
    msgs, overall = [], []
    w.postprocess.connect(msgs.append)
    w.overall.connect(lambda d, t: overall.append((d, t)))
    w._total = 3
    w.postprocessor_hook({"status": "started", "info_dict": {"title": "Song"}})
    w.postprocessor_hook({"status": "finished", "info_dict": {"title": "Song"}})
    assert "Song" in msgs[0]
    assert overall == [(1, 3)]


@pytest.mark.parametrize("mod", MODS, ids=IDS)
def test_postprocessor_silent_after_cancel(mod):
    w = _worker(mod)
    w.cancel()
    msgs = []
    w.postprocess.connect(msgs.append)
    w.postprocessor_hook({"status": "started", "info_dict": {"title": "X"}})
    assert msgs == []
