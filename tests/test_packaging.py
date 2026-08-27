"""Cross-consistency between source, PyInstaller specs, installers and CI.

None of this needs the apps to run: it checks that the names each layer hard-codes
still agree. Every CI failure this repo hit was a disagreement of exactly this kind
(NSIS looking for dist/*.exe from the wrong directory, an installer asset that was
never built, a dep with no Android wheel).
"""
import configparser
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

APPS = [
    # spec file,                        entry script,   exe name
    ("youtube-downloader.spec",         "ytd.py",       "youtube-downloader"),
    ("youtube-audio-downloader.spec",   "ytd_audio.py", "youtube-audio-downloader"),
    ("youtube-tui.spec",                "ytd_tui.py",   "youtube-tui"),
]

GUI_APPS = APPS[:2]


def _read(rel):
    return (ROOT / rel).read_text()


# ── version consistency ──────────────────────────────────────────────────────

def test_app_version_matches_android_package_version():
    version = {}
    exec(_read("version.py"), version)
    cp = configparser.ConfigParser()
    cp.read(ROOT / "android" / "buildozer.spec")
    assert cp["app"]["version"] == version["__version__"]


def test_version_is_a_three_part_release_tag():
    """The release workflow only fires on v[0-9]+.[0-9]+.[0-9]+."""
    version = {}
    exec(_read("version.py"), version)
    assert re.fullmatch(r"\d+\.\d+\.\d+", version["__version__"])


# ── PyInstaller specs ────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec,entry,exe", APPS)
def test_spec_entry_script_exists(spec, entry, exe):
    assert (ROOT / entry).exists()
    assert f"'{entry}'" in _read(spec) or f'"{entry}"' in _read(spec)


@pytest.mark.parametrize("spec,entry,exe", APPS)
def test_spec_builds_the_expected_binary_name(spec, entry, exe):
    assert re.search(rf"""name=['"]{re.escape(exe)}['"]""", _read(spec))


@pytest.mark.parametrize("spec,entry,exe", APPS)
def test_local_modules_imported_by_entry_are_declared_hidden(spec, entry, exe):
    """PyInstaller cannot always follow these; a missing one crashes only when frozen."""
    local = {p.stem for p in ROOT.glob("*.py")} - {"conftest"}
    imported = set(re.findall(r"^\s*(?:from|import)\s+(\w+)", _read(entry), re.M))
    spec_text = _read(spec)
    for mod in sorted(imported & local):
        assert mod in spec_text, f"{entry} imports {mod!r} but {spec} never mentions it"


# ── NSIS installers (Windows) ────────────────────────────────────────────────

@pytest.mark.parametrize("spec,entry,exe", GUI_APPS)
def test_nsis_packages_the_binary_pyinstaller_actually_builds(spec, entry, exe):
    nsi = _read(f"packaging/windows/{exe}.nsi")
    assert f'!define APP_EXE    "{exe}.exe"' in nsi
    assert 'File "dist\\${APP_EXE}"' in nsi


@pytest.mark.parametrize("spec,entry,exe", GUI_APPS)
def test_nsis_output_name_matches_what_the_updater_looks_for(spec, entry, exe):
    """updater._platform_suffix() expects '<app>-windows-x86_64-setup.exe'."""
    nsi = _read(f"packaging/windows/{exe}.nsi")
    assert f'OutFile "release\\{exe}-windows-x86_64-setup.exe"' in nsi


def test_no_orphaned_nsi_scripts():
    built = {f"{exe}.nsi" for _, _, exe in GUI_APPS}
    present = {p.name for p in (ROOT / "packaging" / "windows").glob("*.nsi")}
    assert present == built, f"unused installer script(s): {present - built}"


# ── Debian packaging (Linux) ─────────────────────────────────────────────────

@pytest.mark.parametrize("spec,entry,exe", GUI_APPS)
def test_deb_has_a_desktop_entry(spec, entry, exe):
    desktop = ROOT / "packaging" / "linux" / f"{exe}.desktop"
    assert desktop.exists(), "make-deb.sh installs <app>.desktop unconditionally"
    assert f"Exec={exe}" in desktop.read_text()


def test_no_orphaned_desktop_files():
    built = {f"{exe}.desktop" for _, _, exe in GUI_APPS}
    present = {p.name for p in (ROOT / "packaging" / "linux").glob("*.desktop")}
    assert present == built, f"unused desktop file(s): {present - built}"


