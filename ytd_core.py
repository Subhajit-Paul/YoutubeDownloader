"""Everything the video and audio desktop apps share.

They are two products with genuinely different windows — audio carries format
and bitrate inside the info card, video a quality selector below it — but they
had grown 89% identical line for line, and the identical part was the engine:
the same workers, the same yt-dlp plumbing, the same stylesheet. Every fix down
there had to be made twice, and nothing but memory stopped one being missed.

What differs between the products stays in the products. What is the same is
here, once.
"""
import os
import shutil
import tempfile
import threading
import time

from common import lazy_import

# Deferred: yt-dlp is ~64 ms of a ~120 ms cold start and is not touched until a
# download or metadata fetch begins.
yt_dlp = lazy_import("yt_dlp")

from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QWidget,
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, QObject, QRectF, QPointF, QThread, QTimer,
)
from PyQt5.QtGui import (
    QFont, QIcon, QPainter, QPainterPath, QPixmap, QColor, QLinearGradient,
)

import theme as _T
from theme import (
    WARNING as _WARN, IDENTITY as _IDENTITY,
    ACCENT as _ACCENT, ACCENT_HOVER as _ACCENT_HOVER, ACCENT_DIM as _ACCENT_DIM,
    ACCENT_PRESSED as _ACCENT_PRESSED,
    BG as _BG, SURFACE as _SURFACE, CARD as _CARD, BORDER as _BORDER,
    BORDER_STRONG as _BORDER_STRONG, TEXT as _TEXT, MUTED as _MUTED,
    FAINT as _FAINT, ON_ACCENT as _ON_ACCENT,
    SUCCESS as _SUCCESS, ERROR as _ERROR,
    RADIUS_CONTROL as _R_CTL,
)
from common import get_ffmpeg_location, resource_path


# ── Options both apps offer ───────────────────────────────────────────────────

_BROWSERS = [
    'None', 'Chrome', 'Firefox', 'Brave', 'Safari',
    'Opera', 'Edge', 'Chromium', 'Vivaldi',
]
_BROWSER_KEY = {b: b.lower() for b in _BROWSERS if b != 'None'}

# Advanced performance options
_ADV_FRAGMENTS = [('1', 1), ('2', 2), ('4', 4), ('8', 8), ('12', 12), ('16', 16)]
_ADV_BUFSIZE   = [('256 KB', 256*1024), ('512 KB', 512*1024),
                  ('1 MB', 1024*1024), ('2 MB', 2*1024*1024), ('4 MB', 4*1024*1024)]
_ADV_CHUNK     = [('1 MB', 1024*1024), ('5 MB', 5*1024*1024),
                  ('10 MB', 10*1024*1024), ('25 MB', 25*1024*1024)]
_ADV_TIMEOUT   = [('10 s', 10), ('30 s', 30), ('60 s', 60)]
_ARIA2C_FOUND  = shutil.which('aria2c') is not None

_ADV_FRAG_DEFAULT    = 3   # index → 8
_ADV_BUFSIZE_DEFAULT = 2   # index → 1 MB
_ADV_CHUNK_DEFAULT   = 2   # index → 10 MB
_ADV_TIMEOUT_DEFAULT = 1   # index → 30 s


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_dur(secs):
    if not secs:
        return ''
    h, m, s = int(secs) // 3600, (int(secs) % 3600) // 60, int(secs) % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'



# ── Thumbnail widget ──────────────────────────────────────────────────────────

