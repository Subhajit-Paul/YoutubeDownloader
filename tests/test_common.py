"""common.py — path and ffmpeg resolution, frozen (PyInstaller) and not."""
import os
import sys
import pathlib

import pytest

import common


def test_resource_path_unfrozen_is_relative_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert common.resource_path("logo.png") == os.path.join(str(tmp_path), "logo.png")


def test_resource_path_frozen_is_relative_to_meipass(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
    assert common.resource_path("logo.png") == os.path.join("/bundle", "logo.png")


def test_get_ffmpeg_location_none_when_unfrozen(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert common.get_ffmpeg_location() is None


def test_get_ffmpeg_location_is_meipass_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", "/bundle", raising=False)
    assert common.get_ffmpeg_location() == "/bundle"


@pytest.mark.parametrize("binary", ["ffmpeg", "ffmpeg.exe"])
def test_check_ffmpeg_available_frozen_finds_bundled_binary(monkeypatch, tmp_path, binary):
    (tmp_path / binary).write_text("")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert common.check_ffmpeg_available() is True


def test_check_ffmpeg_available_frozen_without_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert common.check_ffmpeg_available() is False


def test_check_ffmpeg_available_unfrozen_uses_path(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(common.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    assert common.check_ffmpeg_available() is True
    monkeypatch.setattr(common.shutil, "which", lambda n: None)
    assert common.check_ffmpeg_available() is False
