import sys
import os
import shutil
import yt_dlp
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QComboBox,
    QFileDialog, QTextEdit, QFrame, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QFont, QIcon
from qt_material import apply_stylesheet


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_ffmpeg_location():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return None


def check_ffmpeg_available():
    if hasattr(sys, '_MEIPASS'):
        return any(
            os.path.exists(os.path.join(sys._MEIPASS, n))
            for n in ('ffmpeg', 'ffmpeg.exe')
        )
    return shutil.which('ffmpeg') is not None


# ── Download worker ────────────────────────────────────────────────────────────

class DownloadWorker(QObject):
    progress = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url, save_path, quality):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.quality = quality

    def progress_hook(self, d):
        if d['status'] != 'downloading':
            return
        try:
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed') or 0
            if total and speed:
                pct = (downloaded / total) * 100
                speed_mb = speed / 1_048_576
                eta = d.get('eta', 0)
                self.status.emit(f"{speed_mb:.1f} MB/s  ·  ETA {eta}s")
                self.progress.emit({
                    'percent': pct,
                    'filename': d.get('filename', ''),
                    'speed': speed_mb,
                    'eta': eta,
                })
        except Exception:
            pass

    def run(self):
        quality_map = {
            'Best':  'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '1080p': 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '720p':  'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '480p':  'bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
        }
        ydl_opts = {
            'format': quality_map[self.quality],
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook],
            'quiet': True,
        }
        loc = get_ffmpeg_location()
        if loc:
            ydl_opts['ffmpeg_location'] = loc
        try:
            self.status.emit('Starting download…')
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


# ── Main window ────────────────────────────────────────────────────────────────

