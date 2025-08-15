import sys
import os
import yt_dlp
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QProgressBar, QComboBox, QFileDialog, QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread


class DownloadWorker(QObject):
    progress = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url, save_path, audio_format, audio_quality):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.audio_format = audio_format
        self.audio_quality = audio_quality

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed', 0)

                if total and speed:
                    percent = (downloaded / total) * 100
                    speed_mb = speed / 1024 / 1024  # Convert to MB/s
                    eta = d.get('eta', 0)

                    status_text = f"Speed: {speed_mb:.2f} MB/s | ETA: {eta} seconds"
                    self.status.emit(status_text)

                    progress_data = {
                        'percent': percent,
                        'filename': d.get('filename', ''),
                        'speed': speed_mb,
                        'eta': eta
                    }
                    self.progress.emit(progress_data)
            except Exception as e:
                self.error.emit(f"Error calculating progress: {str(e)}")

    def run(self):
        ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': self.audio_format,
                        'preferredquality': self.audio_quality,
                    }],
                    'progress_hooks': [self.progress_hook],
                    'quiet': True,
                    'noplaylist': False,  # Support playlists
                    'ignoreerrors': True,  # ✅ Skip unavailable/private videos and continue
                }

        try:
            self.status.emit(f"Downloading as {self.audio_format.upper()} ({self.audio_quality}kbps)...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class YoutubeDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Audio Downloader")
        self.setMinimumSize(600, 400)
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout()
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # YouTube URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel("YouTube Playlist URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube Playlist URL")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        main_layout.addLayout(url_layout)

        # Save Path
        save_layout = QHBoxLayout()
        save_label = QLabel("Save Location:")
        self.save_input = QLineEdit(str(Path.home() / "Downloads"))
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_location)
        save_layout.addWidget(save_label)
        save_layout.addWidget(self.save_input)
        save_layout.addWidget(browse_btn)
        main_layout.addLayout(save_layout)

        # Audio Format Selection
        format_layout = QHBoxLayout()
        format_label = QLabel("Audio Format:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp3", "aac", "m4a", "opus", "flac", "wav"])  # Supported formats
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        main_layout.addLayout(format_layout)

        # Audio Quality Selection
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality (kbps):")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["320", "256", "192", "128", "64"])  # Bitrate options
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.quality_combo)
        main_layout.addLayout(quality_layout)

        # Status Label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Download Button
        self.download_button = QPushButton("Download Audio")
        self.download_button.clicked.connect(self.handle_download_click)
        main_layout.addWidget(self.download_button)

        # Log Text
        log_label = QLabel("Download Log:")
        main_layout.addWidget(log_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        main_layout.addWidget(self.log_text)

    def browse_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Location", self.save_input.text())
        if directory:
            self.save_input.setText(directory)

    def handle_download_click(self):
        url = self.url_input.text().strip()
        if not url:
            self.log_text.append("Error: Please enter a YouTube playlist URL")
            return

        save_path = self.save_input.text().strip()
        audio_format = self.format_combo.currentText()  # Get selected format
        audio_quality = self.quality_combo.currentText()  # Get selected quality (bitrate)

        self.download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        # Create and setup worker thread
        self.thread = QThread()
        self.worker = DownloadWorker(url, save_path, audio_format, audio_quality)
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.download_complete)
        self.worker.error.connect(self.download_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.status.connect(self.update_status)

        # Start download
        self.log_text.append(f"Downloading playlist in {audio_format.upper()} ({audio_quality}kbps)...")
        self.thread.start()

    def update_progress(self, progress_data):
        self.progress_bar.setValue(int(progress_data['percent']))
        filename = os.path.basename(progress_data['filename'])
        self.log_text.append(
            f"Downloading: {filename}\n"
            f"Progress: {progress_data['percent']:.1f}%\n"
            f"Speed: {progress_data['speed']:.2f} MB/s\n"
            f"ETA: {progress_data['eta']} seconds\n"
        )

    def update_status(self, status):
        self.status_label.setText(status)

    def download_complete(self):
        self.thread.quit()
        self.thread.wait()
        self.download_button.setEnabled(True)
        self.status_label.setText("Download completed successfully!")
        self.log_text.append("Download completed successfully!")
        self.progress_bar.setValue(100)

    def download_error(self, error_msg):
        self.thread.quit()
        self.thread.wait()
        self.download_button.setEnabled(True)
        self.status_label.setText("Error occurred during download")
        self.log_text.append(f"Error: {error_msg}")
        self.progress_bar.setValue(0)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YoutubeDownloaderApp()
    window.show()
    sys.exit(app.exec_())
