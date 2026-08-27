"""Functional tests for the TUI, driven through textual's pilot harness.

The real app is mounted and interacted with; only _run_download is stubbed so
no network access happens. This covers the input validation and mode switching
that unit tests on helpers alone would miss.
"""
import pytest

import ytd_tui


@pytest.fixture
def app(monkeypatch):
    calls = []
    monkeypatch.setattr(ytd_tui.YTDApp, "_run_download",
                        lambda self, *a, **k: calls.append((a, k)))
    instance = ytd_tui.YTDApp()
    instance.download_calls = calls
    return instance


async def test_app_mounts_with_url_focused(app):
    async with app.run_test() as pilot:
        assert pilot.app.focused.id == "url-input"


async def test_cancel_disabled_until_a_download_starts(app):
    async with app.run_test():
        assert app.query_one("#cancel-btn").disabled is True


async def test_empty_url_is_rejected(app):
    async with app.run_test() as pilot:
        await pilot.press("ctrl+d")
        assert app.download_calls == []


@pytest.mark.parametrize("bad", ["youtube.com/watch?v=x", "ftp://x/y", "just some text"])
async def test_url_without_http_scheme_is_rejected(app, bad):
    async with app.run_test() as pilot:
        app.query_one("#url-input").value = bad
        await pilot.press("ctrl+d")
        assert app.download_calls == []


async def test_empty_save_path_is_rejected(app):
    async with app.run_test() as pilot:
        app.query_one("#url-input").value = "https://youtu.be/x"
        app.query_one("#save-input").value = ""
        await pilot.press("ctrl+d")
        assert app.download_calls == []


async def test_valid_input_starts_a_download(app, tmp_path):
    async with app.run_test() as pilot:
        app.query_one("#url-input").value = "https://youtu.be/abc"
        app.query_one("#save-input").value = str(tmp_path)
        await pilot.press("ctrl+d")
        assert len(app.download_calls) == 1
        args = app.download_calls[0][0]
        assert args[0] == "https://youtu.be/abc"
        assert args[1] == str(tmp_path)
        assert args[2] is False, "video mode is the default"


async def test_download_button_click_also_starts(app, tmp_path):
    async with app.run_test() as pilot:
        app.query_one("#url-input").value = "https://youtu.be/abc"
        app.query_one("#save-input").value = str(tmp_path)
        await pilot.click("#download-btn")
        assert len(app.download_calls) == 1


async def test_save_directory_is_created(app, tmp_path):
    target = tmp_path / "nested" / "downloads"
    async with app.run_test() as pilot:
        app.query_one("#url-input").value = "https://youtu.be/abc"
        app.query_one("#save-input").value = str(target)
        await pilot.press("ctrl+d")
        assert target.is_dir()


async def test_audio_mode_swaps_quality_for_format_and_bitrate(app):
    async with app.run_test() as pilot:
        assert app.query_one("#quality-select").display is True
        assert app.query_one("#format-select").display is False
        await pilot.click("#rb-audio")
        await pilot.pause()
        assert app.query_one("#quality-select").display is False
        assert app.query_one("#format-select").display is True
        assert app.query_one("#bitrate-select").display is True


async def test_audio_mode_is_passed_to_the_downloader(app, tmp_path):
    async with app.run_test() as pilot:
        await pilot.click("#rb-audio")
        await pilot.pause()
        app.query_one("#url-input").value = "https://youtu.be/abc"
        app.query_one("#save-input").value = str(tmp_path)
        await pilot.press("ctrl+d")
        assert app.download_calls[0][0][2] is True


async def test_log_starts_hidden_and_toggles(app):
    async with app.run_test() as pilot:
        log = app.query_one("#log")
        assert log.display is False
        await pilot.press("ctrl+l")
        await pilot.pause()
        assert log.display is True
        await pilot.press("ctrl+l")
        await pilot.pause()
        assert log.display is False


async def test_advanced_options_start_hidden_and_toggle(app):
    async with app.run_test() as pilot:
        adv = app.query_one("#adv-section")
        assert adv.display is False
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert adv.display is True


# ── keybindings ──────────────────────────────────────────────────────────────
# textual's Input binds ctrl+a (home), ctrl+d (delete), ctrl+x (cut) and ctrl+e.
# The app focuses the URL Input on mount, so any app binding that collides with
# those is dead on startup unless declared priority=True. The footer advertises
# every binding, so a silently-swallowed one is a visible lie.

def _binding(key):
    for b in ytd_tui.YTDApp.BINDINGS:
        if b.key == key:
            return b
    raise AssertionError(f"no binding for {key}")


@pytest.mark.parametrize("key", ["ctrl+d", "ctrl+x", "ctrl+a"])
def test_bindings_colliding_with_input_are_priority(key):
    from textual.widgets import Input
    input_keys = {k for b in Input.BINDINGS for k in b.key.split(",")}
    assert key in input_keys, f"{key} no longer collides — this guard can be relaxed"
    assert _binding(key).priority, (
        f"{key} is swallowed by the focused URL Input without priority=True")


async def test_advertised_bindings_fire_while_url_input_is_focused(app):
    """Press each binding with the default focus and assert the action ran."""
    fired = []
    for action in ("toggle_adv", "toggle_log"):
        monkeyed = f"action_{action}"
        setattr(ytd_tui.YTDApp, monkeyed,
                lambda self, a=action: fired.append(a))
    try:
        async with app.run_test() as pilot:
            assert pilot.app.focused.id == "url-input"
            await pilot.press("ctrl+a")
            await pilot.press("ctrl+l")
            await pilot.pause()
        assert set(fired) == {"toggle_adv", "toggle_log"}
    finally:
        importlib_reload = __import__("importlib").reload
        importlib_reload(ytd_tui)
