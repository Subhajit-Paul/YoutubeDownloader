"""Qt update-checker worker and dialog — shared by both apps."""
import os
import sys
import tempfile
import threading
import webbrowser

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

import updater
from version import __version__


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
        self.setMinimumWidth(420)
        self._dl_url = dl_url
        self._asset = asset_name
        self._html = html_url
        self._sigs = _DlSignals()
        self._sigs.progress.connect(self._on_progress)
        self._sigs.done.connect(self._on_done)
        self._sigs.error.connect(self._on_error)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>New version available: {new_tag}</b>"))
        layout.addWidget(QLabel(f"You are running: {__version__}"))

        self._bar = QProgressBar()
        self._bar.hide()
        layout.addWidget(self._bar)

        self._status = QLabel("")
        layout.addWidget(self._status)

        row = QHBoxLayout()
        self._btn = QPushButton("Download && Install")
        self._btn.clicked.connect(self._start)
        row.addWidget(self._btn)
        later = QPushButton("Later")
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
        sigs, url, asset = self._sigs, self._dl_url, self._asset

        def _run():
            try:
                ext = os.path.splitext(asset)[1] if asset else ""
                tmp = tempfile.mktemp(suffix=ext)
                updater.download_file(url, tmp, lambda p: sigs.progress.emit(p))
                sigs.done.emit(tmp)
            except Exception as exc:
                sigs.error.emit(str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def _on_progress(self, pct):
        self._bar.setValue(pct)
        self._status.setText(f"Downloading… {pct}%")

    def _on_done(self, path):
        self._status.setText("Launching installer…")
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
        self._status.setText("Download failed — opening browser.")
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
    # Keep references so GC doesn't collect them
    parent._upd_thread = thread
    parent._upd_checker = checker
    thread.start()