class ThumbWidget(QWidget):
    """Rounded thumbnail that reveals itself left-to-right as download progresses."""

    W, H, R = 200, 113, 10   # width, height, corner radius
    # Subclasses set these: the two apps differ only in the resting glyph
    # and the tint of the not-yet-downloaded overlay.
    GLYPH = '▶'
    OVERLAY = (10, 10, 20, 195)

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.W, self.H)
        self._pix = None
        self._pct = 0.0    # 0–100
        self._placeholder_text = self.GLYPH

    def setPixmap(self, pix: QPixmap):
        self._pix = pix
        self.update()

    def setProgress(self, pct: float):
        self._pct = pct
        self.update()

    def setPlaceholderText(self, t: str):
        self._placeholder_text = t
        self.update()

    def reset(self):
        self._pix = None
        self._pct = 0.0
        self._placeholder_text = self.GLYPH
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = QRectF(0, 0, self.W, self.H)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self.R, self.R)
        p.setClipPath(clip)

        if self._pix:
            # Scale to fill
            scaled = self._pix.scaled(
                self.W, self.H,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (self.W - scaled.width()) // 2
            y = (self.H - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)

            # Dark overlay on un-downloaded portion (reveals left→right)
            filled = self.W * self._pct / 100.0
            if filled < self.W:
                p.fillRect(
                    QRectF(filled, 0, self.W - filled, self.H),
                    QColor(*self.OVERLAY),
                )
                # Soft gradient seam
                if filled > 4:
                    grad = QLinearGradient(
                        QPointF(filled - 16, 0), QPointF(filled + 2, 0))
                    grad.setColorAt(0, QColor(0, 0, 0, 0))
                    grad.setColorAt(1, QColor(*self.OVERLAY))
                    p.fillRect(
                        QRectF(filled - 16, 0, 18, self.H), grad)
        else:
            p.fillRect(rect, QColor(_T.SURFACE))
            p.setPen(QColor(_T.FAINT))
            glyph_font = QFont(self.font())
            glyph_font.setPointSize(26)
            p.setFont(glyph_font)
            p.drawText(rect, Qt.AlignCenter, self._placeholder_text)

        p.end()



# ── Workers ───────────────────────────────────────────────────────────────────

class MetaWorker(QObject):
    ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            opts = {'quiet': True, 'no_warnings': True, 'extract_flat': 'in_playlist'}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if not info:
                self.failed.emit('Could not fetch video info.')
                return
            if info.get('_type') == 'playlist':
                entries = [e for e in (info.get('entries') or []) if e]
                count = info.get('playlist_count') or len(entries)
                first = entries[0] if entries else {}
                thumb = (info.get('thumbnail') or first.get('thumbnail') or
                         next((t['url'] for t in reversed(info.get('thumbnails') or [])
                               if t.get('url')), ''))
                self.ready.emit({
                    'title': info.get('title', 'Playlist'),
                    'channel': info.get('channel') or info.get('uploader', ''),
                    'duration': 0,
                    'thumbnail_url': thumb,
                    'is_playlist': True,
                    'count': count,
                })
            else:
                thumbs = info.get('thumbnails') or []
                thumb = (info.get('thumbnail') or
                         next((t['url'] for t in reversed(thumbs) if t.get('url')), ''))
                self.ready.emit({
                    '_info': info,
                    '_url': self.url,
                    '_fetched_at': time.monotonic(),
                    'title': info.get('title', ''),
                    'channel': info.get('channel') or info.get('uploader', ''),
                    'duration': info.get('duration', 0),
                    'thumbnail_url': thumb,
                    'is_playlist': False,
                    'count': 1,
                })
        except Exception as exc:
            self.failed.emit(str(exc).split('\n')[0][:120])


class ThumbnailFetcher(QObject):
    ready = pyqtSignal(bytes)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        # Deferred: urllib.request costs ~17 ms (it drags in http.client,
        # email.parser and ssl) and is not reached until metadata has arrived.
        import urllib.request
        try:
            req = urllib.request.Request(
                self.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.ready.emit(r.read())
        except Exception:
            pass

class BaseDownloadWorker(QObject):
    progress = pyqtSignal(dict)
    overall = pyqtSignal(int, int)
    postprocess = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url, save_path, browser='None',
                 concurrent_fragments=8, buffersize=1024*1024,
                 http_chunk_size=10*1024*1024, socket_timeout=30,
                 use_aria2c=False, info=None):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.browser = browser
        self.concurrent_fragments = concurrent_fragments
        self.buffersize = buffersize
        self.http_chunk_size = http_chunk_size
        self.socket_timeout = socket_timeout
        self.use_aria2c = use_aria2c
        self.info = info
        self._cancel = threading.Event()
        self._completed = 0
        self._total = 0
        self._lock = threading.Lock()
        self._last_emit = 0.0
        self._last_file = None

    def cancel(self):
        self._cancel.set()

    # yt-dlp calls this per chunk — hundreds of times a second on a fast link.
    # Emitting a Qt signal and repainting at that rate burns CPU that would
    # otherwise be moving bytes, and no display updates faster than ~60 Hz.
    _EMIT_INTERVAL = 0.08

    def progress_hook(self, d):
        if self._cancel.is_set():
            raise yt_dlp.utils.DownloadCancelled()
        if d['status'] != 'downloading':
            return
        try:
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed') or 0
            if not (total and speed):
                return
            pct = (downloaded / total) * 100

            # Throttle, but never swallow an update the user must see: the
            # final chunk (or the bar sticks below 100) and the first chunk of
            # a new file in a playlist.
            filename = d.get('filename', '')
            must_emit = pct >= 100 or filename != self._last_file
            now = time.monotonic()
            if not must_emit and now - self._last_emit < self._EMIT_INTERVAL:
                return
            self._last_emit = now
            self._last_file = filename
            speed_mb = speed / 1_048_576
            eta = d.get('eta', 0)
            playlist_count = d.get('playlist_count') or 0
            with self._lock:
                if playlist_count:
                    self._total = playlist_count
            self.progress.emit({
                'percent': pct,
                'filename': filename,
                'speed': speed_mb,
                'eta': eta,
                'playlist_index': d.get('playlist_index'),
                'playlist_count': playlist_count or self._total,
            })
        except yt_dlp.utils.DownloadCancelled:
            raise
        except Exception:
            pass

    def postprocessor_hook(self, d):
        if self._cancel.is_set():
            return
        info = d.get('info_dict', {})
        title = info.get('title', '')
        if d['status'] == 'started':
            self.postprocess.emit(f'Converting: {title}…')
        elif d['status'] == 'finished':
            self.postprocess.emit('')
            with self._lock:
                self._completed += 1
                done, total = self._completed, self._total
            if total:
                self.overall.emit(done, total)


    # Metadata fetched for the preview is reusable: clicking Download otherwise
    # pays for a second full extraction, measured at 2.0 s on YouTube before a
    # single byte moves. Format URLs carry a 6 h expiry, so this window has a
    # wide margin; past it, or for a playlist (whose entries are flat stubs and
    # would be re-extracted individually anyway), we simply extract afresh.
    INFO_MAX_AGE = 300  # seconds

    def _download(self, ydl_opts):
        """Run the download, starting from cached info when we have it.

        download_with_info_file() is yt-dlp's own entry point for this, but its
        built-in recovery only fires on a raised DownloadError — and this app
        sets ignoreerrors, so a failure comes back as a non-zero retcode
        instead. Expired formats look exactly like that, so the retry is ours
        to make: extract afresh rather than report a failure we can recover
        from. It costs a wasted attempt only on a path that was already failing.
        """
        if not self.info:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.download([self.url])

        fd, path = tempfile.mkstemp(suffix='.info.json')
        os.close(fd)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                yt_dlp.utils.write_json_file(ydl.sanitize_info(self.info), path)
                retcode = ydl.download_with_info_file(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        if retcode and not self._cancel.is_set():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.download([self.url])
        return retcode

    def media_opts(self):
        """The yt-dlp keys that decide what is produced — the whole difference
        between the two apps' downloads. Everything else below is identical."""
        raise NotImplementedError

    def run(self):
        archive = os.path.join(self.save_path, '.ytdl-archive')
        outtmpl = os.path.join(
            self.save_path,
            '%(playlist_title&{}|)s/%(title)s.%(ext)s',
        )
        ydl_opts = {
            **self.media_opts(),
            'outtmpl': outtmpl,
            'progress_hooks': [self.progress_hook],
            'postprocessor_hooks': [self.postprocessor_hook],
            'download_archive': archive,
            'continuedl': True,
            'concurrent_fragment_downloads': self.concurrent_fragments,
            'buffersize': self.buffersize,
            'http_chunk_size': self.http_chunk_size,
            'socket_timeout': self.socket_timeout,
            'retries': 10,
            'fragment_retries': 10,
            'ignoreerrors': True,
            'quiet': True,
            # quiet alone does not stop the downloader drawing a progress
            # bar: noprogress is its gate. No console reads it here (the
            # GUI has none, and a windowed Windows build has no stdout at
            # all), so it was terminal formatting done per chunk for nobody.
            'noprogress': True,
        }
        loc = get_ffmpeg_location()
        if loc:
            ydl_opts['ffmpeg_location'] = loc
        if self.browser and self.browser != 'None':
            ydl_opts['cookiesfrombrowser'] = (_BROWSER_KEY[self.browser],)
        if self.use_aria2c:
            ydl_opts['external_downloader'] = 'aria2c'
            ydl_opts['external_downloader_args'] = {
                'aria2c': ['-x', '16', '-s', '16', '-k', '1M', '--min-split-size=1M']
            }
        try:
            self.status.emit('Starting…')
            retcode = self._download(ydl_opts)
            if self._cancel.is_set():
                self.error.emit('cancelled')
            elif retcode:
                # ignoreerrors keeps playlists going past a bad item, so yt-dlp
                # returns non-zero instead of raising. Without this the app
                # reports success for a download that produced no file.
                self.error.emit('Download finished with errors — '
                                'some items may be missing.')
            else:
                self.finished.emit()
        except yt_dlp.utils.DownloadCancelled:
            self.error.emit('cancelled')
        except Exception as exc:
            self.error.emit(str(exc).split('\n')[0][:200])



def reusable_info(meta, url):
    """The info from the preview fetch, if it is safe to download from.

    Reusing it skips a second full extraction — 2.0 s on YouTube, paid after
    the user clicks Download and before any byte moves. It is only safe when
    it describes this exact URL, is a single video (playlist entries are flat
    stubs that get re-extracted individually anyway), and is recent enough that
    its format URLs cannot have expired; YouTube's carry a 6 h expiry, so the
    window below leaves a wide margin. Anything else returns None, which is
    exactly the behaviour this app had before.
    """
    if not meta or meta.get('_url') != url or meta.get('is_playlist'):
        return None
    if time.monotonic() - meta.get('_fetched_at', 0) >= BaseDownloadWorker.INFO_MAX_AGE:
        return None
    return meta.get('_info')



# ── Stylesheet ────────────────────────────────────────────────────────────────
# Shared by both windows. Each app appends its own rules after this string, so a
# later rule of equal specificity wins — which is how the two differ.

BASE_SS = f"""
        QMainWindow, QWidget#root {{ background: {_BG}; }}

        QLabel {{ color: {_TEXT}; }}
        QLabel#muted {{ color: {_MUTED}; font-size: 11px; }}
        QLabel#section {{
            color: {_MUTED}; font-size: 10px;
            letter-spacing: 1.5px; text-transform: uppercase;
        }}

        QLineEdit {{
            background: {_SURFACE};
            border: 1px solid {_BORDER};
            border-radius: {_R_CTL}px;
            padding: 12px 14px;
            color: {_TEXT};
            font-size: 14px;
            selection-background-color: {_ACCENT};
            selection-color: {_ON_ACCENT};
        }}
        QLineEdit:hover {{ border-color: {_BORDER_STRONG}; }}
        QLineEdit:focus {{ border: 1px solid {_ACCENT}; background: {_CARD}; }}

        QComboBox {{
            background: {_SURFACE};
            border: 1.5px solid {_BORDER};
            border-radius: 10px;
            padding: 11px 14px;
            color: {_TEXT};
            font-size: 14px;
        }}
        QComboBox::drop-down {{ border: none; width: 28px; }}
        QComboBox QAbstractItemView {{
            background: {_SURFACE};
            color: {_TEXT};
            selection-background-color: {_ACCENT};
            border: 1px solid {_BORDER};
        }}

        QPushButton {{
            background: {_SURFACE};
            border: 1.5px solid {_BORDER};
            border-radius: 10px;
            padding: 10px 18px;
            color: {_TEXT};
            font-size: 13px;
        }}
        QPushButton:hover {{ background: {_CARD}; border-color: {_ACCENT}; }}
        QPushButton:pressed {{ background: {_SURFACE}; }}

        QPushButton#primary {{
            background: {_ACCENT};
            border: none;
            color: #fff;
            font-size: 15px;
            font-weight: bold;
            border-radius: 12px;
            padding: 15px;
            letter-spacing: 0.5px;
        }}
        QPushButton#primary:hover {{ background: {_ACCENT_HOVER}; }}
        QPushButton#primary:pressed {{ background: {_ACCENT_PRESSED}; }}
        QPushButton#primary:disabled {{ background: {_ACCENT_DIM}; color: {_BORDER_STRONG}; }}

        /* Cancelling mid-download is routine, not destructive: a full-width
           red button made it the loudest thing on screen. Quiet by default,
           red only on hover, where intent is already expressed. */
        QPushButton#cancel {{
            background: transparent;
            border: 1px solid {_BORDER_STRONG};
            color: {_MUTED};
            font-size: 13px;
            font-weight: 500;
            border-radius: {_R_CTL}px;
            padding: 10px 18px;
        }}
        QPushButton#cancel:hover {{
            background: {_CARD}; border-color: {_ERROR}; color: {_ERROR};
        }}
        QPushButton#cancel:disabled {{
            border-color: {_BORDER}; color: {_FAINT};
        }}

        /* Secondary: present, but never competing with the primary action. */
        QPushButton#secondary {{
            background: {_SURFACE};
            border: 1px solid {_BORDER};
            color: {_MUTED};
            font-size: 13px;
            font-weight: 500;
            border-radius: {_R_CTL}px;
            padding: 0 14px;
        }}
        QPushButton#secondary:hover {{
            background: {_CARD}; border-color: {_BORDER_STRONG}; color: {_TEXT};
        }}
        QPushButton#secondary:pressed {{ background: {_SURFACE}; }}

        /* The bar carries the progress; the number annotates it. */
        QLabel#pct {{
            color: {_TEXT}; font-size: 15px; font-weight: 600;
            letter-spacing: -0.2px;
        }}

        QProgressBar {{
            background: {_SURFACE};
            border: none;
            border-radius: 3px;
            height: 5px;
        }}
        QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 3px; }}
        QProgressBar#overall::chunk {{ background: {_SUCCESS}; border-radius: 3px; }}

        QFrame#card {{
            background: {_CARD};
            border: 1px solid {_BORDER};
            border-radius: 14px;
        }}
        QFrame#divider {{ background: {_BORDER}; max-height: 1px; }}

        QPushButton#adv_toggle {{
            background: transparent;
            border: none;
            color: {_MUTED};
            font-size: 11px;
            text-align: left;
            padding: 2px 0;
        }}
        QPushButton#adv_toggle:hover {{ color: {_TEXT}; }}

        QCheckBox {{ color: {_MUTED}; font-size: 12px; spacing: 6px; }}
        QCheckBox:hover {{ color: {_TEXT}; }}
        QCheckBox::indicator {{
            width: 14px; height: 14px;
            border: 1.5px solid {_BORDER};
            border-radius: 3px;
            background: {_SURFACE};
        }}
        QCheckBox::indicator:checked {{
            background: {_ACCENT};
            border-color: {_ACCENT};
        }}

        QLabel#appname {{
            color: {_TEXT}; font-size: 15px; font-weight: 600;
            letter-spacing: -0.2px;
        }}
        QLabel#version {{ color: {_FAINT}; font-size: 11px; }}
        QLabel#empty_title {{
            color: {_MUTED}; font-size: 14px; font-weight: 500;
        }}
        QLabel#empty_body {{ color: {_FAINT}; font-size: 12px; }}

        QPushButton:focus {{
            border: 1px solid {_ACCENT};
        }}
        QPushButton#primary:focus {{
            border: 2px solid {_TEXT};
        }}
        QComboBox:focus {{ border-color: {_ACCENT}; }}
        QCheckBox:focus {{ color: {_TEXT}; }}
"""


# ── Window ────────────────────────────────────────────────────────────────────

class BaseWindow(QMainWindow):
    """The parts of the two windows that are the same window.

    Everything below is state and event handling — what happens when a URL is
    typed, metadata arrives, a download progresses, finishes or fails. None of
    it carries any design intent, and it was byte-identical in both apps.

    What the products genuinely differ in is declared as class attributes and
    in _build_ui(), which each app supplies for itself.
    """

    WINDOW_TITLE = 'YouTube Downloader'
    WINDOW_SIZE = (880, 640)
    IDENTITY_KEY = 'video'
    ITEM_NOUN = 'videos'            # how a playlist counts its contents
    FINALISING_LABEL = 'Finalising…'
    PCT_ACTIVE_STYLE = None         # audio tints the percentage while running

    def _build_ui(self):
        raise NotImplementedError

    def __init__(self):
            super().__init__()
            self.setWindowTitle(self.WINDOW_TITLE)
            self.setMinimumSize(720, 560)
            self.resize(*self.WINDOW_SIZE)
            self.setWindowIcon(QIcon(resource_path('logo.png')))
            _app = QApplication.instance()
            if _app is not None:
                _T.apply_font(_app)
            self.setStyleSheet(self._SS)

            self._meta = {}        # last fetched metadata dict
            self._fetch_timer = QTimer()
            self._fetch_timer.setSingleShot(True)
            self._fetch_timer.setInterval(1000)
            self._fetch_timer.timeout.connect(self._fetch_metadata)

            self._build_ui()

    def _lbl(self, text):
            l = QLabel(text.upper())
            l.setObjectName('section')
            return l

    def _toggle_advanced(self):
            if self.adv_panel.isVisible():
                self.adv_panel.hide()
                self.adv_btn.setText('▸  Advanced')
            else:
                self.adv_panel.show()
                self.adv_btn.setText('▾  Advanced')

    def _adv_opts(self):
            return dict(
                concurrent_fragments=_ADV_FRAGMENTS[self.adv_frag.currentIndex()][1],
                buffersize=_ADV_BUFSIZE[self.adv_buf.currentIndex()][1],
                http_chunk_size=_ADV_CHUNK[self.adv_chunk.currentIndex()][1],
                socket_timeout=_ADV_TIMEOUT[self.adv_timeout.currentIndex()][1],
                use_aria2c=self.adv_aria2c.isChecked(),
            )

    def _set_idle(self):
            self.empty.show()
            self.card.hide()
            self.controls.hide()
            self.dl_btn.hide()
            self.cancel_btn.hide()
            self.progress_widget.hide()
            self.overall_bar.hide()
            self.overall_label.hide()
            self._set_status('')

    def _set_fetching(self):
            self.empty.hide()
            self.card.hide()
            self.controls.hide()
            self.dl_btn.hide()
            self.cancel_btn.hide()
            self.progress_widget.hide()
            self._set_status('Fetching video info…', _MUTED)

    def _set_ready(self, meta: dict):
            self.empty.hide()
            self._meta = meta
            t = meta['title']
            self.title_label.setText(
                t if len(t) <= 52 else t[:50] + '…')
            self.channel_label.setText(meta.get('channel', ''))
            parts = []
            dur = fmt_dur(meta.get('duration', 0))
            if dur:
                parts.append(dur)
            if meta.get('is_playlist'):
                parts.append(f"{meta['count']} {self.ITEM_NOUN}")
            self.meta_label.setText('  ·  '.join(parts))
            self.thumb.reset()
            self.thumb.setPlaceholderText('⏳')
            self.card.show()
            self.controls.show()
            self.dl_btn.show()
            self.cancel_btn.hide()
            self.progress_widget.hide()
            self._set_status('Ready to download', _SUCCESS)

    def _set_downloading(self):
            self.empty.hide()
            self.controls.hide()
            self.dl_btn.hide()
            self.cancel_btn.show()
            self.cancel_btn.setEnabled(True)
            self.progress_widget.show()
            self.thumb.setProgress(0)
            self.pct_big.setText('0%')
            if self.PCT_ACTIVE_STYLE:
                self.pct_big.setStyleSheet(self.PCT_ACTIVE_STYLE)
            self.progress_bar.setValue(0)
            self.speed_label.setText('')

    def _set_status(self, text: str, color: str = _MUTED):
            self.status_label.setText(text)
            self.status_label.setStyleSheet(f'color: {color}; font-size: 11px;')

    def _on_url_changed(self, text: str):
            text = text.strip()
            if text.startswith(('http://', 'https://')):
                self._fetch_timer.start()
                self._set_fetching()
            else:
                self._fetch_timer.stop()
                self._set_idle()

    def _paste_and_fetch(self):
            self.url_input.setText(QApplication.clipboard().text())

    def _fetch_metadata(self):
            url = self.url_input.text().strip()
            if not url.startswith(('http://', 'https://')):
                return
            self._set_fetching()
            self._meta_thread = QThread()
            self._meta_worker = MetaWorker(url)
            self._meta_worker.moveToThread(self._meta_thread)
            self._meta_thread.started.connect(self._meta_worker.run)
            self._meta_worker.ready.connect(self._on_meta_ready)
            self._meta_worker.failed.connect(self._on_meta_failed)
            self._meta_worker.ready.connect(self._meta_thread.quit)
            self._meta_worker.failed.connect(self._meta_thread.quit)
            self._meta_thread.finished.connect(self._meta_thread.deleteLater)
            self._meta_thread.start()

    def _on_meta_ready(self, meta: dict):
            self._set_ready(meta)
            thumb_url = meta.get('thumbnail_url', '')
            if thumb_url:
                self._thumb_thread = QThread()
                self._thumb_worker = ThumbnailFetcher(thumb_url)
                self._thumb_worker.moveToThread(self._thumb_thread)
                self._thumb_thread.started.connect(self._thumb_worker.run)
                self._thumb_worker.ready.connect(self._on_thumb_ready)
                self._thumb_worker.ready.connect(self._thumb_thread.quit)
                self._thumb_thread.finished.connect(self._thumb_thread.deleteLater)
                self._thumb_thread.start()

    def _on_meta_failed(self, msg: str):
            self._set_status(f'⚠  {msg}', _ERROR)
            self.card.hide()
            self.controls.hide()
            self.dl_btn.hide()

    def _on_thumb_ready(self, data: bytes):
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull():
                self.thumb.setPixmap(pix)

    def _browse(self):
            d = QFileDialog.getExistingDirectory(
                self, 'Select folder', self.save_input.text())
            if d:
                self.save_input.setText(d)

    def _cancel_download(self):
            if hasattr(self, 'worker'):
                self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self._set_status('Cancelling…', _WARN)

    def _on_progress(self, d: dict):
            pct = d['percent']
            ipct = int(pct)
            # Animate toward the new value instead of snapping to it.
            self._bar_anim.stop()
            self._bar_anim.setStartValue(self.progress_bar.value())
            self._bar_anim.setEndValue(ipct)
            self._bar_anim.start()
            self.pct_big.setText(f'{ipct}%')
            self.thumb.setProgress(pct)

            speed = d['speed']
            eta = d['eta']
            idx = d.get('playlist_index')
            count = d.get('playlist_count')

            if idx and count:
                self.speed_label.setText(
                    f'{idx}/{count}  ·  {speed:.1f} MB/s  ·  ETA {eta}s')
            else:
                self.speed_label.setText(
                    f'{speed:.1f} MB/s  ·  ETA {eta}s')

    def _on_postprocess(self, msg: str):
            if msg:
                self._set_status(msg, _WARN)
            else:
                self._set_status(self.FINALISING_LABEL, _ACCENT)

    def _on_overall(self, done: int, total: int):
            self.overall_bar.setMaximum(total)
            self.overall_bar.setValue(done)
            self.overall_bar.show()
            self.overall_label.setText(f'Completed {done} of {total}')
            self.overall_label.show()

    def _on_done(self):
            self.thread.quit(); self.thread.wait()
            self.thumb.setProgress(100)
            self.progress_bar.setValue(100)
            self.pct_big.setText('✓')
            self.pct_big.setStyleSheet(f'color: {_SUCCESS}; font-size: 15px; font-weight: 600;')
            self.speed_label.setText('')
            self.cancel_btn.hide()
            self.controls.show()
            self.dl_btn.show()
            self._set_status('Download complete', _SUCCESS)

    def _on_error(self, msg: str):
            self.thread.quit(); self.thread.wait()
            self.cancel_btn.hide()
            self.controls.show()
            self.dl_btn.show()
            self.progress_widget.hide()
            if 'cancelled' in msg.lower():
                self._set_status('Download cancelled', _WARN)
            else:
                self._set_status(f'✗  {msg}', _ERROR)
