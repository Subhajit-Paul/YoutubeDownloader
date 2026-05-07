# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sys

# Bundle ffmpeg if it exists in the project root (placed there by CI) or found via which
ffmpeg_binaries = []
if sys.platform == 'win32':
    if os.path.exists('ffmpeg.exe'):
        ffmpeg_binaries.append(('ffmpeg.exe', '.'))
else:
    if os.path.exists('ffmpeg'):
        ffmpeg_binaries.append(('ffmpeg', '.'))
    elif sys.platform == 'darwin' and shutil.which('ffmpeg'):
        ffmpeg_binaries.append((shutil.which('ffmpeg'), '.'))

a = Analysis(
    ['ytd_audio.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='youtube-audio-downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
