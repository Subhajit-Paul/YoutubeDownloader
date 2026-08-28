"""YouTube Downloader — Terminal UI powered by Textual."""

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from common import lazy_import

# Deferred: yt-dlp is ~64 ms of a ~120 ms cold start and is not touched until a
# download or metadata fetch begins.
yt_dlp = lazy_import("yt_dlp")
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Footer, Header, Input, Label,
    ProgressBar, RadioButton, RadioSet, RichLog, Select,
)

from common import get_ffmpeg_location
from version import __version__
import theme as T

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

# Metadata fetched for the preview card is reusable: pressing Download
# otherwise pays for a second full extraction, measured at 2.0 s on YouTube
# before a single byte moves. Format URLs carry a 6 h expiry, so this window
# leaves a wide margin; past it we simply extract again.
_INFO_MAX_AGE = 300  # seconds


def _download(ydl_opts, url, info, cancel=None):
    """Run the download, starting from cached info when we have it.

    download_with_info_file() is yt-dlp's own entry point for this, but its
    built-in recovery only fires on a raised DownloadError — and this app sets
    ignoreerrors, so a failure comes back as a non-zero retcode instead.
    Expired formats look exactly like that, so the retry is ours to make. It
    costs a wasted attempt only on a path that was already failing.
    """
    if not info:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.download([url])

    fd, path = tempfile.mkstemp(suffix=".info.json")
    os.close(fd)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            yt_dlp.utils.write_json_file(ydl.sanitize_info(info), path)
            retcode = ydl.download_with_info_file(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    if retcode and not (cancel and cancel.is_set()):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.download([url])
    return retcode


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

    CSS = f"""
    /* Tokens come from theme.py so the TUI, the video app and the audio app
       share one palette. Previously all three used different accents. */

    Screen {{ background: {T.BG}; color: {T.TEXT}; overflow: hidden; }}
    /* The default scrollbar gutter left an unstyled strip down the right edge
       that read as a rendering fault. */
    * {{ scrollbar-background: {T.BG}; scrollbar-color: {T.BORDER};
         scrollbar-background-hover: {T.BG}; scrollbar-color-hover: {T.BORDER_STRONG};
         scrollbar-size-vertical: 1; }}
    Header {{ background: {T.BG}; color: {T.TEXT}; text-style: bold; }}
    Footer {{ background: {T.SURFACE}; color: {T.MUTED}; }}
    Footer > .footer-key--key {{ background: {T.SURFACE}; color: {T.ACCENT}; }}

    /* ── Layout ──────────────────────────────────────────────────────────── */
    #body {{ padding: 1 3; height: 1fr; overflow: hidden; }}

    .row {{ height: 3; width: 100%; margin-bottom: 1; }}

    .field-label {{
        width: 9;
        color: {T.MUTED};
        content-align: right middle;
        padding-right: 2;
    }}

    #divider {{ height: 1; background: {T.BORDER}; margin-bottom: 1; }}

    /* Metadata card — the TUI previously showed nothing about the video before
       downloading, so it had no structural counterpart to the GUI card. */
    #meta-card {{
        display: none;
        height: auto;
        width: 100%;
        background: {T.CARD};
        border: tall {T.BORDER};
        padding: 0 2;
        margin-bottom: 1;
    }}
    #meta-card.visible {{ display: block; }}
    #meta-title {{ color: {T.TEXT}; text-style: bold; width: 100%; }}
    #meta-sub {{ color: {T.MUTED}; width: 100%; }}

    /* ── Inputs ──────────────────────────────────────────────────────────── */
    Input {{
        background: {T.SURFACE};
        border: tall {T.BORDER};
        color: {T.TEXT};
        width: 1fr;
    }}
    Input:focus {{ border: tall {T.ACCENT}; background: {T.CARD}; }}

    /* ── Mode + options ──────────────────────────────────────────────────── */
    /* height: auto and explicit widths — the selects were previously clipped
       off the right edge and never rendered at all. */
    #options-row {{ height: 3; width: 100%; margin-bottom: 1; }}

    RadioSet {{
        width: 26;
        height: 3;
        background: {T.SURFACE};
        border: tall {T.BORDER};
        padding: 0 1;
        layout: horizontal;
    }}
    RadioSet:focus {{ border: tall {T.ACCENT}; }}
    RadioButton {{ color: {T.MUTED}; background: transparent; width: 11; }}
    RadioButton.-on {{ color: {T.TEXT}; text-style: bold; }}
    RadioButton:focus {{ text-style: bold; }}

    Select {{ width: 18; margin-left: 1; }}
    Select > SelectCurrent {{
        background: {T.SURFACE};
        border: tall {T.BORDER};
        color: {T.TEXT};
    }}
    Select:focus > SelectCurrent {{ border: tall {T.ACCENT}; }}
    SelectOverlay {{
        background: {T.CARD};
        border: tall {T.BORDER_STRONG};
        color: {T.TEXT};
    }}
    SelectOverlay > .option-list--option-highlighted {{
        background: {T.ACCENT};
        color: {T.ON_ACCENT};
        text-style: bold;
    }}

    /* ── Actions ─────────────────────────────────────────────────────────── */
    /* One primary action. Everything else is quiet, so the eye has a single
       place to land. */
    #btn-row {{ height: 3; width: 100%; margin-bottom: 1; }}
    Button {{
        margin-right: 2;
        border: none;
        height: 3;
        background: {T.SURFACE};
        color: {T.MUTED};
    }}
    Button:hover {{ background: {T.ELEVATED}; color: {T.TEXT}; }}

    Button#download-btn {{
        background: {T.ACCENT};
        color: {T.ON_ACCENT};
        text-style: bold;
        width: 24;
    }}
    Button#download-btn:hover {{ background: {T.ACCENT_HOVER}; }}
    Button#download-btn:disabled {{ background: {T.SURFACE}; color: {T.FAINT}; }}

    Button#cancel-btn {{ width: 18; }}
    Button#cancel-btn:disabled {{ color: {T.FAINT}; }}
    Button#adv-btn {{ width: 20; }}
    Button#adv-btn.active {{ color: {T.ACCENT}; text-style: bold; }}
    Button#log-btn {{ width: 20; margin-right: 0; }}

    /* ── Advanced (hidden until asked for) ───────────────────────────────── */
    #adv-section {{ display: none; height: auto; margin-bottom: 1; }}
    #adv-section.adv-visible {{ display: block; }}
    #adv-row {{ height: 3; }}

    /* ── Progress ────────────────────────────────────────────────────────── */
    #progress-section {{ display: none; height: auto; margin-bottom: 1; }}
    #progress-section.active {{ display: block; }}
    #current-row {{ height: 1; }}
    #current-label {{ color: {T.TEXT}; width: 1fr; }}
    #speed-label {{ color: {T.MUTED}; width: 28; content-align: right middle; }}

    ProgressBar {{ height: 1; }}
    ProgressBar > Bar {{ width: 1fr; }}
    ProgressBar > Bar > .bar--bar {{ color: {T.ACCENT}; background: {T.SURFACE}; }}
    ProgressBar > Bar > .bar--complete {{ color: {T.SUCCESS}; }}

    #overall-bar {{ display: none; height: 1; }}
    #overall-bar.active {{ display: block; }}
    #overall-bar > Bar > .bar--bar {{ color: {T.MUTED}; background: {T.SURFACE}; }}
    #overall-bar > Bar > .bar--complete {{ color: {T.SUCCESS}; }}
    #overall-label {{ display: none; color: {T.MUTED}; height: 1; }}
    #overall-label.active {{ display: block; }}

    /* ── Log (opt-in) ────────────────────────────────────────────────────── */
    RichLog {{
        display: none;
        height: 1fr;
        min-height: 8;
        background: {T.SURFACE};
        border: tall {T.BORDER};
        color: {T.MUTED};
        padding: 0 1;
    }}
    RichLog.log-visible {{ display: block; }}

    /* ── Empty state ─────────────────────────────────────────────────────── */
    #empty {{ height: 1fr; width: 100%; content-align: center middle;
             text-align: center; color: {T.FAINT}; }}
    #empty.hidden {{ display: none; }}
    """

    BINDINGS = [
        Binding("ctrl+d", "download", "Download", priority=True),
        Binding("ctrl+x", "cancel_dl", "Cancel", priority=True),
        Binding("ctrl+l", "toggle_log", "Toggle log"),
        Binding("ctrl+a", "toggle_adv", "Advanced", priority=True),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._cancel_event = threading.Event()
        self._meta_timer = None
        self._completed = 0
        self._total = 0
        self._lock = threading.Lock()
        self._info = None
        self._info_url = None
        self._info_at = 0.0

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

            with Vertical(id="meta-card"):
                yield Label("", id="meta-title")
                yield Label("", id="meta-sub")

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

            yield Label(id="divider")

            with Vertical(id="progress-section"):
                with Horizontal(id="current-row"):
                    yield Label("", id="current-label")
                    yield Label("", id="speed-label")
                yield ProgressBar(total=100, id="file-bar", show_eta=False)
                yield Label("", id="overall-label")
                yield ProgressBar(total=100, id="overall-bar", show_eta=False)

            yield Label(
                "Paste a link above to begin\n"
                "Works with videos, playlists and channels",
                id="empty",
            )

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

    @on(Input.Changed, "#url-input")
    def on_url_changed(self, event: Input.Changed) -> None:
        if self._meta_timer is not None:
            self._meta_timer.stop()
        url = event.value.strip()
        if url != self._info_url:
            self._info = None
        if not url.startswith(("http://", "https://")):
            self.query_one("#meta-card").remove_class("visible")
            return
        # Debounced: fetching on every keystroke would hammer the extractor
        # while the user is still pasting.
        self._meta_timer = self.set_timer(0.6, lambda: self._fetch_meta(url))

    @work(thread=True, exclusive=True, group="meta")
    def _fetch_meta(self, url: str) -> None:
        if yt_dlp is None:
            return
        try:
            opts = {"quiet": True, "no_warnings": True,
                    "extract_flat": "in_playlist"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            return
        if not info:
            return
        if info.get("_type") == "playlist":
            # Playlist entries are flat stubs here and would be re-extracted
            # individually anyway, so there is nothing worth carrying forward.
            self._info = None
            entries = [e for e in (info.get("entries") or []) if e]
            count = info.get("playlist_count") or len(entries)
            sub = f"Playlist · {count} items"
        else:
            # Reused when Download is pressed, so the extraction just paid for
            # is not thrown away and repeated — 2.0 s on YouTube.
            self._info, self._info_url, self._info_at = info, url, time.monotonic()
            secs = info.get("duration") or 0
            mins, sec = divmod(int(secs), 60)
            hrs, mins = divmod(mins, 60)
            dur = f"{hrs}:{mins:02d}:{sec:02d}" if hrs else f"{mins}:{sec:02d}"
            channel = info.get("channel") or info.get("uploader") or ""
            sub = f"{channel} · {dur}" if channel else dur
        self.call_from_thread(self._ui_meta, info.get("title", ""), sub)

    def _ui_meta(self, title: str, sub: str) -> None:
        self.query_one("#meta-title", Label).update(title)
        self.query_one("#meta-sub", Label).update(sub)
        self.query_one("#meta-card").add_class("visible")
        self.query_one("#empty").add_class("hidden")

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
        self.query_one("#empty").add_class("hidden")

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

        info = None
        if (self._info_url == url
                and time.monotonic() - self._info_at < _INFO_MAX_AGE):
            info = self._info

        self._run_download(
            url, save_path, is_audio, quality, fmt, bitrate, browser,
            adv_frag, adv_buf, adv_chunk, adv_timeout, adv_aria2c, info,
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
        info: dict | None = None,
    ) -> None:
        cancel = self._cancel_event

        # Coalesced for the same reason as the GUI: call_from_thread per chunk
        # is more expensive than a Qt signal, and the terminal cannot show it.
        last_emit = [0.0]

        def progress_hook(d: dict) -> None:
            if cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled()
            if d["status"] != "downloading":
                return
            now = time.monotonic()
            if now - last_emit[0] < 0.08:
                return
            last_emit[0] = now
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
            "%(playlist_title&{}|)s/%(title)s.%(ext)s",
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
            # Textual captures stdout, so the downloader was rendering a
            # progress bar per chunk straight into a discarded buffer.
            "noprogress": True,
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
            retcode = _download(ydl_opts, url, info, cancel)
            if cancel.is_set():
                self.call_from_thread(self._ui_cancelled)
            elif retcode:
                # ignoreerrors keeps playlists going past a bad item, so yt-dlp
                # returns non-zero instead of raising. Without this the app
                # reports success for a download that produced no file.
                self.call_from_thread(
                    self._ui_error,
                    "Download finished with errors — some items may be missing.")
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
        # Deferred: updater pulls urllib.request (~10 ms of the import) and this
        # runs three seconds after the first paint.
        import updater
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
