"""Qt update-checker worker and dialog — shared by both apps."""
import os
import sys
import tempfile
import threading
import webbrowser

from PyQt5.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

import updater
from version import __version__

_DIALOG_STYLE = """
    QDialog {
        background-color: #0f1117;
    }
    QLabel {
        color: #e0e0e0;
        font-size: 13px;
    }
    QLabel#title {
        color: #ffffff;
        font-size: 15px;
        font-weight: bold;
    }
    QLabel#meta {
        color: #777;
        font-size: 12px;
    }
    QLabel#status {
        color: #9e9e9e;
        font-size: 12px;
    }
    QProgressBar {
        background-color: #1a1a2e;
        border: none;
        border-radius: 4px;
        height: 6px;
    }
    QProgressBar::chunk {
        background-color: #00b0ff;
        border-radius: 4px;
    }
    QPushButton {
        background-color: #1a1a2e;
        border: 1px solid #2a2a3e;
        border-radius: 8px;
        padding: 9px 18px;
        color: #f0f0f0;
        font-size: 13px;
    }
    QPushButton:hover { background-color: #22223e; border-color: #444; }
    QPushButton:pressed { background-color: #111; }
    QPushButton#primary {
        background-color: #00838f;
        border: none;
        color: #fff;
        font-weight: bold;
    }
    QPushButton#primary:hover { background-color: #00acc1; }
    QPushButton#primary:pressed { background-color: #005662; }
    QPushButton#primary:disabled { background-color: #0a2a2e; color: #444; }
    QFrame#divider { background-color: #1e1e2e; max-height: 1px; }
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
        self._status.setStyleSheet("color: #00e676; font-size: 12px;")
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
        self._status.setStyleSheet("color: #ff5252; font-size: 12px;")
        self._status.setText("Download failed — opening release page.")
        webbrowser.open(self._html)
        self.reject()


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
