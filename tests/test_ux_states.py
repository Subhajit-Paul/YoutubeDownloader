"""The states a user actually lands in — loading, failure, retry, resize.

Every case here is a defect that shipped: a percentage that stayed green after
the first download, a title cut at a fixed character count, a fetch that showed
nothing while it ran and nothing when it failed, and a TUI error whose reason
lived only in a log panel that is hidden by default.
"""
import pathlib

import pytest

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication

import common
import ytd
import ytd_audio
import ytd_tui


WINDOWS = [ytd.YoutubeDownloaderApp, ytd_audio.YoutubeAudioDownloaderApp]
IDS = ["video", "audio"]

META = {"title": "T", "channel": "C", "duration": 60,
        "is_playlist": False, "count": 1}


@pytest.fixture(scope="session")
def qapp():
    """Held for the whole session: an unbound QApplication is collected, and
    constructing a widget after that aborts the interpreter."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(request, qapp):
    w = request.param()
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()


class _FakeThread:
    """_on_done/_on_error reap self.thread; no real QThread is needed here."""

    def quit(self): pass

    def wait(self): pass


# ── Error text ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "Cookies from browser"),
    ("HTTP Error 403: Forbidden", "Cookies from browser"),
    ("HTTP Error 429: Too Many Requests", "rate-limiting"),
    ("ERROR: Video unavailable", "unavailable"),
    ("<urlopen error [Errno -3] Temporary failure in name resolution>", "No connection"),
    ("OSError: [Errno 28] No space left on device", "disk is full"),
    ("ERROR: unable to open for writing: Permission denied", "another"),
])
def test_known_failures_say_what_to_do_next(raw, expected):
    assert expected in common.friendly_error(raw)


def test_unknown_failures_are_passed_through_not_guessed_at():
    assert common.friendly_error("ERROR: something nobody mapped\nstack") == \
        "something nobody mapped"


def test_no_message_still_yields_a_sentence():
    assert common.friendly_error("").endswith(".")


# ── GUI state ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_percentage_does_not_stay_green_after_a_finished_download(window):
    window.thread = _FakeThread()
    window._on_done()
    assert "3FB950" in window.pct_big.styleSheet().upper()
    window._set_downloading()
    assert "3FB950" not in window.pct_big.styleSheet().upper()


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_title_elides_to_the_window_not_to_a_character_count(window):
    long_title = "Word " * 60
    window._set_ready({**META, "title": long_title})
    window.resize(720, 660)
    QApplication.instance().processEvents()
    narrow = window.title_label.text()
    window.resize(1600, 900)
    QApplication.instance().processEvents()
    wide = window.title_label.text()
    assert narrow.endswith("…") and wide.endswith("…")
    assert len(wide) > len(narrow)


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_fetching_and_failure_both_fill_the_empty_body(window):
    window._set_fetching()
    assert window.empty.isVisible()
    assert "Reading" in window.empty_title.text()

    window._on_meta_failed("HTTP Error 403: Forbidden")
    assert window.empty.isVisible()
    assert not window.card.isVisible()
    assert "Cookies from browser" in window.empty_body.text()

    window._set_idle()
    assert window.empty_title.text() == window.EMPTY_TITLE


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_a_failed_download_explains_itself_and_drops_the_stale_speed(window):
    window.thread = _FakeThread()
    window.speed_label.setText("8.2 MB/s  ·  ETA 51s")
    window._on_error("HTTP Error 403: Forbidden")
    assert "Cookies from browser" in window.status_label.text()
    assert window.speed_label.text() == ""
    # Download stays on screen: pressing it again is the retry.
    assert window.dl_btn.isVisible()


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_enter_in_the_url_field_is_wired_to_the_primary_action(window):
    """Reconnecting here would only test that Qt signals work; count receivers."""
    assert window.url_input.receivers(window.url_input.returnPressed) == 1


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_enter_with_no_metadata_starts_nothing(window):
    window._meta = {}
    window.url_input.setText("https://example.invalid/x")
    window.url_input.returnPressed.emit()
    assert not hasattr(window, "worker")


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_escape_cancels_only_while_a_download_can_be_cancelled(window):
    cancelled = []
    window._cancel_download = lambda: cancelled.append(True)
    esc = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)

    window.keyPressEvent(esc)          # idle: cancel button hidden
    assert cancelled == []

    window._set_ready(dict(META))
    window._set_downloading()
    QApplication.instance().processEvents()
    window.keyPressEvent(esc)
    assert cancelled == [True]


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_every_control_is_announced_to_a_screen_reader(window):
    named = {attr: getattr(window, attr).accessibleName()
             for attr in window.A11Y_NAMES if hasattr(window, attr)}
    assert named, "no control matched A11Y_NAMES"
    assert all(named.values()), [k for k, v in named.items() if not v]


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_the_ready_layout_fits_inside_the_minimum_window(window):
    """A minimum smaller than the layout is how controls came to overlap."""
    window._set_ready(dict(META))
    QApplication.instance().processEvents()
    needed = window.centralWidget().widget().minimumSizeHint().height()
    assert window.minimumHeight() >= needed, (window.minimumHeight(), needed)


# ── TUI state ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tui(monkeypatch):
    import dep_check
    monkeypatch.setattr(dep_check, "check_deps", lambda **kw: [])
    monkeypatch.setattr(ytd_tui.YTDApp, "_run_download", lambda self, *a, **k: None)
    return ytd_tui.YTDApp()


def _note(app):
    return str(app.query_one("#empty").render())


async def test_tui_download_error_is_on_screen_not_only_in_the_hidden_log(tui):
    async with tui.run_test() as pilot:
        assert "log-visible" not in tui.query_one("#log").classes
        tui._ui_error("HTTP Error 403: Forbidden")
        await pilot.pause()
        assert "Cookies from browser" in _note(tui)


async def test_tui_failed_metadata_fetch_says_so(tui):
    async with tui.run_test() as pilot:
        tui._ui_meta("Song", "Channel · 1:00")
        await pilot.pause()
        tui._ui_meta_failed("ERROR: Video unavailable")
        await pilot.pause()
        assert tui.query_one("#meta-card").display is False
        assert "unavailable" in _note(tui)


async def test_tui_says_it_is_reading_the_link_while_it_fetches(tui, monkeypatch):
    monkeypatch.setattr(ytd_tui.YTDApp, "_fetch_meta", lambda self, url: None)
    async with tui.run_test() as pilot:
        tui._start_fetch("https://youtube.com/watch?v=x")
        await pilot.pause()
        assert "Reading" in _note(tui)


async def test_tui_action_row_fits_an_eighty_column_terminal(tui):
    async with tui.run_test(size=(80, 30)) as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        widths = [w.outer_size.width for w in tui.query("#btn-row > Button")]
        assert sum(widths) + 6 <= 80, widths
        for select in tui.query("#adv-row > Select"):
            assert select.region.right <= 80, select.id


# ── Dialogs: one design system, and failures you can act on ──────────────────

def test_update_failure_keeps_the_dialog_open_and_offers_the_release_page(
        qapp, monkeypatch):
    """It used to report and reject() together, then open a browser unasked."""
    import webbrowser
    import update_ui

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    dlg = update_ui.UpdateDialog("v9.9.9", "https://x/y.deb", "y.deb",
                                 "https://example.com/releases")
    rejected = []
    dlg.rejected.connect(lambda: rejected.append(True))

    dlg._on_error("connection reset")

    assert not opened, "a browser was opened without being asked for"
    assert not rejected, "the dialog closed before the message could be read"
    # isHidden, not isVisible: the dialog itself is never shown here, and a
    # child of a hidden parent is never 'visible' whatever it was told.
    assert not dlg._status.isHidden()
    assert "release page" in dlg._status.text()
    assert dlg._btn.isEnabled() and "release page" in dlg._btn.text()

    dlg._btn.click()
    assert opened == ["https://example.com/releases"]
    dlg.deleteLater()


def test_dep_dialog_names_its_copy_buttons(qapp):
    import dep_check
    dlg = dep_check.DepDialog([
        {"name": "ffmpeg", "reason": "Needed for merging.",
         "cmd": "sudo apt install ffmpeg", "required": True},
    ])
    from PyQt5.QtWidgets import QPushButton
    copies = [b for b in dlg.findChildren(QPushButton)
              if b.objectName() == "copy-btn"]
    assert copies and all("ffmpeg" in b.accessibleName() for b in copies)
    dlg.deleteLater()


# ── TUI option row ────────────────────────────────────────────────────────────

async def test_tui_option_headings_follow_the_selected_mode(tui):
    async with tui.run_test() as pilot:
        assert tui.query_one("#lbl-quality").display is True
        assert tui.query_one("#lbl-format").display is False
        await pilot.click("#rb-audio")
        await pilot.pause()
        assert tui.query_one("#lbl-quality").display is False
        assert tui.query_one("#lbl-format").display is True
        assert tui.query_one("#lbl-bitrate").display is True


@pytest.mark.parametrize("audio", [False, True], ids=["video", "audio"])
async def test_tui_option_row_fits_an_eighty_column_terminal(tui, audio):
    """Audio mode totalled 89 columns, cutting the cookies select in half."""
    async with tui.run_test(size=(80, 24)) as pilot:
        if audio:
            await pilot.click("#rb-audio")
        await pilot.pause()
        shown = [w for w in tui.query("#options-row > Select") if w.display]
        assert shown
        for w in shown:
            assert w.region.right <= 80, (w.id, w.region.right)
            # A value that wraps spills out of the 3-row box it lives in.
            assert w.region.height == 3, (w.id, w.region.height)


# ── Save folder ───────────────────────────────────────────────────────────────

def test_a_folder_that_does_not_exist_yet_is_fine(tmp_path):
    """yt-dlp creates it; only the nearest existing ancestor has to be writable."""
    assert common.save_path_problem(str(tmp_path / "new" / "nested")) is None


@pytest.mark.parametrize("bad,expected", [
    ("", "Choose a folder"),
    ("   ", "Choose a folder"),
    ("/proc/no-such-place", "can’t be written to"),
])
def test_unusable_save_folders_are_named(bad, expected):
    problem = common.save_path_problem(bad)
    assert problem and expected in problem


def test_a_file_is_not_a_folder(tmp_path):
    f = tmp_path / "notadir.txt"
    f.write_text("")
    assert "not a folder" in common.save_path_problem(str(f))


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_download_stops_before_it_starts_on_an_unwritable_folder(window):
    """It used to fetch metadata, start a thread, and fail on the write."""
    window._meta = dict(META, _url="https://x/y")
    window.url_input.setText("https://x/y")
    window.save_input.setText("/proc/no-such-place")

    window._start_download()

    assert not hasattr(window, "worker"), "a download thread was started anyway"
    assert "can’t be written to" in window.status_label.text()
    assert window.save_input.hasFocus()


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_leaving_the_folder_field_reports_a_problem_immediately(window):
    window.save_input.setText("/proc/no-such-place")
    window._check_save_path()
    assert "✗" in window.status_label.text()
    window.save_input.setText(str(pathlib.Path.home()))
    window._check_save_path()
    assert window.status_label.text() == "", "the error outlived the problem"


# ── Window icon ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", ["video", "audio"])
def test_the_window_icon_is_square_at_every_size(key, qapp):
    """logo.png is 640x153: asked for 64x64, Qt returned 64x15."""
    from PyQt5.QtCore import QSize
    import theme
    icon = theme.app_icon(key)
    for n in (16, 32, 64, 256):
        pix = icon.pixmap(QSize(n, n))
        assert (pix.width(), pix.height()) == (n, n), (key, n)
        assert not pix.isNull()


def test_the_two_apps_do_not_share_one_window_icon(qapp):
    """Both shipped the same wordmark, so the switcher could not tell them apart."""
    from PyQt5.QtCore import QSize
    import theme
    shots = [theme.app_icon(k).pixmap(QSize(64, 64)).toImage()
             for k in ("video", "audio")]
    assert shots[0] != shots[1]


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_each_window_carries_its_own_identity(window):
    assert not window.windowIcon().isNull()


@pytest.mark.parametrize("spec", ["youtube-downloader.spec",
                                  "youtube-audio-downloader.spec"])
def test_the_wordmark_is_no_longer_bundled(spec):
    """Nothing reads it at runtime once the icon is drawn."""
    src = (pathlib.Path(__file__).resolve().parent.parent / spec).read_text()
    assert "datas=[('logo.png'" not in src.replace('"', "'")


# ── Advanced panel ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_opening_advanced_keeps_the_primary_action_on_screen(window):
    """Two rows of two needed 773 px against a 700 px window, so Download fell
    under the fold the moment the panel opened."""
    window._set_ready(dict(META))
    window._toggle_advanced()
    QApplication.instance().processEvents()
    assert window.adv_panel.isVisible()
    visible = window.dl_btn.visibleRegion().boundingRect().height()
    assert visible >= window.dl_btn.height(), (
        f"only {visible} of {window.dl_btn.height()}px of Download is on screen")


@pytest.mark.parametrize("window", WINDOWS, ids=IDS, indirect=True)
def test_the_advanced_controls_are_built_once_for_both_apps(window):
    for attr in ("adv_frag", "adv_buf", "adv_chunk", "adv_timeout", "adv_aria2c"):
        assert hasattr(window, attr), attr
    # One row: every combo shares a top edge.
    tops = {window.mapFromGlobal(getattr(window, a).mapToGlobal(
        getattr(window, a).rect().topLeft())).y()
        for a in ("adv_frag", "adv_buf", "adv_chunk", "adv_timeout")}
    assert len(tops) == 1, f"the advanced combos sit on {len(tops)} rows"