# ── CI workflow agreement ────────────────────────────────────────────────────

def _release_workflow():
    return yaml.safe_load(_read(".github/workflows/build-release.yml"))


def _release_steps():
    return _release_workflow()["jobs"]["build"]["steps"]


def _step(name_fragment):
    for s in _release_steps():
        if name_fragment in s.get("name", ""):
            return s
    raise AssertionError(f"no CI step named like {name_fragment!r}")


@pytest.mark.parametrize("spec,entry,exe", APPS)
def test_ci_builds_every_spec(spec, entry, exe):
    runs = " ".join(s.get("run", "") for s in _release_steps())
    assert spec in runs, f"{spec} is never built by build-release.yml"


def test_ci_invokes_makensis_with_nocd():
    """Without /NOCD makensis chdirs to the .nsi dir and cannot find dist/."""
    run = _step("Create Windows packages")["run"]
    for line in run.splitlines():
        if "makensis" in line:
            assert "/NOCD" in line, f"missing /NOCD: {line.strip()}"


def test_dev_fallback_version_is_valid_for_dpkg():
    """dpkg-deb rejects a Version field that does not start with a digit."""
    run = _step("Extract version from tag")["run"]
    fallback = re.search(r'version=([^\s"]+)"?\s*>>', run.split("else")[1])
    assert fallback and fallback.group(1)[0].isdigit()


def _ci_release_filenames():
    """Release artefact names CI writes, with the matrix's ${SUFFIX} expanded."""
    runs = " ".join(s.get("run", "") for s in _release_steps())
    suffixes = [e["artifact_suffix"]
                for e in _release_workflow()["jobs"]["build"]["strategy"]["matrix"]["include"]]
    names = {runs}
    for suf in suffixes:
        names.add(runs.replace("${SUFFIX}", suf))
    return " ".join(names)


@pytest.mark.parametrize("asset", [
    "youtube-tui-linux-x86_64.tar.gz",
    "youtube-tui-macos-arm64.tar.gz",
])
def test_assets_install_tui_downloads_are_produced_by_ci(asset):
    """install-tui.sh fetches these by exact name — a rename in CI breaks the installer."""
    assert asset in _ci_release_filenames(), f"install-tui.sh wants {asset}, CI never creates it"
    assert asset in _read("install-tui.sh")


def test_ci_produces_the_windows_tui_binary():
    """install-tui.sh sends Windows users to the release page for this exact file."""
    assert "youtube-tui-windows-x86_64.exe" in _ci_release_filenames()


def test_install_tui_matches_on_arch_not_just_os():
    """Only linux-x86_64 and macos-arm64 are published; anything else must be refused."""
    script = _read("install-tui.sh")
    assert "uname -m" in script
    assert "Linux/x86_64" in script and "Darwin/arm64" in script


def test_ci_publishes_release_notes_exactly_once():
    """Every matrix job runs the publish step; only one may generate notes."""
    publish = [s for s in _release_steps() if "gh-release" in str(s.get("uses", ""))]
    assert len(publish) == 1
    notes = publish[0]["with"]["generate_release_notes"]
    assert notes is not True, "all matrix jobs would race to write release notes"


# ── Android ──────────────────────────────────────────────────────────────────

def _android_requirements():
    cp = configparser.ConfigParser()
    cp.read(ROOT / "android" / "buildozer.spec")
    return [r.strip() for r in cp["app"]["requirements"].split(",")]


def test_android_pins_p4a_so_master_cannot_drift():
    cp = configparser.ConfigParser()
    cp.read(ROOT / "android" / "buildozer.spec")
    branch = cp["app"].get("p4a.branch", "")
    assert re.fullmatch(r"v\d{4}\.\d{2}\.\d{2}", branch), "p4a must be pinned to a release"


@pytest.mark.parametrize("pkg", ["brotli", "brotlicffi", "pycryptodomex", "lxml"])
def test_android_avoids_c_extensions_without_android_wheels(pkg):
    """p4a resolves with --only-binary=:all: --platform=android_*; these have no wheel."""
    assert pkg not in [r.lower() for r in _android_requirements()]


def test_android_entry_point_exists():
    assert (ROOT / "android" / "main.py").exists()
