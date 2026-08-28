"""Cold-start cost.

Startup was ~120 ms of imports before a window appeared, over half of it yt-dlp
— which is not touched until a download begins — plus qt-material, which
applied a theme that theme.py immediately overrode and dragged jinja2 along.

These assertions are structural rather than timed: a wall-clock budget is flaky
on shared CI runners, but the properties that produce the speed-up are exact.
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ["ytd", "ytd_audio", "ytd_tui"]


def _read(rel):
    """Always decode as UTF-8.

    Path.read_text() uses the locale codec, which on Windows is cp1252 — and
    ytd.py / ytd_audio.py contain box-drawing characters. Six of these tests
    passed everywhere but the Windows runners until they came through here.
    """
    return (ROOT / rel).read_text(encoding="utf-8")


def _import_probe(module, expression):
    """Import `module` in a clean interpreter and evaluate `expression`."""
    code = f"import sys; import {module}; print(repr({expression}))"
    # Inherit the environment and override only what matters: a hand-built env
    # drops SYSTEMROOT/TEMP, without which Python cannot start on Windows.
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=str(ROOT), env=env)
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("app", APPS)
def test_yt_dlp_is_not_executed_at_import(app):
    """It is over half the import cost and is unused until a download starts."""
    got = _import_probe(app, "type(sys.modules['yt_dlp']).__name__")
    assert got == "'_LazyModule'", (
        f"{app} eagerly imports yt-dlp ({got}); use common.lazy_import")


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("heavy", ["qt_material", "jinja2"])
def test_dropped_dependencies_stay_dropped(app, heavy):
    got = _import_probe(app, f"'{heavy}' in sys.modules")
    assert got == "False", f"{app} pulls in {heavy} again"


def test_qt_material_is_not_a_requirement():
    assert "qt-material" not in _read("requirements.txt")


@pytest.mark.parametrize("spec", ["youtube-downloader.spec",
                                  "youtube-audio-downloader.spec"])
def test_specs_exclude_unused_qt_modules(spec):
    """Every bundled module is unpacked by the bootloader on each launch."""
    src = _read(spec)
    for excluded in ("PyQt5.QtWebEngine", "PyQt5.QtQml", "PyQt5.QtSql",
                     "tkinter", "qt_material"):
        assert excluded in src, f"{spec} no longer excludes {excluded}"


@pytest.mark.parametrize("app", APPS)
def test_import_stays_under_budget(app):
    """A loose ceiling: catches a new top-level import of something enormous.

    Deliberately generous — this is a smoke alarm, not a stopwatch.
    """
    import time
    code = f"import time;t=time.perf_counter();import {app};print(time.perf_counter()-t)"
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=str(ROOT), env=env)
    assert out.returncode == 0, out.stderr[-500:]
    # Take the last line: a warning on stdout would otherwise break the parse.
    elapsed = float(out.stdout.strip().splitlines()[-1]) * 1000
    assert elapsed < 900, f"{app} import took {elapsed:.0f} ms"


# ── Regressions found by profiling first paint, not import ────────────────────

def test_check_deps_does_not_materialise_the_lazy_yt_dlp():
    """The trap that silently undid lazy loading.

    importlib.util.find_spec() short-circuits on sys.modules and reads
    __spec__, which on a LazyLoader module runs the deferred import. check_deps
    runs before the first window paint in all three apps, so the 55 ms and 68
    submodules lazy_import saved were being paid a few lines later anyway.
    """
    code = (
        "import sys, ytd; import dep_check; dep_check.check_deps(); "
        "print(type(sys.modules['yt_dlp']).__name__)"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT), env=env)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip().splitlines()[-1] == "_LazyModule", (
        "check_deps forced the full yt-dlp import")


def test_missing_yt_dlp_is_still_reported():
    """The fast path must not become a blind path."""
    code = (
        "import sys, importlib.util\n"
        "_real = importlib.util.find_spec\n"
        "importlib.util.find_spec = lambda n, *a, **k: "
        "None if n == 'yt_dlp' else _real(n, *a, **k)\n"
        "import dep_check\n"
        "print([d['name'] for d in dep_check.check_deps()])\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT), env=env)
    assert out.returncode == 0, out.stderr[-800:]
    assert "yt-dlp" in out.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("app", ["ytd", "ytd_audio"])
def test_urllib_is_not_imported_before_the_window(app):
    """~17 ms of http.client/email.parser/ssl, first needed by the thumbnail
    fetcher — which cannot run until metadata has arrived."""
    got = _import_probe(app, "'urllib.request' in sys.modules")
    assert got == "False", f"{app} imports urllib.request at startup"


@pytest.mark.parametrize("app", ["ytd", "ytd_audio", "ytd_tui"])
def test_update_check_is_not_imported_before_the_window(app):
    """The update check fires three seconds after first paint."""
    got = _import_probe(app, "'updater' in sys.modules")
    assert got == "False", f"{app} imports updater at startup"


@pytest.mark.parametrize("app", ["ytd", "ytd_audio"])
def test_stylesheet_has_no_universal_font_rule(app):
    """A `* { font-family: <7-family stack> }` rule makes Qt re-run family
    matching per widget, and six of the seven families are other platforms' UI
    fonts — a fontconfig miss each. theme.apply_font resolves it once.
    """
    src = _read(f"{app}.py")
    assert "* {{ font-family:" not in src and "* { font-family:" not in src, (
        f"{app} reintroduced the universal font rule")
    assert "apply_font" in src, f"{app} no longer applies the resolved font"


def test_apply_font_picks_the_same_family_the_stack_would():
    """Resolving the stack by hand must not change what the user sees."""
    code = (
        "from PyQt5.QtWidgets import QApplication\n"
        "from PyQt5.QtGui import QFont, QFontInfo\n"
        "import theme\n"
        "app = QApplication([])\n"
        "stack = [f.strip().strip('\\\"') for f in theme.FONT_STACK.split(',')]\n"
        "qt = QFont(); qt.setFamilies(stack)\n"
        "theme.apply_font(app)\n"
        "print(QFontInfo(qt).family() == QFontInfo(app.font()).family())\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=str(ROOT), env=env)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip().splitlines()[-1] == "True", (
        "apply_font resolves to a different family than the CSS stack did")


@pytest.mark.parametrize("app", ["ytd_core", "ytd_tui"])
def test_downloader_progress_bar_is_off(app):
    """quiet=True does not gate yt-dlp's progress bar; noprogress does. It was
    formatting a terminal bar per chunk that no front-end here displays.

    ytd_core covers both desktop apps; they share one worker now.
    """
    src = _read(f"{app}.py")
    assert "noprogress" in src, f"{app} lets yt-dlp draw a progress bar"


@pytest.mark.parametrize("app", ["ytd", "ytd_audio"])
def test_no_font_is_built_without_a_family(app):
    """QFont('') carries no family and resolves to a serif face.

    While the stylesheet had a universal font rule this was masked — the rule
    overrode the widget font. Removing that rule made two labels render serif,
    with ligatures, until they were derived from the inherited font instead.
    """
    import ast

    tree = ast.parse(_read(f"{app}.py"))
    bad = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "QFont"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == ""
    ]
    assert not bad, f"{app} builds a QFont with an empty family at line(s) {bad}"
