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

# (display label, is_video, yt-dlp format string, audio codec or None)
_FORMATS = [
    ("MP4 Best",  True,  "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",                      None),
    ("MP4 1080p", True,  "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",         None),
    ("MP4 720p",  True,  "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",          None),
    ("MP4 480p",  True,  "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",          None),
    ("MP3",       False, "bestaudio/best", "mp3"),
    ("M4A",       False, "bestaudio/best", "m4a"),
    ("OPUS",      False, "bestaudio/best", "opus"),
    ("FLAC",      False, "bestaudio/best", "flac"),
]

_LOG_MAX = 200
_BTN_BLUE = (0.16, 0.38, 1, 1)
_BTN_RED  = (0.55, 0.08, 0.08, 1)


class RootLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=16, spacing=8, **kwargs)
        os.makedirs(SAVE_DIR, exist_ok=True)

        self._fmt_idx = 0
        self._cancel_event = threading.Event()
        self._completed = 0
        self._total = 0
        self._lock = threading.Lock()
        self._log_lines = []

        # ── URL input ──────────────────────────────────────────────────────────
        self.url_input = TextInput(
            hint_text="Paste YouTube URL or playlist URL here",
            multiline=False,
            size_hint_y=None,
            height=52,
        )
        self.add_widget(self.url_input)

        # ── Format cycle button ────────────────────────────────────────────────
        self.format_btn = Button(
            text=f"Format: {_FORMATS[0][0]}",
            size_hint_y=None,
            height=48,
            background_color=_BTN_BLUE,
        )
        self.format_btn.bind(on_press=self._cycle_format)
        self.add_widget(self.format_btn)

        # ── Status label ───────────────────────────────────────────────────────
        self.status_label = Label(
            text="Enter a URL and tap Download",
            size_hint_y=None,
            height=36,
        )
        self.add_widget(self.status_label)

        # ── Per-file progress bar ──────────────────────────────────────────────
        self.progress_bar = ProgressBar(max=100, size_hint_y=None, height=20)
        self.add_widget(self.progress_bar)

        # ── Playlist progress bar (hidden until a playlist is detected) ────────
        self.playlist_bar = ProgressBar(max=100, size_hint_y=None, height=10)
        self.playlist_bar.opacity = 0
        self.add_widget(self.playlist_bar)

        self.playlist_label = Label(
            text="",
            size_hint_y=None,
            height=22,
            font_size=12,
        )
        self.add_widget(self.playlist_label)

        # ── Download / Cancel button ───────────────────────────────────────────
        self.action_btn = Button(
            text="Download",
            size_hint_y=None,
            height=56,
            background_color=_BTN_BLUE,
        )
        self.action_btn.bind(on_press=self._on_action)
        self.add_widget(self.action_btn)

        # ── Scrollable log ─────────────────────────────────────────────────────
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

    # ── Format cycling ─────────────────────────────────────────────────────────

    def _cycle_format(self, _):
        self._fmt_idx = (self._fmt_idx + 1) % len(_FORMATS)
        self.format_btn.text = f"Format: {_FORMATS[self._fmt_idx][0]}"

    # ── Download / Cancel button handler ───────────────────────────────────────

    def _on_action(self, _):
        if self.action_btn.text == "Cancel":
            self._cancel_event.set()
            self._set_status("Cancelling…")
            self.action_btn.disabled = True
            return

        url = self.url_input.text.strip()
        if not url.startswith(("http://", "https://")):
            self._set_status("Please enter a valid http/https URL.")
            return

        self._cancel_event.clear()
        with self._lock:
            self._completed = 0
            self._total = 0
        self._log_lines.clear()
        self.log_label.text = ""
        self.progress_bar.value = 0
        self.playlist_bar.value = 0
        self.playlist_bar.opacity = 0
        self.playlist_label.text = ""
        self.action_btn.text = "Cancel"
        self.action_btn.background_color = _BTN_RED
        self.format_btn.disabled = True
        self._set_status("Starting…")

        _, is_video, fmt, codec = _FORMATS[self._fmt_idx]
        threading.Thread(
            target=self._download, args=(url, is_video, fmt, codec), daemon=True
        ).start()

    # ── Download thread ────────────────────────────────────────────────────────

    def _download(self, url, is_video, fmt, codec):

        def progress_hook(d):
            if self._cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            if d["status"] != "downloading":
                return
            try:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                eta = d.get("eta", 0)
                playlist_count = d.get("playlist_count") or 0
                with self._lock:
                    if playlist_count:
                        self._total = playlist_count
                if not (total and speed):
                    return
                pct = downloaded / total * 100
                speed_mb = speed / 1_048_576
                idx = d.get("playlist_index")
                count = playlist_count or self._total

                def _update(dt, p=pct, s=speed_mb, e=eta, i=idx, c=count):
                    self.progress_bar.value = p
                    if i and c:
                        self._set_status(
                            f"Downloading {i}/{c}  ·  {s:.1f} MB/s  ·  ETA {e}s")
                    else:
                        self._set_status(f"Downloading…  {s:.1f} MB/s  ·  ETA {e}s")

                Clock.schedule_once(_update)
            except yt_dlp.utils.DownloadCancelled:
                raise
            except Exception:
                pass

        def postprocessor_hook(d):
            if self._cancel_event.is_set():
                return
            info = d.get("info_dict", {})
            title = info.get("title", "")
            if d["status"] == "started":
                Clock.schedule_once(
                    lambda dt, t=title: self._set_status(f"Converting: {t}…"))
            elif d["status"] == "finished":
                with self._lock:
                    self._completed += 1
                    done, total = self._completed, self._total

                def _upd(dt, dn=done, tot=total):
                    if tot:
                        self.playlist_bar.max = tot
                        self.playlist_bar.value = dn
                        self.playlist_bar.opacity = 1
                        self.playlist_label.text = f"Completed {dn} of {tot}"

                Clock.schedule_once(_upd)

        archive = os.path.join(SAVE_DIR, ".ytdl-archive")
        outtmpl = os.path.join(
            SAVE_DIR,
            "%(playlist_title&%(playlist_title)s/|)s%(title)s.%(ext)s",
        )
        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "download_archive": archive,
            "continuedl": True,
            "concurrent_fragment_downloads": 4,
            "retries": 10,
            "fragment_retries": 10,
            "ignoreerrors": True,
            "quiet": True,
        }
        if is_video:
            ydl_opts["merge_output_format"] = "mp4"
        elif codec:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": "192",
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if self._cancel_event.is_set():
                Clock.schedule_once(lambda dt: self._on_cancelled())
            else:
                Clock.schedule_once(lambda dt: self._on_complete())
        except yt_dlp.utils.DownloadCancelled:
            Clock.schedule_once(lambda dt: self._on_cancelled())
        except Exception as exc:
            Clock.schedule_once(
                lambda dt, e=str(exc).split("\n")[0][:200]: self._on_error(e))

    # ── UI helpers ─────────────────────────────────────────────────────────────

    def _set_status(self, text):
        self.status_label.text = text

    def _append_log(self, text):
        self._log_lines.append(text)
        if len(self._log_lines) > _LOG_MAX:
            self._log_lines.pop(0)
        self.log_label.text = "\n".join(self._log_lines)

    def _reset_btn(self):
        self.action_btn.text = "Download"
        self.action_btn.background_color = _BTN_BLUE
        self.action_btn.disabled = False
        self.format_btn.disabled = False

    # ── Completion callbacks (main thread via Clock) ────────────────────────────

    def _on_complete(self):
        self.progress_bar.value = 100
        self._set_status("Download complete!")
        self._append_log(f"Saved to: {SAVE_DIR}")
        self._reset_btn()

    def _on_cancelled(self):
        self._set_status("Download cancelled.")
        self._append_log("[color=fbbf24]Cancelled by user.[/color]")
        self._reset_btn()

    def _on_error(self, error):
        self._set_status("Error during download")
        self._append_log(f"[color=ff4444]Error: {error}[/color]")
        self._reset_btn()


class YouTubeDownloaderApp(App):
    def build(self):
        self.title = "YouTube Downloader"
        return RootLayout()


if __name__ == "__main__":
    YouTubeDownloaderApp().run()
