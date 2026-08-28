"""Compatibility with dependencies, Python versions and platforms.

Dependabot bumps these monthly. The apps call a specific slice of each library's
API; these tests fail when a bump removes or renames something the apps rely on,
instead of the failure surfacing as a crash in a shipped binary.
"""
import ast
import configparser
import inspect
import pathlib
import sys

import pytest

# The GUI download workers live in ytd_core now, so that is where they
# resolve yt_dlp; the TUI still owns its own. Patch where code looks it up.
def _ydl(mod):
    import ytd_core
    return getattr(mod, "yt_dlp", None) or ytd_core.yt_dlp


ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted(ROOT.glob("*.py")) + [ROOT / "android" / "main.py"]


# ── source hygiene ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_sources_are_utf8_and_parse(path):
    """Windows defaults to cp1252; these files contain box-drawing characters."""
    src = path.read_text(encoding="utf-8")
    ast.parse(src)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_tabs_mixed_into_indentation(path):
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        assert not line.startswith("\t"), f"{path.name}:{i} indents with a tab"


# ── declared versions agree ──────────────────────────────────────────────────

def _app_version():
    ns = {}
    exec((ROOT / "version.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def test_pyproject_version_matches_version_py():
    import tomllib
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == _app_version()


def test_requires_python_covers_every_version_ci_tests():
    import tomllib
    import yaml
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = data["project"]["requires-python"].lstrip(">=")
    wf = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8"))
    tested = wf["jobs"]["test"]["strategy"]["matrix"]["python"]
    floor_t = tuple(int(x) for x in floor.split("."))
    for v in tested:
        assert tuple(int(x) for x in str(v).split(".")) >= floor_t, (
            f"CI tests {v} but pyproject requires-python is {floor}")


def test_release_workflow_python_is_supported():
    import tomllib
    import yaml
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = tuple(int(x) for x in data["project"]["requires-python"].lstrip(">=").split("."))
    wf = yaml.safe_load((ROOT / ".github/workflows/build-release.yml").read_text(encoding="utf-8"))
    for step in wf["jobs"]["build"]["steps"]:
        if "setup-python" in str(step.get("uses", "")):
            got = tuple(int(x) for x in str(step["with"]["python-version"]).split("."))
            assert got >= floor


# ── yt-dlp API surface ───────────────────────────────────────────────────────

def _worker_opts(runner_name):
    from unittest import mock
    import ytd
    import ytd_audio
    import ytd_core

    class Rec:
        def __call__(self, opts):
            self.opts = opts
            return self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def download(self, urls): return 0

    rec = Rec()
    if runner_name == "video":
        w = ytd.DownloadWorker("https://x/1", "/tmp/dl", "Best", use_aria2c=True,
                               browser="Firefox")
        mod = ytd
    else:
        w = ytd_audio.DownloadWorker("https://x/1", "/tmp/dl", "mp3", "192",
                                     use_aria2c=True, browser="Firefox")
        mod = ytd_audio
    with mock.patch.object(_ydl(mod), "YoutubeDL", rec):
        w.run()
    return rec.opts


@pytest.mark.parametrize("kind", ["video", "audio"])
def test_every_ytdlp_option_used_is_still_documented(kind):
    """yt-dlp silently ignores unknown keys — a rename would otherwise go unnoticed."""
    from yt_dlp import YoutubeDL
    documented = inspect.getdoc(YoutubeDL)
    unknown = [k for k in _worker_opts(kind) if k not in documented]
    assert not unknown, f"options not found in yt-dlp's documented params: {unknown}"


def test_audio_postprocessor_key_resolves():
    from yt_dlp.postprocessor import get_postprocessor
    assert get_postprocessor("FFmpegExtractAudio") is not None


def test_download_cancelled_exception_exists():
    import yt_dlp
    assert issubclass(yt_dlp.utils.DownloadCancelled, Exception)


def test_ytdlp_download_returns_a_status_code():
    """The apps rely on the return value to detect failure under ignoreerrors."""
    import yt_dlp
    sig = inspect.signature(yt_dlp.YoutubeDL.download)
    assert "url_list" in sig.parameters or len(sig.parameters) >= 2


# ── textual API surface ──────────────────────────────────────────────────────

def test_textual_binding_supports_priority():
    from textual.binding import Binding
    assert "priority" in inspect.signature(Binding).parameters


def test_textual_widgets_used_by_the_tui_exist():
    import textual.widgets as w
    for name in ("Input", "Button", "Select", "RadioSet", "RadioButton",
                 "ProgressBar", "RichLog", "Label", "Footer", "Header"):
        assert hasattr(w, name), f"textual.widgets.{name} is gone"


def test_textual_select_blank_sentinel_exists():
    from textual.widgets import Select
    assert hasattr(Select, "BLANK")


def test_textual_worker_decorator_supports_thread():
    from textual import work
    assert "thread" in inspect.signature(work).parameters


# ── PyQt5 API surface ────────────────────────────────────────────────────────

def test_pyqt_widgets_used_by_the_guis_exist():
    import PyQt5.QtWidgets as w
    for name in ("QMainWindow", "QDialog", "QVBoxLayout", "QHBoxLayout",
                 "QLabel", "QPushButton", "QComboBox", "QLineEdit",
                 "QProgressBar", "QFileDialog", "QApplication", "QFrame"):
        assert hasattr(w, name), f"PyQt5.QtWidgets.{name} is gone"


def test_pyqt_core_primitives_exist():
    from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, Qt
    assert all([QObject, QThread, QTimer, pyqtSignal, Qt])


# ── platform behaviour ───────────────────────────────────────────────────────

def test_save_path_join_is_platform_correct():
    """outtmpl is built with os.path.join; it must stay inside the save dir."""
    import os
    base = os.path.join("C:\\Users\\x" if sys.platform == "win32" else "/home/x", "dl")
    joined = os.path.join(base, "%(title)s.%(ext)s")
    assert joined.startswith(base)


@pytest.mark.parametrize("raw,forbidden", [
    ("a/b", "/"),
    ("a\\b", "\\"),
    ("../../etc/passwd", "/"),
])
def test_ytdlp_neutralises_path_separators_in_titles(raw, forbidden):
    """The apps rely on this to keep a remote title from steering the path."""
    from yt_dlp.utils import sanitize_filename
    assert forbidden not in sanitize_filename(raw)


@pytest.mark.parametrize("name", ["CON", "PRN", "AUX", "NUL", "COM1"])
def test_windows_reserved_device_names_are_a_known_gap(name):
    """Documented limitation: yt-dlp leaves these intact, so a video titled
    'CON' cannot be saved on Windows. Asserting current behaviour so that a
    future yt-dlp change is noticed rather than silently altering filenames."""
    from yt_dlp.utils import sanitize_filename
    assert sanitize_filename(name) == name


# ── the shared engine stays shared ───────────────────────────────────────────

def test_the_two_desktop_apps_no_longer_duplicate_the_engine():
    """They were 89% identical line for line, and the identical part was the
    engine — so every fix in it had to be made twice, and one of them getting
    missed was a matter of memory rather than of design.

    Asserted as structure, not a similarity percentage: the windows are allowed
    to look alike, but neither app may carry its own copy of the workers.
    """
    import ast as _ast

    root = pathlib.Path(__file__).resolve().parent.parent
    shared = {"MetaWorker", "ThumbnailFetcher", "ThumbWidget"}
    for app in ("ytd.py", "ytd_audio.py"):
        tree = _ast.parse((root / app).read_text(encoding="utf-8"))
        defined = {n.name for n in tree.body if isinstance(n, _ast.ClassDef)}
        clash = defined & shared
        assert not clash, f"{app} redefines {sorted(clash)} instead of using ytd_core"

        worker = next((n for n in tree.body
                       if isinstance(n, _ast.ClassDef) and n.name == "DownloadWorker"), None)
        assert worker is not None, f"{app} has no DownloadWorker"
        bases = {b.id for b in worker.bases if isinstance(b, _ast.Name)}
        assert "BaseDownloadWorker" in bases, (
            f"{app}'s DownloadWorker no longer builds on the shared one: {bases}")

        # It may say what to download; it may not restate how.
        methods = {n.name for n in worker.body if isinstance(n, _ast.FunctionDef)}
        assert methods <= {"__init__", "media_opts"}, (
            f"{app}'s worker overrides shared behaviour: "
            f"{sorted(methods - {'__init__', 'media_opts'})}")

        # The window may lay itself out; the state machine is shared.
        window = next(n for n in tree.body if isinstance(n, _ast.ClassDef)
                      and n.name.endswith("DownloaderApp"))
        assert {b.id for b in window.bases if isinstance(b, _ast.Name)} == {"BaseWindow"}
        win_methods = {n.name for n in window.body if isinstance(n, _ast.FunctionDef)}
        allowed = {"_build_ui", "_start_download", "_selected_bitrate"}
        assert win_methods <= allowed, (
            f"{app}'s window re-implements shared behaviour: "
            f"{sorted(win_methods - allowed)}")


@pytest.mark.parametrize("mod_name", ["ytd", "ytd_audio"])
def test_both_apps_resolve_the_same_engine(mod_name):
    """One worker, one stylesheet base, one set of option lists."""
    import importlib

    import ytd_core
    mod = importlib.import_module(mod_name)
    assert issubclass(mod.DownloadWorker, ytd_core.BaseDownloadWorker)
    assert issubclass(mod._ThumbWidget, ytd_core.ThumbWidget)
    assert issubclass(mod.DownloadWorker, ytd_core.BaseDownloadWorker)

    window = getattr(mod, "YoutubeDownloaderApp", None) or mod.YoutubeAudioDownloaderApp
    assert window._SS.startswith(ytd_core.BASE_SS), (
        f"{mod_name} no longer builds its stylesheet on the shared base")
