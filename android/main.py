"""Android YouTube downloader — Kivy UI wrapping yt-dlp."""
import os
import threading
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import yt_dlp

SAVE_DIR = str(Path.home() / "Downloads" / "YouTubeDownloader")
FORMATS = ["mp3", "mp4", "m4a", "opus", "flac"]


class RootLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=10, **kwargs)
        os.makedirs(SAVE_DIR, exist_ok=True)
        self._format_idx = 0

        self.url_input = TextInput(
            hint_text="Paste YouTube URL or playlist URL here",
            multiline=False,
            size_hint_y=None,
            height=52,
        )
        self.add_widget(self.url_input)

        self.format_btn = Button(
            text=f"Format: {FORMATS[0].upper()}",
            size_hint_y=None,
            height=48,
            background_color=(0.16, 0.38, 1, 1),
        )
        self.format_btn.bind(on_press=self._cycle_format)
        self.add_widget(self.format_btn)

        self.status_label = Label(
            text="Enter a URL and tap Download",
            size_hint_y=None,
            height=36,
        )
        self.add_widget(self.status_label)

        self.progress_bar = ProgressBar(max=100, size_hint_y=None, height=24)
        self.add_widget(self.progress_bar)

        self.download_btn = Button(
            text="Download",
            size_hint_y=None,
            height=56,
            background_color=(0.16, 0.38, 1, 1),
        )
        self.download_btn.bind(on_press=self._start_download)
        self.add_widget(self.download_btn)

        scroll = ScrollView(size_hint=(1, 1))
        self.log_label = Label(
            text="",
            size_hint_y=None,
            markup=True,
            halign="left",
            valign="top",
        )
        self.log_label.bind(texture_size=self.log_label.setter("size"))
        scroll.add_widget(self.log_label)
        self.add_widget(scroll)

    def _cycle_format(self, _):
        self._format_idx = (self._format_idx + 1) % len(FORMATS)
        fmt = FORMATS[self._format_idx]
        self.format_btn.text = f"Format: {fmt.upper()}"

    def _start_download(self, _):
        url = self.url_input.text.strip()
        if not url:
            self._set_status("Please enter a URL first.")
            return
        self.download_btn.disabled = True
        self.progress_bar.value = 0
        self.log_label.text = ""
        fmt = FORMATS[self._format_idx]
        t = threading.Thread(target=self._download, args=(url, fmt), daemon=True)
        t.start()

    def _download(self, url, fmt):
        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    pct = downloaded / total * 100
                    Clock.schedule_once(lambda dt: setattr(self.progress_bar, "value", pct))
                    Clock.schedule_once(
                        lambda dt, p=pct: self._set_status(f"Downloading… {p:.0f}%")
                    )

        if fmt == "mp4":
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "outtmpl": os.path.join(SAVE_DIR, "%(title)s.%(ext)s"),
                "progress_hooks": [progress_hook],
                "quiet": True,
                "ignoreerrors": True,
            }
        else:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(SAVE_DIR, "%(title)s.%(ext)s"),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": fmt,
                        "preferredquality": "192",
                    }
                ],
                "progress_hooks": [progress_hook],
                "quiet": True,
                "ignoreerrors": True,
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            Clock.schedule_once(lambda dt: self._on_complete())
        except Exception as exc:
            Clock.schedule_once(lambda dt, e=str(exc): self._on_error(e))

    def _set_status(self, text):
        self.status_label.text = text

    def _append_log(self, text):
        self.log_label.text += text + "\n"

    def _on_complete(self):
        self.progress_bar.value = 100
        self._set_status("Download complete!")
        self._append_log(f"Saved to: {SAVE_DIR}")
        self.download_btn.disabled = False

    def _on_error(self, error):
        self._set_status("Error during download")
        self._append_log(f"[color=ff4444]Error: {error}[/color]")
        self.download_btn.disabled = False


class YouTubeDownloaderApp(App):
    def build(self):
        self.title = "YouTube Downloader"
        return RootLayout()


if __name__ == "__main__":
    YouTubeDownloaderApp().run()
