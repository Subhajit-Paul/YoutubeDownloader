"""End-to-end through the real Qt windows.

The window is built offscreen, given a URL served from localhost, and driven
through the same signal/thread machinery the app uses at runtime — metadata
fetch, UI state transitions, download, completion.
"""
import time

import pytest

pytestmark = pytest.mark.integration

from PyQt5.QtWidgets import QApplication

import ytd
import ytd_audio


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _spin(app, predicate, timeout=60.0):
    """Run the Qt event loop until predicate() is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def window(qapp, request):
    cls = request.param
    w = cls()
    yield w
    # NB: QMainWindow already defines .thread(); only stop real QThread objects.
    from PyQt5.QtCore import QThread
    for attr in ("_meta_thread", "thread", "_thumb_thread"):
        t = getattr(w, attr, None)
        if isinstance(t, QThread):
            try:
                t.quit()
                t.wait(3000)
            except RuntimeError:
                pass  # already reaped by deleteLater
    w.close()


WINDOWS = [ytd.YoutubeDownloaderApp, ytd_audio.YoutubeAudioDownloaderApp]
IDS = ["video", "audio"]


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_metadata_fetch_populates_the_card(qapp, window, media_server):
    window.url_input.setText(f"{media_server}/clip.mp4")
    window._fetch_metadata()
    assert _spin(qapp, lambda: bool(window._meta)), "metadata never arrived"
    assert window._meta["title"]
    assert window.card.isVisible() or window._meta is not None


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_bad_url_shows_an_error_and_hides_the_card(qapp, window, media_server):
    failures = []
    window.url_input.setText(f"{media_server}/missing.mp4")
    orig = window._on_meta_failed
    window._on_meta_failed = lambda m: (failures.append(m), orig(m))
    window._fetch_metadata()
    assert _spin(qapp, lambda: failures), "failure was never reported to the UI"
    assert not window.card.isVisible()


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_full_download_flow_writes_a_file(qapp, window, media_server, tmp_path):
    window.url_input.setText(f"{media_server}/clip.mp4")
    window._fetch_metadata()
    assert _spin(qapp, lambda: bool(window._meta)), "metadata never arrived"

    window.save_input.setText(str(tmp_path))
    done, errors = [], []
    window._start_download()
    window.worker.finished.connect(lambda: done.append(True))
    window.worker.error.connect(errors.append)

    assert _spin(qapp, lambda: done or errors), "download never finished"
    assert not errors, errors
    assert any(p.is_file() for p in tmp_path.iterdir()), list(tmp_path.iterdir())


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_download_without_metadata_is_a_no_op(qapp, window, tmp_path):
    """The download button must not act on a URL that was never resolved."""
    window.url_input.setText("https://example.invalid/x")
    window.save_input.setText(str(tmp_path))
    window._meta = {}
    window._start_download()
    assert not list(tmp_path.iterdir())
