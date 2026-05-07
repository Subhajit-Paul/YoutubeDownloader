# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ffmpeg_binaries = []
if sys.platform == "win32":
    if os.path.exists("ffmpeg.exe"):
        ffmpeg_binaries.append(("ffmpeg.exe", "."))
else:
    if os.path.exists("ffmpeg"):
        ffmpeg_binaries.append(("ffmpeg", "."))
    elif sys.platform == "darwin" and shutil.which("ffmpeg"):
        ffmpeg_binaries.append((shutil.which("ffmpeg"), "."))

a = Analysis(
    ["ytd_tui.py"],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=(
        collect_data_files("textual") +
        collect_data_files("rich")
    ),
    hiddenimports=(
        collect_submodules("textual") +
        ["common", "version", "updater"]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="youtube-tui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