class YoutubeDownloaderApp(QMainWindow):

    _STYLESHEET = """
        QMainWindow, QWidget#root { background-color: #121212; }

        QLabel#section { color: #9e9e9e; font-size: 11px; letter-spacing: 1px;
                         text-transform: uppercase; margin-top: 4px; }

        QLineEdit {
            background-color: #1e1e1e;
            border: 1px solid #2e2e2e;
            border-radius: 8px;
            padding: 10px 14px;
            color: #f0f0f0;
            font-size: 14px;
            selection-background-color: #2979ff;
        }
        QLineEdit:focus { border-color: #2979ff; }

        QComboBox {
            background-color: #1e1e1e;
            border: 1px solid #2e2e2e;
            border-radius: 8px;
            padding: 10px 14px;
            color: #f0f0f0;
            font-size: 14px;
        }
        QComboBox::drop-down { border: none; width: 28px; }
        QComboBox QAbstractItemView {
            background-color: #1e1e1e;
            color: #f0f0f0;
            selection-background-color: #2979ff;
            border: 1px solid #333;
        }

        QPushButton {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 10px 18px;
            color: #f0f0f0;
            font-size: 13px;
        }
        QPushButton:hover { background-color: #2a2a2a; border-color: #444; }
        QPushButton:pressed { background-color: #111; }

        QPushButton#primary {
            background-color: #2979ff;
            border: none;
            color: #fff;
            font-size: 15px;
            font-weight: bold;
            border-radius: 10px;
            padding: 14px;
        }
        QPushButton#primary:hover { background-color: #448aff; }
        QPushButton#primary:pressed { background-color: #1565c0; }
        QPushButton#primary:disabled { background-color: #1a2a4a; color: #555; }

        QProgressBar {
            background-color: #1e1e1e;
            border: none;
            border-radius: 4px;
            height: 6px;
        }
        QProgressBar::chunk { background-color: #2979ff; border-radius: 4px; }

        QTextEdit {
            background-color: #0d0d0d;
            color: #9e9e9e;
            border: 1px solid #1e1e1e;
            border-radius: 8px;
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
        }

        QFrame#divider { background-color: #222; max-height: 1px; }
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle('YouTube Downloader')
        self.setMinimumSize(640, 560)
        self.resize(720, 600)
        self.setWindowIcon(QIcon(resource_path('logo.png')))
        self.setStyleSheet(self._STYLESHEET)

        if not check_ffmpeg_available():
            QMessageBox.warning(self, 'ffmpeg Not Found',
                'ffmpeg is required for video merging but was not found.\n\n'
                '  • macOS:   brew install ffmpeg\n'
                '  • Linux:   sudo apt install ffmpeg\n'
                '  • Windows: https://ffmpeg.org/download.html')

        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = QLabel('YouTube Downloader')
        title.setFont(QFont('', 20, QFont.Bold))
        title.setStyleSheet('color: #ffffff;')
        header.addWidget(title)
        header.addStretch()
        from version import __version__
        badge = QLabel(f'v{__version__}')
        badge.setStyleSheet(
            'background:#1e1e1e; color:#555; border-radius:4px;'
            'padding:2px 8px; font-size:11px;')
        header.addWidget(badge)
        layout.addLayout(header)
        layout.addSpacing(16)

        divider = QFrame()
        divider.setObjectName('divider')
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addSpacing(20)

        # URL
        layout.addWidget(self._section_label('YouTube URL'))
        layout.addSpacing(6)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('https://youtube.com/watch?v=…')
        self.url_input.setMinimumHeight(44)
        url_row.addWidget(self.url_input)
        paste_btn = QPushButton('Paste')
        paste_btn.setFixedSize(72, 44)
        paste_btn.clicked.connect(
            lambda: self.url_input.setText(QApplication.clipboard().text()))
        url_row.addWidget(paste_btn)
        layout.addLayout(url_row)
        layout.addSpacing(16)

        # Save folder
        layout.addWidget(self._section_label('Save to'))
        layout.addSpacing(6)
        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.save_input = QLineEdit(str(Path.home() / 'Downloads'))
        self.save_input.setMinimumHeight(44)
        save_row.addWidget(self.save_input)
        browse_btn = QPushButton('Browse')
        browse_btn.setFixedSize(80, 44)
        browse_btn.clicked.connect(self._browse)
        save_row.addWidget(browse_btn)
        layout.addLayout(save_row)
        layout.addSpacing(16)

        # Quality
        layout.addWidget(self._section_label('Quality'))
        layout.addSpacing(6)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['Best', '1080p', '720p', '480p'])
        self.quality_combo.setMinimumHeight(44)
        layout.addWidget(self.quality_combo)
        layout.addSpacing(20)

        # Download button
        self.dl_btn = QPushButton('Download')
        self.dl_btn.setObjectName('primary')
        self.dl_btn.setMinimumHeight(52)
        self.dl_btn.clicked.connect(self._start_download)
        layout.addWidget(self.dl_btn)
        layout.addSpacing(16)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(6)

        stats_row = QHBoxLayout()
        self.status_label = QLabel('Ready')
        self.status_label.setStyleSheet('color: #555; font-size: 12px;')
        stats_row.addWidget(self.status_label)
        stats_row.addStretch()
        self.pct_label = QLabel('')
        self.pct_label.setStyleSheet('color: #555; font-size: 12px;')
        stats_row.addWidget(self.pct_label)
        layout.addLayout(stats_row)
        layout.addSpacing(12)

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(110)
        layout.addWidget(self.log_text)

    def _section_label(self, text):
        lbl = QLabel(text.upper())
        lbl.setObjectName('section')
        return lbl

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, 'Select folder', self.save_input.text())
        if d:
            self.save_input.setText(d)

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.log_text.append('⚠  Please enter a URL.')
            return
        self.dl_btn.setEnabled(False)
        self.dl_btn.setText('Downloading…')
        self.progress_bar.setValue(0)
        self.pct_label.setText('')
        self.status_label.setText('Starting…')
        self.status_label.setStyleSheet('color: #2979ff; font-size: 12px;')
        self.log_text.clear()

        self.thread = QThread()
        self.worker = DownloadWorker(
            url, self.save_input.text(), self.quality_combo.currentText())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(lambda s: self.status_label.setText(s))
        self.thread.start()

    def _on_progress(self, d):
        pct = int(d['percent'])
        self.progress_bar.setValue(pct)
        self.pct_label.setText(f'{pct}%')
        name = os.path.basename(d['filename'])
        if name:
            self.log_text.append(
                f"{name}  {pct}%  {d['speed']:.1f} MB/s  ETA {d['eta']}s")

    def _on_done(self):
        self.thread.quit(); self.thread.wait()
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText('Download')
        self.progress_bar.setValue(100)
        self.pct_label.setText('100%')
        self.status_label.setText('Done ✓')
        self.status_label.setStyleSheet('color: #00e676; font-size: 12px;')
        self.log_text.append('✓  Download complete')

    def _on_error(self, msg):
        self.thread.quit(); self.thread.wait()
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText('Download')
        self.progress_bar.setValue(0)
        self.pct_label.setText('')
        self.status_label.setText('Failed')
        self.status_label.setStyleSheet('color: #ff5252; font-size: 12px;')
        self.log_text.append(f'✗  {msg}')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme='dark_blue.xml', invert_secondary=True)
    window = YoutubeDownloaderApp()
    window.show()
    from update_ui import start_update_check
    QTimer.singleShot(3000, lambda: start_update_check(window, 'youtube-downloader'))
    sys.exit(app.exec_())
