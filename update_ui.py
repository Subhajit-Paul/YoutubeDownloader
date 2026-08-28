"""Qt update-checker worker and dialog — shared by both apps."""
import os
import sys
import tempfile
import threading
import webbrowser

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

import theme as T
import updater
from version import __version__

# This dialog was teal — a third palette in a product that had already agreed on
# one, so the update prompt read as another application's window appearing over
# yours. Its "You are running vX" line was also 4.2:1 and its disabled primary
# 1.6:1, both under WCAG AA.
_DIALOG_STYLE = f"""
    QDialog {{
        background-color: {T.BG};
    }}
    QLabel {{
        color: {T.TEXT};
        font-size: 13px;
    }}
    QLabel#title {{
        color: {T.TEXT};
        font-size: 15px;
        font-weight: 600;
    }}
    QLabel#meta {{
        color: {T.MUTED};
        font-size: 12px;
    }}
    QLabel#status {{
        color: {T.MUTED};
        font-size: 12px;
    }}
    QProgressBar {{
        background-color: {T.SURFACE};
        border: none;
        border-radius: 4px;
        height: 6px;
    }}
    QProgressBar::chunk {{
        background-color: {T.ACCENT};
        border-radius: 4px;
    }}
    QPushButton {{
        background-color: {T.SURFACE};
        border: 1px solid {T.BORDER};
        border-radius: {T.RADIUS_CONTROL}px;
        padding: 9px 18px;
        color: {T.TEXT};
        font-size: 13px;
    }}
    QPushButton:hover {{ background-color: {T.CARD}; border-color: {T.BORDER_STRONG}; }}
    QPushButton:pressed {{ background-color: {T.SURFACE}; }}
    QPushButton:focus {{ border: 1px solid {T.ACCENT}; }}
    QPushButton#primary {{
        background-color: {T.ACCENT};
        border: none;
        color: {T.ON_ACCENT};
        font-weight: 600;
    }}
    QPushButton#primary:hover {{ background-color: {T.ACCENT_HOVER}; }}
    QPushButton#primary:pressed {{ background-color: {T.ACCENT_PRESSED}; }}
    QPushButton#primary:disabled {{ background-color: {T.ACCENT_DIM}; color: {T.MUTED}; }}
    QPushButton#primary:focus {{ border: 2px solid {T.TEXT}; }}
    QFrame#divider {{ background-color: {T.BORDER}; max-height: 1px; }}
"""


class _Checker(QObject):
    found = pyqtSignal(str, str, str, str)  # tag, dl_url, asset_name, html_url

    def __init__(self, app_slug):
        super().__init__()
        self._slug = app_slug

    def run(self):
        tag, url, name, html = updater.check_update(self._slug)
        if tag:
            self.found.emit(tag, url or "", name or "", html or "")


class _DlSignals(QObject):
    progress = pyqtSignal(int)
    done = pyqtSignal(str)
    error = pyqtSignal(str)


class UpdateDialog(QDialog):
    def __init__(self, new_tag, dl_url, asset_name, html_url, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(460)
        self.setStyleSheet(_DIALOG_STYLE)
        self._dl_url = dl_url
        self._asset = asset_name
        self._html = html_url
        self._sigs = _DlSignals()
        self._sigs.progress.connect(self._on_progress)
        self._sigs.done.connect(self._on_done)
        self._sigs.error.connect(self._on_error)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        title = QLabel(f"New version available: {new_tag}")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addSpacing(6)

        meta = QLabel(f"You are running v{__version__}")
        meta.setObjectName("meta")
        layout.addWidget(meta)
        layout.addSpacing(16)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(16)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.hide()
        layout.addWidget(self._bar)
        layout.addSpacing(8)

        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.hide()
        layout.addWidget(self._status)
        layout.addSpacing(16)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._btn = QPushButton("Download && Install")
        self._btn.setObjectName("primary")
        self._btn.setMinimumHeight(40)
        self._btn.setDefault(True)
        self._btn.clicked.connect(self._start)
        row.addWidget(self._btn)
        later = QPushButton("Later")
        later.setMinimumHeight(40)
        later.clicked.connect(self.reject)
        row.addWidget(later)
        layout.addLayout(row)

    def _start(self):
        if not self._dl_url:
            webbrowser.open(self._html)
            self.accept()
            return
        self._btn.setEnabled(False)
        self._bar.show()
        self._status.show()
        self._status.setText("Starting download…")
        sigs, url, asset = self._sigs, self._dl_url, self._asset

        def _run():
            try:
                ext = os.path.splitext(asset)[1] if asset else ""
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext).name
                updater.download_file(url, tmp, lambda p: sigs.progress.emit(p))
                sigs.done.emit(tmp)
            except Exception as exc:
                sigs.error.emit(str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def _on_progress(self, pct):
        self._bar.setValue(pct)
        self._status.setText(f"Downloading… {pct}%")

    def _on_done(self, path):
        self._bar.setValue(100)
        self._status.setStyleSheet(f"color: {T.SUCCESS}; font-size: 12px;")
        updater.launch_installer(path)
        if sys.platform == "win32":
            self._status.setText("Installer running — close this app when prompted.")
        elif sys.platform == "darwin":
            self._status.setText("DMG opened — drag the app to Applications.")
        else:
            self._status.setText("Installer started.")
        self._btn.setText("Close")
        self._btn.setEnabled(True)
        self._btn.clicked.disconnect()
        self._btn.clicked.connect(self.accept)

    def _on_error(self, err):
        self._status.setStyleSheet(f"color: {T.ERROR}; font-size: 12px;")
        self._status.setText(
            "Couldn't download the update. Check your connection, or get it "
            "from the release page.")
        self._status.setWordWrap(True)
        self._status.show()
        self._bar.hide()
        # Was: report and reject() in the same breath, so the message never
        # stayed on screen, and a browser window opened without being asked for.
        self._btn.setEnabled(True)
        self._btn.setText("Open release page")
        self._btn.clicked.disconnect()
        self._btn.clicked.connect(self._open_release)

    def _open_release(self):
        webbrowser.open(self._html)
        self.accept()


def start_update_check(parent, app_slug):
    """Fire-and-forget background update check. Shows dialog if update found."""
    thread = QThread(parent)
    checker = _Checker(app_slug)
    checker.moveToThread(thread)
    thread.started.connect(checker.run)

    def _show(tag, url, name, html):
        dlg = UpdateDialog(tag, url, name, html, parent)
        dlg.exec_()
        thread.quit()
        thread.wait()

    checker.found.connect(_show)
    thread.finished.connect(thread.deleteLater)
    parent._upd_thread = thread
    parent._upd_checker = checker
    thread.start()
