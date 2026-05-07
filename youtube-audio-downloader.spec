# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_data_files

ffmpeg_binaries = []
if sys.platform == 'win32':
    if os.path.exists('ffmpeg.exe'):
        ffmpeg_binaries.append(('ffmpeg.exe', '.'))
else:
    if os.path.exists('ffmpeg'):
        ffmpeg_binaries.append(('ffmpeg', '.'))
    elif sys.platform == 'darwin' and shutil.which('ffmpeg'):
        ffmpeg_binaries.append((shutil.which('ffmpeg'), '.'))

icon_file = 'logo.ico' if sys.platform == 'win32' and os.path.exists('logo.ico') else 'logo.png'

a = Analysis(
    ['ytd_audio.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=collect_data_files('qt_material') + [('logo.png', '.')],
    hiddenimports=['update_ui', 'updater', 'version', 'common', 'qt_material', 'dep_check'],
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
        name='youtube-audio-downloader',
        debug=False,
        strip=False,
        upx=True,
        console=False,
        argv_emulation=True,
        icon='logo.icns' if os.path.exists('logo.icns') else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name='youtube-audio-downloader',
    )
    app = BUNDLE(
        coll,
        name='YouTube Audio Downloader.app',
        bundle_identifier='com.subhajitpaul.youtubeaudiodownloader',
        icon='logo.icns' if os.path.exists('logo.icns') else None,
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
        icon=icon_file,
    )
