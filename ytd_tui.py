"""YouTube Downloader — Terminal UI powered by Textual."""

import os
import sys
import shutil
import threading
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    yt_dlp = None
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Footer, Header, Input, Label,
    ProgressBar, RadioButton, RadioSet, RichLog, Select,
)

from common import get_ffmpeg_location, check_ffmpeg_available
from version import __version__
import updater

# ── Constants ──────────────────────────────────────────────────────────────────

_QUALITY_OPTS = [
    ("Best", "Best"), ("1080p", "1080p"), ("720p", "720p"), ("480p", "480p"),
]
_FORMAT_OPTS = [(f, f) for f in ("mp3", "aac", "m4a", "opus", "flac", "wav")]
_BITRATE_OPTS = [(f"{b} kbps", b) for b in ("320", "256", "192", "128", "64")]
_BROWSER_OPTS = [
    ("No cookies", "none"),
    ("Chrome",     "chrome"),
    ("Firefox",    "firefox"),
    ("Brave",      "brave"),
    ("Safari",     "safari"),
    ("Opera",      "opera"),
    ("Edge",       "edge"),
    ("Chromium",   "chromium"),
    ("Vivaldi",    "vivaldi"),
]

_ADV_FRAG_OPTS    = [("1",  "1"), ("2", "2"), ("4", "4"), ("8", "8"),
                     ("12", "12"), ("16", "16")]
_ADV_BUF_OPTS     = [("256 KB", "262144"), ("512 KB", "524288"),
                     ("1 MB", "1048576"), ("2 MB", "2097152"), ("4 MB", "4194304")]
_ADV_CHUNK_OPTS   = [("1 MB", "1048576"), ("5 MB", "5242880"),
                     ("10 MB", "10485760"), ("25 MB", "26214400")]
_ADV_TIMEOUT_OPTS = [("10 s", "10"), ("30 s", "30"), ("60 s", "60")]
_ARIA2C_FOUND     = shutil.which("aria2c") is not None

_QUALITY_MAP = {
    "Best":  "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
    "1080p": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
    "720p":  "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
    "480p":  "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
}


# ── Application ────────────────────────────────────────────────────────────────

