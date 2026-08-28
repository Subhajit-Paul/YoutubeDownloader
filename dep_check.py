"""Pre-flight dependency checker.

check_deps()  — pure stdlib + common, safe to call from any app.
DepDialog     — PyQt5 styled missing-dep dialog (GUI apps only).
"""

import sys
import importlib.util

import theme as T
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

    # This dialog carried its own indigo palette, so the first thing a user with
    # no ffmpeg ever saw was a different product from the one behind it — and
    # its two secondary greys sat at 3.9:1 and 3.5:1, under WCAG AA. Colour
    # comes from the design system now, like everywhere else.
    _ERROR, _WARN = T.ERROR, T.WARNING

    _SS = f"""
        QDialog, QWidget {{ background: {T.BG}; }}
        QLabel {{ color: {T.TEXT}; background: transparent; }}
        QLabel#hdr  {{ font-size: 16px; font-weight: 600; }}
        QLabel#sub  {{ font-size: 12px; color: {T.MUTED}; }}
        QLabel#dep-name {{ font-size: 13px; font-weight: 600; }}
        QLabel#dep-reason {{ font-size: 11px; color: {T.MUTED}; }}
        QLabel#dep-cmd {{
            background: {T.SURFACE};
            color: {T.TEXT};
            font-family: {T.MONO_STACK};
            font-size: 12px;
            padding: 6px 10px;
            border: 1px solid {T.BORDER};
            border-radius: 6px;
        }}
        QPushButton {{
            background: {T.SURFACE};
            border: 1px solid {T.BORDER};
            border-radius: {T.RADIUS_CONTROL}px;
            padding: 8px 16px;
            color: {T.TEXT};
            font-size: 12px;
        }}
        QPushButton:hover {{ border-color: {T.ACCENT}; }}
        QPushButton:focus {{ border: 1px solid {T.ACCENT}; }}
        QPushButton#copy-btn {{
            background: transparent;
            border: 1px solid {T.BORDER};
            color: {T.MUTED};
            padding: 4px 10px;
            font-size: 11px;
            min-width: 52px;
        }}
        QPushButton#copy-btn:hover {{ color: {T.TEXT}; border-color: {T.BORDER_STRONG}; }}
        /* Quiet by default, red only on hover — the same rule the app's Cancel
           button follows, so a destructive-looking control means one thing. */
        QPushButton#quit-btn {{
            background: transparent;
            border: 1px solid {T.BORDER_STRONG};
            color: {T.MUTED};
            font-size: 13px;
            font-weight: 500;
            padding: 10px 28px;
            border-radius: {T.RADIUS_CONTROL}px;
        }}
        QPushButton#quit-btn:hover {{
            background: {T.CARD}; border-color: {T.ERROR}; color: {T.ERROR};
        }}
        QPushButton#continue-btn {{
            background: {T.ACCENT};
            border: none;
            color: {T.ON_ACCENT};
            font-size: 13px;
            font-weight: 600;
            padding: 10px 28px;
            border-radius: {T.RADIUS_CONTROL}px;
        }}
        QPushButton#continue-btn:hover {{ background: {T.ACCENT_HOVER}; }}
        QPushButton#continue-btn:pressed {{ background: {T.ACCENT_PRESSED}; }}
        QPushButton#continue-btn:focus {{ border: 2px solid {T.TEXT}; }}
        QFrame#card {{
            background: {T.CARD};
            border: 1px solid {T.BORDER};
            border-radius: {T.RADIUS_CARD}px;
        }}
        QFrame#divider {{ background: {T.BORDER}; }}
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
                copy_btn.setFixedWidth(78)
                copy_btn.setAccessibleName(f"Copy install command for {dep['name']}")

                def _make_copy(btn, text):
                    def _fn():
                        QApplication.clipboard().setText(text)
                        btn.setText('✓ Copied')
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
