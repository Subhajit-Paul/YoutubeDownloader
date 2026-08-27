"""Import and construction smoke tests.

A frozen build fails at startup for things that never show up in unit tests:
a syntax error in a rarely-touched module, a Qt widget built at import time,
a stylesheet referencing a missing colour constant. Importing every module and
constructing the top-level windows catches those cheaply.
"""
import importlib

import pytest

MODULES = ["common", "version", "updater", "dep_check", "update_ui",
           "ytd", "ytd_audio", "ytd_tui"]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    assert importlib.import_module(name) is not None


def test_every_app_declares_a_version():
    import version
    assert version.__version__
    assert version.GITHUB_REPO.count("/") == 1


@pytest.mark.parametrize("mod,cls", [
    ("ytd", "YoutubeDownloaderApp"),
    ("ytd_audio", "YoutubeAudioDownloaderApp"),
])
def test_gui_main_window_constructs(mod, cls):
    """Builds the full widget tree offscreen — catches stylesheet/layout errors."""
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    window = getattr(importlib.import_module(mod), cls)()
    assert window.windowTitle()
    window.close()
    window.deleteLater()


def test_dep_dialog_is_available_with_qt_and_lists_deps():
    from PyQt5.QtWidgets import QApplication
    import dep_check
    app = QApplication.instance() or QApplication([])
    assert dep_check.DepDialog is not None
    dlg = dep_check.DepDialog([
        {"name": "ffmpeg", "reason": "needed", "cmd": "sudo apt install ffmpeg",
         "required": True},
    ])
    assert dlg.windowTitle() == "Missing Dependencies"
    dlg.close()
    dlg.deleteLater()