class YTDApp(App):
    """Combined video + audio YouTube downloader — Terminal UI."""

    TITLE = "YouTube Downloader TUI"
    SUB_TITLE = f"v{__version__}"

    CSS = """
    Screen { background: #0d0d0d; color: #e0e0e0; }
    Header { background: #1a1a2e; color: #ffffff; }
    Footer { background: #1a1a2e; }

    /* ── Layout ─────────────────────────────────────────── */
    #body { padding: 1 2; }

    .row {
        height: 3;
        margin-bottom: 1;
    }

    .field-label {
        width: 10;
        color: #555;
        content-align: right middle;
        padding-right: 1;
    }

    /* ── Inputs ─────────────────────────────────────────── */
    Input {
        background: #1e1e1e;
        border: tall #2e2e2e;
        color: #f0f0f0;
        width: 1fr;
    }
    Input:focus { border: tall #2979ff; }

    /* ── Mode radio ─────────────────────────────────────── */
    #options-row { height: 3; margin-bottom: 1; }

    RadioSet {
        background: transparent;
        border: none;
        width: auto;
        height: 3;
        margin-right: 2;
    }
    RadioButton { color: #555; }
    RadioButton:focus { color: #aaa; }
    RadioButton.-on { color: #ffffff; }

    /* ── Selects ─────────────────────────────────────────── */
    Select {
        background: #1e1e1e;
        border: tall #2e2e2e;
        color: #f0f0f0;
        width: 1fr;
    }
    Select:focus { border: tall #2979ff; }
    SelectOverlay {
        background: #1e1e1e;
        border: tall #333;
    }
    SelectOverlay > .option-list--option-highlighted {
        background: #2979ff;
    }

    /* ── Advanced section ───────────────────────────────── */
    #adv-section { display: none; height: auto; margin-bottom: 1; }
    #adv-section.adv-visible { display: block; }

    #adv-row { height: 3; margin-bottom: 1; }

    /* ── Buttons ─────────────────────────────────────────── */
    #btn-row { height: 3; margin-bottom: 1; }
    Button { margin-right: 1; }

    Button#download-btn {
        background: #2979ff;
        color: #ffffff;
        border: none;
        min-width: 26;
    }
    Button#download-btn:hover { background: #448aff; }
    Button#download-btn:disabled { background: #1a2a4a; color: #444; border: none; }

    Button#cancel-btn {
        background: #1e1e1e;
        border: tall #c62828;
        color: #ff5252;
        min-width: 22;
    }
    Button#cancel-btn:hover { background: #2a1010; }
    Button#cancel-btn:disabled { border: tall #333; color: #444; }

    Button#log-btn {
        background: #1e1e1e;
        border: tall #2e2e2e;
        color: #666;
        min-width: 22;
        margin-left: auto;
    }
    Button#log-btn:hover { background: #282828; color: #aaa; }

    Button#adv-btn {
        background: #1e1e1e;
        border: tall #2e2e2e;
        color: #555;
        min-width: 22;
    }
    Button#adv-btn:hover { background: #282828; color: #aaa; }
    Button#adv-btn.active { color: #aaa; border: tall #555; }

    /* ── Divider ─────────────────────────────────────────── */
    #divider {
        height: 1;
        background: #1e1e1e;
        margin-bottom: 1;
    }

    /* ── Progress section ────────────────────────────────── */
    #progress-section {
        height: auto;
        padding: 0 0 1 0;
        margin-bottom: 1;
        display: none;
    }
    #progress-section.active { display: block; }

    #current-row { height: 1; margin-bottom: 1; }
    #current-label { color: #aaa; width: 1fr; }
    #speed-label { color: #2979ff; width: auto; }

    ProgressBar { width: 100%; margin-bottom: 1; }
    ProgressBar > Bar > .bar--bar { color: #2979ff; }
    ProgressBar > Bar > .bar--complete { color: #2979ff; }

    #overall-bar { display: none; }
    #overall-bar.active { display: block; }
    #overall-bar > Bar > .bar--bar { color: #00e676; }
    #overall-bar > Bar > .bar--complete { color: #00e676; }

    #overall-label { color: #00e676; height: 1; display: none; }
    #overall-label.active { display: block; }

    /* ── Log ─────────────────────────────────────────────── */
    RichLog {
        border: solid #1e1e1e;
        background: #080808;
        padding: 0 1;
        display: none;
    }
    RichLog.log-visible { display: block; }
    """

    BINDINGS = [
        Binding("ctrl+d", "download", "Download", priority=True),
        Binding("ctrl+x", "cancel_dl", "Cancel", priority=True),
        Binding("ctrl+l", "toggle_log", "Toggle log"),
        Binding("ctrl+a", "toggle_adv", "Advanced"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._cancel_event = threading.Event()
        self._completed = 0
        self._total = 0
        self._lock = threading.Lock()

    # ── Compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical(id="body"):
            with Horizontal(classes="row"):
                yield Label("URL", classes="field-label")
                yield Input(
                    placeholder="https://youtube.com/watch?v=…  (or playlist / channel URL)",
                    id="url-input",
                )

            with Horizontal(classes="row"):
                yield Label("Save to", classes="field-label")
                yield Input(str(Path.home() / "Downloads"), id="save-input")

            with Horizontal(id="options-row"):
                with RadioSet(id="mode-radio"):
                    yield RadioButton("Video", value=True, id="rb-video")
                    yield RadioButton("Audio", id="rb-audio")
                yield Select(_QUALITY_OPTS, id="quality-select", value="Best")
                yield Select(_FORMAT_OPTS, id="format-select", value="mp3")
                yield Select(_BITRATE_OPTS, id="bitrate-select", value="320")
                yield Select(_BROWSER_OPTS, id="browser-select", value="none")

            with Vertical(id="adv-section"):
                with Horizontal(id="adv-row"):
                    yield Select(_ADV_FRAG_OPTS,    id="adv-frag",    value="8",       prompt="Fragments")
                    yield Select(_ADV_BUF_OPTS,     id="adv-buf",     value="1048576", prompt="Buffer")
                    yield Select(_ADV_CHUNK_OPTS,   id="adv-chunk",   value="10485760",prompt="Chunk size")
                    yield Select(_ADV_TIMEOUT_OPTS, id="adv-timeout", value="30",      prompt="Timeout")
                if _ARIA2C_FOUND:
                    yield Select(
                        [("aria2c off", "0"), ("aria2c on", "1")],
                        id="adv-aria2c", value="0", prompt="aria2c"
                    )

            with Horizontal(id="btn-row"):
                yield Button("Download  [ctrl+d]", id="download-btn")
                yield Button("Cancel  [ctrl+x]", id="cancel-btn", disabled=True)
                yield Button("Advanced  [ctrl+a]", id="adv-btn")
                yield Button("Show log  [ctrl+l]", id="log-btn", variant="default")

            Label(id="divider")

            with Vertical(id="progress-section"):
                with Horizontal(id="current-row"):
                    yield Label("", id="current-label")
                    yield Label("", id="speed-label")
                yield ProgressBar(total=100, id="file-bar", show_eta=False)
                yield Label("", id="overall-label")
                yield ProgressBar(total=100, id="overall-bar", show_eta=False)

            yield RichLog(id="log", highlight=True, markup=True, wrap=False)

        yield Footer()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.query_one("#format-select", Select).display = False
        self.query_one("#bitrate-select", Select).display = False
        self.query_one("#url-input", Input).focus()

        log = self.query_one("#log", RichLog)
        log.write(
            f"[bold white]YouTube Downloader TUI[/]  [dim]v{__version__}[/]  "
            "— downloads resume automatically via per-directory archive"
        )

        # ── Dependency checks ─────────────────────────────────────────────────
        from dep_check import check_deps
        issues = check_deps(check_qt_material=False)
        if issues:
            log.add_class("log-visible")
            self.query_one("#log-btn", Button).label = "Hide log  [ctrl+l]"
            log.write("")
            has_required = any(d['required'] for d in issues)
            if has_required:
                log.write("[bold red]✗  Missing required dependencies — downloads disabled.[/]")
            else:
                log.write("[bold yellow]⚠  Some optional dependencies are missing.[/]")
            for dep in issues:
                colour = "red" if dep['required'] else "yellow"
                log.write(
                    f"  [{colour}]{'✗' if dep['required'] else '⚠'}  {dep['name']}[/]  "
                    f"[dim]{dep['reason']}[/]"
                )
                log.write(
                    f"    Install:  [bold cyan]{dep['cmd']}[/]"
                )
            if has_required:
                self.query_one("#download-btn", Button).disabled = True

        self.set_timer(3.0, self._check_for_update)

    # ── Event handlers ───────────────────────────────────────────────────────

    @on(RadioSet.Changed, "#mode-radio")
    def on_mode_changed(self, event: RadioSet.Changed) -> None:
        is_audio = event.pressed.id == "rb-audio"
        self.query_one("#quality-select", Select).display = not is_audio
        self.query_one("#format-select", Select).display = is_audio
        self.query_one("#bitrate-select", Select).display = is_audio

    @on(Input.Submitted, "#url-input")
    def on_url_submitted(self, _) -> None:
        self.action_download()

    @on(Button.Pressed, "#download-btn")
    def on_download_pressed(self, _) -> None:
        self.action_download()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self, _) -> None:
        self.action_cancel_dl()

    @on(Button.Pressed, "#log-btn")
    def on_log_pressed(self, _) -> None:
        self.action_toggle_log()

    @on(Button.Pressed, "#adv-btn")
    def on_adv_pressed(self, _) -> None:
        self.action_toggle_adv()

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_download(self) -> None:
        url = self.query_one("#url-input", Input).value.strip()
        save_path = self.query_one("#save-input", Input).value.strip()
        log = self.query_one("#log", RichLog)

        if not url:
            log.write("[bold red]⚠[/]  Please enter a URL.")
            return
        if not url.startswith(("http://", "https://")):
            log.write("[bold red]⚠[/]  URL must start with http:// or https://")
            return
        if not save_path:
            log.write("[bold red]⚠[/]  Please enter a save path.")
            return

        is_audio = self.query_one("#mode-radio", RadioSet).pressed_index == 1
        quality = self._sel("#quality-select", "Best")
        fmt = self._sel("#format-select", "mp3")
        bitrate = self._sel("#bitrate-select", "320")
        browser = self._sel("#browser-select", "none")
        adv_frag    = int(self._sel("#adv-frag",    "8"))
        adv_buf     = int(self._sel("#adv-buf",     "1048576"))
        adv_chunk   = int(self._sel("#adv-chunk",   "10485760"))
        adv_timeout = int(self._sel("#adv-timeout", "30"))
        adv_aria2c  = _ARIA2C_FOUND and self._sel("#adv-aria2c", "0") == "1"

        self._cancel_event.clear()
        with self._lock:
            self._completed = 0
            self._total = 0

        self.query_one("#download-btn", Button).disabled = True
        self.query_one("#cancel-btn", Button).disabled = False
        self.query_one("#file-bar", ProgressBar).update(progress=0)
        self.query_one("#overall-bar", ProgressBar).update(progress=0)
        self.query_one("#overall-bar", ProgressBar).remove_class("active")
        self.query_one("#overall-label", Label).remove_class("active")
        self.query_one("#current-label", Label).update("")
        self.query_one("#speed-label", Label).update("")
        self.query_one("#progress-section").add_class("active")

        mode_str = "audio" if is_audio else "video"
        cookie_str = (
            f"  [dim]cookies from {browser}[/]" if browser != "none" else ""
        )
        log.write("")
        log.write(
            f"[bold]▶  Starting {mode_str} download[/]{cookie_str}  [dim]{url}[/]"
        )

        try:
            os.makedirs(save_path, exist_ok=True)
        except OSError as exc:
            log.write(f"[bold red]✗[/]  Cannot create save directory: {exc}")
            self._reset_ui()
            return

        self._run_download(
            url, save_path, is_audio, quality, fmt, bitrate, browser,
            adv_frag, adv_buf, adv_chunk, adv_timeout, adv_aria2c,
        )

    def action_cancel_dl(self) -> None:
        if self.query_one("#cancel-btn", Button).disabled:
            return
        self._cancel_event.set()
        self.query_one("#cancel-btn", Button).disabled = True
        self.query_one("#current-label", Label).update(
            "[yellow]Cancelling — waiting for current segment to finish…[/]"
        )
        self.query_one("#speed-label", Label).update("")

    def action_toggle_log(self) -> None:
        log = self.query_one("#log", RichLog)
        btn = self.query_one("#log-btn", Button)
        if "log-visible" in log.classes:
            log.remove_class("log-visible")
            btn.label = "Show log  [ctrl+l]"
        else:
            log.add_class("log-visible")
            btn.label = "Hide log  [ctrl+l]"

    def action_toggle_adv(self) -> None:
        sec = self.query_one("#adv-section")
        btn = self.query_one("#adv-btn", Button)
        if "adv-visible" in sec.classes:
            sec.remove_class("adv-visible")
            btn.label = "Advanced  [ctrl+a]"
            btn.remove_class("active")
        else:
            sec.add_class("adv-visible")
            btn.label = "Hide adv  [ctrl+a]"
            btn.add_class("active")

    # ── Download worker ──────────────────────────────────────────────────────

    def _sel(self, selector: str, default: str) -> str:
        val = self.query_one(selector, Select).value
        return default if val is Select.BLANK else str(val)

    @work(thread=True, exclusive=True, name="download")
    def _run_download(
        self,
        url: str,
        save_path: str,
        is_audio: bool,
        quality: str,
        fmt: str,
        bitrate: str,
        browser: str = "none",
        concurrent_fragments: int = 8,
        buffersize: int = 1024 * 1024,
        http_chunk_size: int = 10 * 1024 * 1024,
        socket_timeout: int = 30,
        use_aria2c: bool = False,
    ) -> None:
        cancel = self._cancel_event

        def progress_hook(d: dict) -> None:
            if cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            if d["status"] != "downloading":
                return
            try:
                total_b = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                if not (total_b and speed):
                    return
                pct = (downloaded / total_b) * 100
                speed_mb = speed / 1_048_576
                eta = d.get("eta", 0)
                playlist_count = d.get("playlist_count") or 0
                idx = d.get("playlist_index")
                with self._lock:
                    if playlist_count:
                        self._total = playlist_count
                filename = os.path.basename(d.get("filename", ""))
                self.call_from_thread(
                    self._ui_progress,
                    pct, filename, speed_mb, eta, idx,
                    playlist_count or self._total,
                )
            except yt_dlp.utils.DownloadCancelled:
                raise
            except Exception:
                pass

        def postprocessor_hook(d: dict) -> None:
            if cancel.is_set():
                return
            info = d.get("info_dict", {})
            title = info.get("title") or os.path.basename(
                info.get("filename", "unknown")
            )
            if d["status"] == "started":
                self.call_from_thread(self._ui_postprocessing, title)
            elif d["status"] == "finished":
                size = info.get("filesize") or info.get("filesize_approx") or 0
                size_str = f"{size / 1_048_576:.1f} MB" if size else ""
                self.call_from_thread(self._ui_file_done, title, size_str)
                with self._lock:
                    self._completed += 1
                    done, total = self._completed, self._total
                if total:
                    self.call_from_thread(self._ui_overall, done, total)

        archive = os.path.join(save_path, ".ytdl-archive")
        outtmpl = os.path.join(
            save_path,
            "%(playlist_title&%(playlist_title)s/|)s%(title)s.%(ext)s",
        )
        base_opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "download_archive": archive,
            "continuedl": True,
            "concurrent_fragment_downloads": concurrent_fragments,
            "buffersize": buffersize,
            "http_chunk_size": http_chunk_size,
            "socket_timeout": socket_timeout,
            "retries": 10,
            "fragment_retries": 10,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
        }
        loc = get_ffmpeg_location()
        if loc:
            base_opts["ffmpeg_location"] = loc
        if browser and browser != "none":
            base_opts["cookiesfrombrowser"] = (browser,)
        if use_aria2c:
            base_opts["external_downloader"] = "aria2c"
            base_opts["external_downloader_args"] = {
                "aria2c": ["-x", "16", "-s", "16", "-k", "1M", "--min-split-size=1M"]
            }

        if is_audio:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio/best",
                "noplaylist": False,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": fmt,
                    "preferredquality": bitrate,
                }],
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": _QUALITY_MAP.get(quality, _QUALITY_MAP["Best"]),
                "merge_output_format": "mp4",
            }

        if yt_dlp is None:
            self.call_from_thread(
                self._ui_error, "yt-dlp is not installed — run: pip install yt-dlp")
            return

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if cancel.is_set():
                self.call_from_thread(self._ui_cancelled)
            else:
                self.call_from_thread(self._ui_done)
        except yt_dlp.utils.DownloadCancelled:
            self.call_from_thread(self._ui_cancelled)
        except Exception as exc:
            self.call_from_thread(self._ui_error, str(exc))

    # ── UI update helpers (called from worker thread) ────────────────────────

    def _ui_progress(
        self,
        pct: float,
        filename: str,
        speed_mb: float,
        eta: int,
        idx,
        count,
    ) -> None:
        self.query_one("#file-bar", ProgressBar).update(progress=int(pct))
        playlist_tag = (
            f"  [dim]\\[{idx}/{count}][/]" if idx and count else ""
        )
        name_markup = (
            f"[bold white]{filename}[/]{playlist_tag}" if filename else "…"
        )
        self.query_one("#current-label", Label).update(name_markup)
        self.query_one("#speed-label", Label).update(
            f"[cyan]{speed_mb:.1f} MB/s[/]  [dim]ETA {eta}s  {int(pct)}%[/]"
        )

    def _ui_postprocessing(self, title: str) -> None:
        self.query_one("#current-label", Label).update(
            f"[yellow]Converting:[/] [bold]{title}[/]…"
        )
        self.query_one("#speed-label", Label).update("")

    def _ui_file_done(self, title: str, size_str: str) -> None:
        size_markup = f"  [dim]{size_str}[/]" if size_str else ""
        self.query_one("#log", RichLog).write(
            f"[bold green]✓[/]  {title}{size_markup}"
        )

    def _ui_overall(self, done: int, total: int) -> None:
        bar = self.query_one("#overall-bar", ProgressBar)
        lbl = self.query_one("#overall-label", Label)
        bar.update(total=total, progress=done)
        bar.add_class("active")
        lbl.update(f"[green]Completed {done} of {total}[/]")
        lbl.add_class("active")

    def _ui_done(self) -> None:
        self._reset_ui()
        self.query_one("#file-bar", ProgressBar).update(progress=100)
        self.query_one("#current-label", Label).update(
            "[bold green]✓  All downloads complete[/]"
        )
        self.query_one("#speed-label", Label).update("")
        self.query_one("#log", RichLog).write(
            "[bold green]✓  Session complete.[/]"
        )

    def _ui_cancelled(self) -> None:
        self._reset_ui()
        self.query_one("#current-label", Label).update(
            "[bold yellow]⊘  Cancelled[/]"
        )
        self.query_one("#speed-label", Label).update("")
        self.query_one("#log", RichLog).write("[yellow]⊘  Download cancelled.[/]")

    def _ui_error(self, msg: str) -> None:
        self._reset_ui()
        self.query_one("#current-label", Label).update("[bold red]✗  Error[/]")
        self.query_one("#speed-label", Label).update("")
        self.query_one("#log", RichLog).write(f"[bold red]✗[/]  {msg}")

    def _reset_ui(self) -> None:
        self.query_one("#download-btn", Button).disabled = False
        self.query_one("#cancel-btn", Button).disabled = True

    # ── Update check ─────────────────────────────────────────────────────────

    @work(thread=True, name="update-check")
    def _check_for_update(self) -> None:
        try:
            tag, _, _, html = updater.check_update("youtube-tui")
            if tag:
                self.call_from_thread(
                    self.notify,
                    f"Update available: {tag}  →  {html}",
                    severity="information",
                    timeout=12,
                )
        except Exception:
            pass


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = YTDApp()
    app.run()
