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

icon_file = 'logo.ico' if sys.platform == 'win32' and os.path.exists('logo.ico') else 'logo.png'

a = Analysis(
    ['ytd.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=[('logo.png', '.')],
    hiddenimports=[
        # yt-dlp reaches the app through common.lazy_import(), a runtime string
        # PyInstaller's static analysis cannot follow. It therefore stopped being
        # bundled and the shipped app reported it missing with downloads
        # disabled. Naming it here packages it; lazy_import still keeps it off
        # the startup path.
        'yt_dlp',
        'update_ui', 'updater', 'version', 'common', 'dep_check', 'theme',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'pydoc_data', 'test',
        # qt_material was dropped, and it dragged jinja2 in with it
        'qt_material', 'jinja2', 'markupsafe',
        # PyQt5 modules the apps never import
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebSockets', 'PyQt5.QtWebChannel', 'PyQt5.QtBluetooth',
        'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtLocation',
        'PyQt5.QtSerialPort', 'PyQt5.QtSql', 'PyQt5.QtTest',
        'PyQt5.QtDesigner', 'PyQt5.QtHelp', 'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets', 'PyQt5.QtOpenGL', 'PyQt5.QtXml',
        'PyQt5.QtXmlPatterns', 'PyQt5.QtSensors', 'PyQt5.QtRemoteObjects',
        'PyQt5.QtTextToSpeech', 'PyQt5.Qt3DCore', 'PyQt5.QtCharts',
    ],
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
        upx=False,
        console=False,
        argv_emulation=True,
        icon='logo.icns' if os.path.exists('logo.icns') else None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name='youtube-downloader',
    )
    app = BUNDLE(
        coll,
        name='YouTube Downloader.app',
        bundle_identifier='com.subhajitpaul.youtubedownloader',
        icon='logo.icns' if os.path.exists('logo.icns') else None,
        info_plist={
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '12.0',
        },
    )
else:
    # onedir: onefile re-extracts the entire archive on every launch.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='youtube-downloader',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name='youtube-downloader',
    )
