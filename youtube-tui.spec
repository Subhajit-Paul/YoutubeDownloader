# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_all

ffmpeg_binaries = []
if sys.platform == "win32":
    if os.path.exists("ffmpeg.exe"):
        ffmpeg_binaries.append(("ffmpeg.exe", "."))
else:
    if os.path.exists("ffmpeg"):
        ffmpeg_binaries.append(("ffmpeg", "."))
    elif sys.platform == "darwin" and shutil.which("ffmpeg"):
        ffmpeg_binaries.append((shutil.which("ffmpeg"), "."))

_textual_datas, _textual_bins, _textual_hidden = collect_all("textual")
_rich_datas, _rich_bins, _rich_hidden = collect_all("rich")

a = Analysis(
    ["ytd_tui.py"],
    pathex=[],
    binaries=ffmpeg_binaries + _textual_bins + _rich_bins,
    datas=_textual_datas + _rich_datas + collect_data_files("textual", include_py_files=False),
    hiddenimports=(
        _textual_hidden + _rich_hidden +
        collect_submodules("textual") +
        ["common", "version", "updater", "dep_check", "theme"]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "tkinter", "unittest", "pydoc_data", "test",
              "qt_material", "jinja2", "markupsafe"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# onedir, not onefile: a onefile bootloader decompresses the whole archive to
# a temp directory on *every* launch. Measured on the shipped v1.3.0 TUI that
# cost 1298 ms to first paint; onedir is ~390 ms.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="youtube-tui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="youtube-tui",
)
