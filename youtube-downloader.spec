# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sys

# Bundle ffmpeg if present in project root (downloaded by CI) or via which on macOS
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
    ['ytd.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=[('logo.png', '.'), ('version.py', '.'), ('updater.py', '.'), ('update_ui.py', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='youtube-downloader',
        debug=False,
        strip=False,
        upx=True,
        console=False,
        argv_emulation=True,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name='youtube-downloader',
    )
    app = BUNDLE(
        coll,
        name='YouTube Downloader.app',
        bundle_identifier='com.subhajitpaul.youtubedownloader',
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '12.0',
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='youtube-downloader',
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
        icon=['logo.png'],
    )
