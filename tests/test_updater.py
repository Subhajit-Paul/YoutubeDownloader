"""updater.py — version comparison, platform asset matching, network handling."""
import io
import json
import sys

import pytest

import updater


# ── version parsing / ordering ────────────────────────────────────────────────

@pytest.mark.parametrize("tag,expected", [
    ("v1.1.1", (1, 1, 1)),
    ("1.1.1", (1, 1, 1)),
    ("v2.0", (2, 0)),
    ("v0.0.0", (0, 0, 0)),
])
def test_parse_version_valid(tag, expected):
    assert updater._parse_version(tag) == expected


@pytest.mark.parametrize("tag", ["v1.2.3-beta", "latest", "", "v..", "vx.y.z"])
def test_parse_version_malformed_degrades_to_zero(tag):
    """Malformed tags must not raise; they sort below any real version."""
    assert updater._parse_version(tag) == (0,)


def test_version_ordering_is_numeric_not_lexicographic():
    """1.10.0 > 1.9.0 — a string compare would get this backwards."""
    assert updater._parse_version("v1.10.0") > updater._parse_version("v1.9.0")
    assert updater._parse_version("v2.0.0") > updater._parse_version("v1.99.99")


# ── platform suffix ───────────────────────────────────────────────────────────

def test_platform_suffix_windows(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    assert updater._platform_suffix() == "windows-x86_64-setup.exe"


def test_platform_suffix_macos_arm(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "arm64")
    assert updater._platform_suffix() == "macos-arm64.dmg"


def test_platform_suffix_macos_intel(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "x86_64")
    assert updater._platform_suffix() == "macos-x86_64.dmg"


def test_platform_suffix_linux(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    assert updater._platform_suffix() == "linux-x86_64.deb"


# ── asset matching ────────────────────────────────────────────────────────────

def _assets(*names):
    return [{"name": n, "browser_download_url": f"https://x/{n}"} for n in names]


REAL_RELEASE_ASSETS = _assets(
    "youtube-audio-downloader-linux-x86_64.deb",
    "youtube-audio-downloader-macos-arm64.dmg",
    "youtube-audio-downloader-windows-x86_64-setup.exe",
    "youtube-downloader-linux-x86_64.deb",
    "youtube-downloader-macos-arm64.dmg",
    "youtube-downloader-windows-x86_64-setup.exe",
    "youtube-tui-linux-x86_64.tar.gz",
    "youtube-tui-macos-arm64.tar.gz",
    "youtube-tui-windows-x86_64.exe",
)


def test_find_asset_picks_the_right_app_on_linux(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    url, name = updater._find_asset(REAL_RELEASE_ASSETS, "youtube-downloader")
    assert name == "youtube-downloader-linux-x86_64.deb"


def test_find_asset_does_not_confuse_video_app_with_audio_app(monkeypatch):
    """'youtube-downloader' is a substring risk against 'youtube-audio-downloader'."""
    monkeypatch.setattr(updater.sys, "platform", "linux")
    _, video = updater._find_asset(REAL_RELEASE_ASSETS, "youtube-downloader")
    _, audio = updater._find_asset(REAL_RELEASE_ASSETS, "youtube-audio-downloader")
    assert video == "youtube-downloader-linux-x86_64.deb"
    assert audio == "youtube-audio-downloader-linux-x86_64.deb"
    assert video != audio


def test_find_asset_returns_none_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    assert updater._find_asset(_assets("unrelated.zip"), "youtube-downloader") == (None, None)


# ── network behaviour ─────────────────────────────────────────────────────────

class _FakeResponse(io.BytesIO):
    def __init__(self, payload, headers=None):
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_release(tag, assets=REAL_RELEASE_ASSETS):
    return json.dumps({
        "tag_name": tag,
        "assets": assets,
        "html_url": f"https://github.com/x/releases/{tag}",
    }).encode()


def test_check_update_reports_newer_release(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.1.1")
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(_fake_release("v1.2.0")))
    tag, url, name, html = updater.check_update("youtube-downloader")
    assert tag == "v1.2.0"
    assert name == "youtube-downloader-linux-x86_64.deb"
    assert url and html


def test_check_update_silent_when_already_current(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.1.1")
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(_fake_release("v1.1.1")))
    assert updater.check_update("youtube-downloader") == (None, None, None, None)


def test_check_update_silent_when_remote_is_older(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.1.1")
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(_fake_release("v1.0.0")))
    assert updater.check_update("youtube-downloader") == (None, None, None, None)


def test_check_update_survives_network_failure(monkeypatch):
    """An offline user must not see a crash from a background update check."""
    def boom(*a, **k):
        raise OSError("network unreachable")
    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    assert updater.check_update("youtube-downloader") == (None, None, None, None)


def test_check_update_survives_malformed_json(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(b"not json"))
    assert updater.check_update("youtube-downloader") == (None, None, None, None)


# ── download ──────────────────────────────────────────────────────────────────

def test_download_file_writes_content_and_reports_progress(monkeypatch, tmp_path):
    payload = b"x" * 200_000
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(payload, {"Content-Length": str(len(payload))}))
    seen = []
    dest = tmp_path / "out.bin"
    updater.download_file("https://x/f", str(dest), progress_cb=seen.append)
    assert dest.read_bytes() == payload
    assert seen and seen[-1] == 100
    assert seen == sorted(seen), "progress must be monotonic"


def test_download_file_without_content_length_still_writes(monkeypatch, tmp_path):
    payload = b"y" * 1000
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(payload, {}))
    dest = tmp_path / "out.bin"
    updater.download_file("https://x/f", str(dest), progress_cb=lambda p: None)
    assert dest.read_bytes() == payload


# ── platform support gaps (documented, degrade gracefully) ───────────────────
# The build matrix publishes .deb/.dmg/-setup.exe for the GUI apps only. The TUI
# ships as .tar.gz/.exe, and Intel macOS is no longer built at all. In both cases
# _find_asset finds nothing — the app must still offer the release page rather
# than crash or silently do nothing.

def test_tui_has_no_matching_installer_asset_on_any_platform(monkeypatch):
    for plat, machine in [("linux", "x86_64"), ("darwin", "arm64"), ("win32", "AMD64")]:
        monkeypatch.setattr(updater.sys, "platform", plat)
        monkeypatch.setattr(updater.platform, "machine", lambda m=machine: m)
        assert updater._find_asset(REAL_RELEASE_ASSETS, "youtube-tui") == (None, None)


def test_intel_macos_has_no_asset_since_matrix_dropped_it(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "x86_64")
    assert updater._find_asset(REAL_RELEASE_ASSETS, "youtube-downloader") == (None, None)


def test_check_update_still_returns_tag_and_page_when_asset_missing(monkeypatch):
    """No asset must still yield tag + html_url so the UI can open the release page."""
    monkeypatch.setattr(updater, "__version__", "1.1.1")
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(_fake_release("v1.2.0")))
    tag, url, name, html = updater.check_update("youtube-downloader")
    assert tag == "v1.2.0"
    assert url is None and name is None
    assert html, "release page URL is the fallback path — it must be present"
