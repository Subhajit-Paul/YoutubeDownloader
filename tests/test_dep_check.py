"""dep_check.py — startup dependency detection and per-platform install hints."""
import pathlib

import pytest

import dep_check

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("platform,expected", [
    ("darwin", "brew install ffmpeg"),
    ("win32", "winget install ffmpeg"),
    ("linux", "sudo apt install ffmpeg"),
])
def test_install_cmd_per_platform(monkeypatch, platform, expected):
    monkeypatch.setattr(dep_check.sys, "platform", platform)
    assert dep_check._install_cmd("ffmpeg") == expected


def _fake_find_spec(present):
    return lambda name: object() if name in present else None


def test_no_missing_deps_when_everything_present(monkeypatch):
    monkeypatch.setattr(dep_check.importlib.util, "find_spec",
                        _fake_find_spec({"yt_dlp", "qt_material"}))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: True)
    assert dep_check.check_deps() == []


def test_missing_ytdlp_is_required(monkeypatch):
    monkeypatch.setattr(dep_check.importlib.util, "find_spec",
                        _fake_find_spec({"qt_material"}))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: True)
    missing = dep_check.check_deps()
    assert [d["name"] for d in missing] == ["yt-dlp"]
    assert missing[0]["required"] is True
    assert missing[0]["cmd"]


def test_missing_ffmpeg_is_required(monkeypatch):
    monkeypatch.setattr(dep_check.importlib.util, "find_spec",
                        _fake_find_spec({"yt_dlp", "qt_material"}))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: False)
    missing = dep_check.check_deps()
    assert [d["name"] for d in missing] == ["ffmpeg"]
    assert missing[0]["required"] is True


def test_qt_material_is_no_longer_a_dependency(monkeypatch):
    """theme.py covers styling; qt-material pulled jinja2 in for nothing."""
    monkeypatch.setattr(dep_check.importlib.util, "find_spec",
                        _fake_find_spec({"yt_dlp"}))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: True)
    assert dep_check.check_deps() == []
    assert "qt_material" not in (ROOT / "requirements.txt").read_text()


def test_tui_context_skips_qt_material(monkeypatch):
    """The TUI has no Qt — it must not be told to install a Qt theme."""
    monkeypatch.setattr(dep_check.importlib.util, "find_spec",
                        _fake_find_spec({"yt_dlp"}))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: True)
    assert dep_check.check_deps(check_qt_material=False) == []


def test_all_missing_reports_every_dep(monkeypatch):
    monkeypatch.setattr(dep_check.importlib.util, "find_spec", _fake_find_spec(set()))
    monkeypatch.setattr(dep_check, "check_ffmpeg_available", lambda: False)
    missing = dep_check.check_deps()
    assert {d["name"] for d in missing} == {"yt-dlp", "ffmpeg"}
    assert all(d.keys() >= {"name", "reason", "cmd", "required"} for d in missing)
