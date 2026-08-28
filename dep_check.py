"""Pre-flight dependency checker.

check_deps()  — pure stdlib + common, safe to call from any app.
DepDialog     — PyQt5 styled missing-dep dialog (GUI apps only).
"""

import sys
import importlib.util

from common import check_ffmpeg_available


def _install_cmd(binary: str) -> str:
    if sys.platform == 'darwin':
        return f'brew install {binary}'
    elif sys.platform == 'win32':
        return f'winget install {binary}'
    return f'sudo apt install {binary}'


def check_deps(check_qt_material: bool = False) -> list:
    """Return a list of {name, reason, cmd, required} dicts for missing deps.

    check_qt_material is retained for call compatibility; qt-material was
    dropped once theme.py covered styling, and it pulled in jinja2.
    """
    missing = []

    # find_spec() short-circuits on sys.modules and reads __spec__, which on a
    # LazyLoader module triggers the very import lazy_import deferred: 55 ms and
    # 68 submodules, paid right before the first window paint. Presence in
    # sys.modules already means importable — lazy_import only records it there
    # when find_spec succeeded.
    if 'yt_dlp' not in sys.modules and importlib.util.find_spec('yt_dlp') is None:
        missing.append({
            'name': 'yt-dlp',
            'reason': 'Core download engine — required for all downloads.',
            'cmd': 'pip install yt-dlp',
            'required': True,
        })

    if not check_ffmpeg_available():
        missing.append({
            'name': 'ffmpeg',
            'reason': 'Required for video merging and audio extraction.',
            'cmd': _install_cmd('ffmpeg'),
            'required': True,
        })

    return missing


# ── GUI dialog (only defined when PyQt5 is available) ─────────────────────────

try:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QPushButton, QApplication, QFrame,
    )
    from PyQt5.QtCore import Qt

    _BG     = '#0b0b14'
    _CARD   = '#17172e'
    _BORDER = '#252542'
    _TEXT   = '#e2e8ff'
    _MUTED  = '#6b6b9a'
    _ACCENT = '#6366f1'
    _ERROR  = '#f87171'
    _WARN   = '#fbbf24'

    _SS = f"""
        QDialog, QWidget {{ background: {_BG}; }}
        QLabel {{ color: {_TEXT}; background: transparent; }}
        QLabel#hdr  {{ font-size: 16px; font-weight: bold; }}
        QLabel#sub  {{ font-size: 12px; color: {_MUTED}; }}
        QLabel#dep-name {{ font-size: 13px; font-weight: bold; }}
        QLabel#dep-reason {{ font-size: 11px; color: {_MUTED}; }}
        QLabel#dep-cmd {{
            background: #07071a;
            color: #a5f3fc;
            font-family: monospace;
            font-size: 12px;
            padding: 6px 10px;
            border: 1px solid {_BORDER};
            border-radius: 6px;
        }}
        QPushButton {{
            background: {_CARD};
            border: 1px solid {_BORDER};
            border-radius: 8px;
            padding: 8px 16px;
            color: {_TEXT};
            font-size: 12px;
        }}
        QPushButton:hover {{ border-color: {_ACCENT}; }}
        QPushButton#copy-btn {{
            background: transparent;
            border: 1px solid {_BORDER};
            color: {_MUTED};
            padding: 4px 10px;
            font-size: 11px;
            min-width: 52px;
        }}
        QPushButton#copy-btn:hover {{ color: {_TEXT}; border-color: {_ACCENT}; }}
        QPushButton#quit-btn {{
            background: transparent;
            border: 1.5px solid #7f1d1d;
            color: {_ERROR};
            font-size: 13px;
            font-weight: bold;
            padding: 10px 28px;
            border-radius: 10px;
        }}
        QPushButton#quit-btn:hover {{ background: #2a1010; }}
        QPushButton#continue-btn {{
            background: {_ACCENT};
            border: none;
            color: #fff;
            font-size: 13px;
            font-weight: bold;
            padding: 10px 28px;
            border-radius: 10px;
        }}
        QPushButton#continue-btn:hover {{ background: #818cf8; }}
        QFrame#card {{
            background: {_CARD};
            border: 1px solid {_BORDER};
            border-radius: 12px;
        }}
        QFrame#divider {{ background: {_BORDER}; }}
    """

    class DepDialog(QDialog):
        """Styled dialog listing missing dependencies with copy-to-clipboard commands."""

        def __init__(self, missing: list, parent=None):
            super().__init__(parent)
            self.setWindowTitle('Missing Dependencies')
            self.setMinimumWidth(500)
            self.setStyleSheet(_SS)
            self._has_required = any(d['required'] for d in missing)
            self._build(missing)

        def _build(self, missing: list) -> None:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(24, 24, 24, 24)
            lay.setSpacing(14)

            hdr = QLabel('⚠  Missing Dependencies')
            hdr.setObjectName('hdr')
            lay.addWidget(hdr)

            if self._has_required:
                msg = ('The following required components are missing. '
                       'Install them and restart the app.')
            else:
                msg = ('Some optional components are missing. '
                       'You can continue with limited functionality.')
            sub = QLabel(msg)
            sub.setObjectName('sub')
            sub.setWordWrap(True)
            lay.addWidget(sub)

            div = QFrame()
            div.setObjectName('divider')
            div.setFixedHeight(1)
            lay.addWidget(div)

            for dep in missing:
                card = QFrame()
                card.setObjectName('card')
                cl = QVBoxLayout(card)
                cl.setContentsMargins(14, 12, 14, 12)
                cl.setSpacing(5)

                top = QHBoxLayout()
                nl = QLabel(dep['name'])
                nl.setObjectName('dep-name')
                nl.setStyleSheet(
                    f"color: {_ERROR if dep['required'] else _WARN};")
                top.addWidget(nl)
                badge = QLabel('required' if dep['required'] else 'optional')
                badge.setStyleSheet(
                    f"color: {_ERROR if dep['required'] else _WARN}; "
                    "font-size: 10px; letter-spacing: 1px;")
                top.addWidget(badge)
                top.addStretch()
                cl.addLayout(top)

                rl = QLabel(dep['reason'])
                rl.setObjectName('dep-reason')
                rl.setWordWrap(True)
                cl.addWidget(rl)

                cmd_row = QHBoxLayout()
                cmd_row.setSpacing(8)
                cl_lbl = QLabel(dep['cmd'])
                cl_lbl.setObjectName('dep-cmd')
                cmd_row.addWidget(cl_lbl, 1)

                copy_btn = QPushButton('Copy')
                copy_btn.setObjectName('copy-btn')
                copy_btn.setFixedWidth(56)

                def _make_copy(btn, text):
                    def _fn():
                        QApplication.clipboard().setText(text)
                        btn.setText('✓')
                    return _fn

                copy_btn.clicked.connect(_make_copy(copy_btn, dep['cmd']))
                cmd_row.addWidget(copy_btn)
                cl.addLayout(cmd_row)

                lay.addWidget(card)

            lay.addStretch()

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            if not self._has_required:
                cont = QPushButton('Continue anyway')
                cont.setObjectName('continue-btn')
                cont.clicked.connect(self.accept)
                btn_row.addWidget(cont)
            quit_btn = QPushButton('Quit')
            quit_btn.setObjectName('quit-btn')
            quit_btn.clicked.connect(self.reject)
            btn_row.addWidget(quit_btn)
            lay.addLayout(btn_row)

except ImportError:
    DepDialog = None  # PyQt5 not available (TUI context)
