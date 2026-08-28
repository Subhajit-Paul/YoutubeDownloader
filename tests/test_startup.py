"""Cold-start cost.

Startup was ~120 ms of imports before a window appeared, over half of it yt-dlp
— which is not touched until a download begins — plus qt-material, which
applied a theme that theme.py immediately overrode and dragged jinja2 along.

These assertions are structural rather than timed: a wall-clock budget is flaky
on shared CI runners, but the properties that produce the speed-up are exact.
"""
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = ["ytd", "ytd_audio", "ytd_tui"]


def _import_probe(module, expression):
    """Import `module` in a clean interpreter and evaluate `expression`."""
    code = f"import sys; import {module}; print(repr({expression}))"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=str(ROOT), env={"PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen",
                            "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout.strip()


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
    assert "qt-material" not in (ROOT / "requirements.txt").read_text()


@pytest.mark.parametrize("spec", ["youtube-downloader.spec",
                                  "youtube-audio-downloader.spec"])
def test_specs_exclude_unused_qt_modules(spec):
    """Every bundled module is unpacked by the bootloader on each launch."""
    src = (ROOT / spec).read_text()
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
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=str(ROOT), env={"PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen",
                            "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr[-500:]
    elapsed = float(out.stdout.strip()) * 1000
    assert elapsed < 900, f"{app} import took {elapsed:.0f} ms"
