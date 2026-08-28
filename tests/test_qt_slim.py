"""packaging/qt_slim.py — the two build-time trims, and what must survive them.

The Linux GUI bundle was 111.4 MB, of which Qt was 63.6% and a single ICU data
table 21.4%. These trims take it to 85.3 MB. Both are opportunistic: the point
of most of these tests is that they degrade to a no-op instead of to a bundle
that will not start.
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import qt_slim  # noqa: E402


GUI_SPECS = ["youtube-downloader.spec", "youtube-audio-downloader.spec"]


def _entry(dest, src):
    """A PyInstaller TOC entry: (dest name, source path, typecode)."""
    return (dest, src, "BINARY")


# ── ICU ───────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform != "linux",
                    reason="Qt bundles this ELF ICU table only on Linux")
def test_icu_stub_replaces_the_data_table(tmp_path):
    real = tmp_path / "libicudata.so.56"
    real.write_bytes(b"\0" * 4096)
    binaries = [_entry("libicudata.so.56", str(real)),
                _entry("libQt5Core.so.5", "/nonexistent/libQt5Core.so.5")]

    out, note = qt_slim.stub_icu_data(binaries, str(tmp_path / "work"))

    icu = [b for b in out if b[0] == "libicudata.so.56"]
    assert len(icu) == 1, "exactly one ICU entry must remain"
    assert icu[0][1] != str(real), "still pointing at the real table"
    assert os.path.getsize(icu[0][1]) < 65536, "the stub is not small"
    assert "stubbed" in note
    # Everything else is passed through untouched.
    assert any(b[0] == "libQt5Core.so.5" for b in out)


@pytest.mark.skipif(sys.platform != "linux",
                    reason="Qt bundles this ELF ICU table only on Linux")
def test_icu_stub_exports_the_symbol_the_loader_needs(tmp_path):
    """libQt5Core's DT_NEEDED only resolves if icudt<ver>_dat is exported."""
    real = tmp_path / "libicudata.so.56"
    real.write_bytes(b"\0" * 4096)
    out, note = qt_slim.stub_icu_data([_entry("libicudata.so.56", str(real))],
                                      str(tmp_path / "work"))
    if "failed" in note:
        pytest.skip("no C compiler on this machine")
    stub = [b for b in out if b[0] == "libicudata.so.56"][0][1]
    import ctypes
    lib = ctypes.CDLL(stub)
    assert ctypes.c_char.in_dll(lib, "icudt56_dat") is not None


def test_icu_stub_is_a_no_op_where_qt_ships_no_icu():
    """Windows and macOS wheels bundle no ICU; the build must not care."""
    binaries = [_entry("libQt5Core.so.5", "/x/libQt5Core.so.5")]
    out, note = qt_slim.stub_icu_data(binaries, "/tmp/unused")
    assert out == binaries
    assert "nothing to do" in note


def test_icu_stub_keeps_the_real_table_when_there_is_no_compiler(tmp_path,
                                                                 monkeypatch):
    """Slimming is an optimisation. Never trade a smaller bundle for a broken one."""
    real = tmp_path / "libicudata.so.56"
    real.write_bytes(b"\0" * 4096)
    binaries = [_entry("libicudata.so.56", str(real))]
    monkeypatch.setenv("CC", str(tmp_path / "no-such-compiler"))

    out, note = qt_slim.stub_icu_data(binaries, str(tmp_path / "work"))

    assert out == binaries, "the real table must survive a failed compile"
    assert "keeping the real table" in note


# ── Qt plugins ────────────────────────────────────────────────────────────────

# The window opens through these, the tests render through offscreen, and the
# two icon formats are how Windows and macOS carry the app icon.
MUST_KEEP = ["platforms/libqxcb", "platforms/libqwayland-generic",
             "platforms/libqoffscreen", "platforms/libqminimal",
             "imageformats/libqjpeg", "imageformats/libqwebp",
             "imageformats/libqico", "imageformats/libqicns"]


@pytest.mark.parametrize("plugin", MUST_KEEP)
def test_the_drop_list_never_reaches_a_plugin_the_app_needs(plugin):
    assert not any(p in plugin for p in qt_slim.UNUSED_QT_PLUGINS), (
        f"{plugin} is required but matches the drop list")


def test_unused_plugins_are_dropped_and_the_rest_kept(tmp_path):
    def make(name):
        f = tmp_path / name.replace("/", "_")
        f.write_bytes(b"\0" * 1024)
        return _entry(f"PyQt5/Qt5/plugins/{name}.so", str(f))

    binaries = ([make(n) for n in ("platforms/libqwebgl", "platforms/libqvnc",
                                   "imageformats/libqtiff")]
                + [make(n) for n in ("platforms/libqxcb", "imageformats/libqjpeg")])

    out, note = qt_slim.drop_unused_qt_plugins(binaries)

    kept = {b[0] for b in out}
    assert kept == {"PyQt5/Qt5/plugins/platforms/libqxcb.so",
                    "PyQt5/Qt5/plugins/imageformats/libqjpeg.so"}
    assert "dropped 3" in note


def test_plugin_drop_matches_windows_path_separators(tmp_path):
    f = tmp_path / "webgl"
    f.write_bytes(b"\0")
    binaries = [_entry("PyQt5\\Qt5\\plugins\\platforms\\libqwebgl.dll", str(f))]
    out, _ = qt_slim.drop_unused_qt_plugins(binaries)
    assert out == [], "backslash paths must match the drop list too"


def test_plugin_drop_is_a_no_op_when_nothing_matches():
    binaries = [_entry("libQt5Core.so.5", "/x/libQt5Core.so.5")]
    out, note = qt_slim.drop_unused_qt_plugins(binaries)
    assert out == binaries
    assert "none of the unused set" in note


# ── Wiring ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec", GUI_SPECS)
def test_both_gui_specs_apply_the_trims(spec):
    """One helper, two specs — the alternative is two copies that drift."""
    src = (ROOT / spec).read_text(encoding="utf-8")
    assert "import qt_slim" in src, f"{spec} does not import the helper"
    assert "stub_icu_data" in src, f"{spec} does not stub ICU"
    assert "drop_unused_qt_plugins" in src, f"{spec} does not trim plugins"


def test_the_tui_spec_does_not_pull_in_qt_trimming():
    """The TUI bundles no Qt; importing qt_slim there would be noise."""
    src = (ROOT / "youtube-tui.spec").read_text(encoding="utf-8")
    assert "qt_slim" not in src


def test_the_helper_is_not_shipped():
    """It lives under packaging/ so no spec sweeps it into a bundle."""
    assert (ROOT / "packaging" / "qt_slim.py").exists()
    assert not (ROOT / "qt_slim.py").exists(), (
        "at the repo root it would land in the frozen app")
