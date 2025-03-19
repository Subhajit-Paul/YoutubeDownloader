import sys
import os
import webbrowser
import yt_dlp
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QProgressBar, QComboBox, QFileDialog, QTextEdit,
    QFrame, QGraphicsOpacityEffect, QDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPixmap, QDesktopServices

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

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
        if d['status'] == 'downloading':
            # Calculate download speed and progress
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
        quality_map = {
            "Highest": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "1080p": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "720p": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "480p": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]"
        }
        
        ydl_opts = {
            'format': quality_map[self.quality],
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook],
            'quiet': True,
        }
        
        try:
            self.status.emit("Starting download...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class YoutubeDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.setMinimumSize(900, 600)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
            QLineEdit, QComboBox {
                background-color: #2c2c2c;
                border: 1px solid #333333;
                border-radius: 5px;
                padding: 8px;
                color: #e0e0e0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #2962ff;
                border-radius: 5px;
                padding: 10px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0039cb;
            }
            QPushButton:pressed {
                background-color: #001f80;
            }
            QProgressBar {
                background-color: #2c2c2c;
                border: 1px solid #333333;
                border-radius: 5px;
                height: 20px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2962ff;
                border-radius: 5px;
            }
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #333333;
                border-radius: 5px;
                padding: 10px;
                font-family: monospace;
                font-size: 13px;
            }
        """)
        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout()
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # App Logo
        logo_label = QLabel()
        pixmap = QPixmap(resource_path("logo.png"))
        logo_label.setPixmap(pixmap.scaled(620, 620, Qt.KeepAspectRatio))
        logo_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(logo_label)

        # URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel("YouTube URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL")
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

        # Quality Selection
        quality_layout = QHBoxLayout()
        quality_label = QLabel("Quality:")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Highest", "1080p", "720p", "480p"])
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
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.handle_download_click)
        main_layout.addWidget(self.download_button)

        # Log Text
        log_label = QLabel("Download Log:")
        main_layout.addWidget(log_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(150)
        main_layout.addWidget(self.log_text)

        # About Button
        self.about_button = QPushButton("About")
        self.about_button.clicked.connect(self.toggle_about_panel)
        main_layout.addWidget(self.about_button)

        # About Panel
        self.about_panel = QWidget()
        self.about_panel.setFixedWidth(300)
        self.about_panel.setStyleSheet("background-color: #1e1e1e; padding: 15px;")
        about_layout = QVBoxLayout(self.about_panel)
        
        about_text = QLabel("""
            <b>YouTube Downloader</b><br>
            <i>Developed by <a href='https://github.com/Subhajit-Paul' style='color:#2962ff;'>Subhajit Paul</a></i><br><br>
            📧 Email: <a href='mailto:test.dev.paul@gmail.com' style='color:#2962ff;'>test.dev.paul@gmail.com</a><br>
            🔗 <a href='https://in.linkedin.com/in/stochasticgradientdescent' style='color:#2962ff;'>LinkedIn Profile</a>
        """)
        about_text.setOpenExternalLinks(True)
        about_layout.addWidget(about_text)
        self.about_panel.setLayout(about_layout)
        self.about_panel.hide()
        main_layout.addWidget(self.about_panel)

    def browse_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Location", self.save_input.text())
        if directory:
            self.save_input.setText(directory)

    def handle_download_click(self):
        url = self.url_input.text().strip()
        if not url:
            self.log_text.append("Error: Please enter a YouTube URL")
            return
        
        save_path = self.save_input.text().strip()
        self.download_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        # Create and setup worker thread
        self.thread = QThread()
        self.worker = DownloadWorker(url, save_path, self.quality_combo.currentText())
        self.worker.moveToThread(self.thread)
        
        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.download_complete)
        self.worker.error.connect(self.download_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.status.connect(self.update_status)
        
        # Start download
        self.log_text.append("Starting download...")
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

    def toggle_about_panel(self):
        if self.about_panel.isVisible():
            self.about_panel.hide()
        else:
            self.about_panel.show()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YoutubeDownloaderApp()
    window.show()
    sys.exit(app.exec_())