import sys
import os
import shutil
import threading
import urllib.request
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QComboBox,
    QFileDialog, QFrame, QMessageBox, QSizePolicy, QGraphicsDropShadowEffect,
    QCheckBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QRectF, QPointF
from PyQt5.QtGui import (
    QFont, QIcon, QPainter, QPainterPath, QPixmap, QColor,
    QLinearGradient, QPen,
)
try:
    from qt_material import apply_stylesheet
except ImportError:
    def apply_stylesheet(*a, **kw): pass

from common import resource_path, get_ffmpeg_location, check_ffmpeg_available
from version import __version__
from update_ui import start_update_check


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_dur(secs):
    if not secs:
        return ''
    h, m, s = int(secs) // 3600, (int(secs) % 3600) // 60, int(secs) % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


# ── Thumbnail widget ────────────────────────────────────────────────────────────

class _ThumbWidget(QWidget):
    """Rounded thumbnail that reveals itself left-to-right as download progresses."""

    W, H, R = 200, 113, 10   # width, height, corner radius

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.W, self.H)
        self._pix = None
        self._pct = 0.0    # 0–100
        self._placeholder_text = '▶'

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
        self._placeholder_text = '▶'
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
                    QColor(10, 10, 20, 195),
                )
                # Soft gradient seam
                if filled > 4:
                    grad = QLinearGradient(
                        QPointF(filled - 16, 0), QPointF(filled + 2, 0))
                    grad.setColorAt(0, QColor(0, 0, 0, 0))
                    grad.setColorAt(1, QColor(10, 10, 20, 195))
                    p.fillRect(
                        QRectF(filled - 16, 0, 18, self.H), grad)
        else:
            p.fillRect(rect, QColor('#0d0d20'))
            p.setPen(QColor('#2a2a4a'))
            p.setFont(QFont('', 26))
            p.drawText(rect, Qt.AlignCenter, self._placeholder_text)

        p.end()


# ── Workers ────────────────────────────────────────────────────────────────────

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
        try:
            req = urllib.request.Request(
                self.url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.ready.emit(r.read())
        except Exception:
            pass


class DownloadWorker(QObject):
    progress = pyqtSignal(dict)
    overall = pyqtSignal(int, int)
    postprocess = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url, save_path, quality, browser='None',
                 concurrent_fragments=8, buffersize=1024*1024,
                 http_chunk_size=10*1024*1024, socket_timeout=30,
                 use_aria2c=False):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.quality = quality
        self.browser = browser
        self.concurrent_fragments = concurrent_fragments
        self.buffersize = buffersize
        self.http_chunk_size = http_chunk_size
        self.socket_timeout = socket_timeout
        self.use_aria2c = use_aria2c
        self._cancel = threading.Event()
        self._completed = 0
        self._total = 0
        self._lock = threading.Lock()

    def cancel(self):
        self._cancel.set()

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
            speed_mb = speed / 1_048_576
            eta = d.get('eta', 0)
            playlist_count = d.get('playlist_count') or 0
            with self._lock:
                if playlist_count:
                    self._total = playlist_count
            self.progress.emit({
                'percent': pct,
                'filename': d.get('filename', ''),
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

    def run(self):
        quality_map = {
            'Best':  'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '1080p': 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '720p':  'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
            '480p':  'bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
        }
        archive = os.path.join(self.save_path, '.ytdl-archive')
        outtmpl = os.path.join(
            self.save_path,
            '%(playlist_title&{}|)s/%(title)s.%(ext)s',
        )
        ydl_opts = {
            'format': quality_map.get(self.quality, quality_map['Best']),
            'merge_output_format': 'mp4',
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                retcode = ydl.download([self.url])
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


# ── Main window ────────────────────────────────────────────────────────────────

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

_ACCENT = '#6366f1'
_ACCENT_HOVER = '#818cf8'
_ACCENT_DIM = '#1e1e4a'
_BG = '#0b0b14'
_SURFACE = '#13132a'
_CARD = '#17172e'
_BORDER = '#252542'
_TEXT = '#e2e8ff'
_MUTED = '#6b6b9a'
_SUCCESS = '#34d399'
_ERROR = '#f87171'
_WARN = '#fbbf24'


class YoutubeDownloaderApp(QMainWindow):

    _SS = f"""
        QMainWindow, QWidget#root {{ background: {_BG}; }}

        QLabel {{ color: {_TEXT}; }}
        QLabel#muted {{ color: {_MUTED}; font-size: 11px; }}
        QLabel#section {{
            color: {_MUTED}; font-size: 10px;
            letter-spacing: 1.5px; text-transform: uppercase;
        }}

        QLineEdit {{
            background: {_SURFACE};
            border: 1.5px solid {_BORDER};
            border-radius: 10px;
            padding: 11px 14px;
            color: {_TEXT};
            font-size: 14px;
            selection-background-color: {_ACCENT};
        }}
        QLineEdit:focus {{ border-color: {_ACCENT}; }}

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
        QPushButton:hover {{ background: #1e1e38; border-color: {_ACCENT}; }}
        QPushButton:pressed {{ background: #0d0d20; }}

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
        QPushButton#primary:pressed {{ background: #4338ca; }}
        QPushButton#primary:disabled {{ background: {_ACCENT_DIM}; color: #3a3a6a; }}

        QPushButton#cancel {{
            background: transparent;
            border: 1.5px solid #7f1d1d;
            color: {_ERROR};
            font-size: 14px;
            font-weight: bold;
            border-radius: 12px;
            padding: 13px;
        }}
        QPushButton#cancel:hover {{ background: #2a1010; border-color: {_ERROR}; }}
        QPushButton#cancel:disabled {{ border-color: #333; color: #555; }}

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
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle('YouTube Downloader')
        self.setMinimumSize(660, 480)
        self.resize(720, 540)
        self.setWindowIcon(QIcon(resource_path('logo.png')))
        self.setStyleSheet(self._SS)

        self._meta = {}        # last fetched metadata dict
        self._fetch_timer = QTimer()
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.setInterval(1000)
        self._fetch_timer.timeout.connect(self._fetch_metadata)

        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(0)

        # ── Logo banner ──────────────────────────────────────────────────────
        logo_pix = QPixmap(resource_path('logo.png'))
        logo_label = QLabel()
        logo_label.setPixmap(
            logo_pix.scaledToHeight(44, Qt.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        ver = QLabel(f'v{__version__}')
        ver.setObjectName('muted')
        ver.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        hdr = QHBoxLayout()
        hdr.addWidget(logo_label)
        hdr.addStretch()
        hdr.addWidget(ver)
        layout.addLayout(hdr)
        layout.addSpacing(18)

        div0 = QFrame(); div0.setObjectName('divider'); div0.setFixedHeight(1)
        layout.addWidget(div0)
        layout.addSpacing(20)

        # ── URL input ────────────────────────────────────────────────────────
        layout.addWidget(self._lbl('YouTube URL'))
        layout.addSpacing(6)
        url_row = QHBoxLayout(); url_row.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('Paste a video, playlist, or channel URL…')
        self.url_input.setMinimumHeight(46)
        self.url_input.textChanged.connect(self._on_url_changed)
        url_row.addWidget(self.url_input)
        paste_btn = QPushButton('Paste')
        paste_btn.setFixedSize(72, 46)
        paste_btn.clicked.connect(self._paste_and_fetch)
        url_row.addWidget(paste_btn)
        layout.addLayout(url_row)
        layout.addSpacing(14)

        # ── Fetch / status message ───────────────────────────────────────────
        self.status_label = QLabel('')
        self.status_label.setObjectName('muted')
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setFixedHeight(18)
        layout.addWidget(self.status_label)
        layout.addSpacing(8)

        # ── Info card ────────────────────────────────────────────────────────
        self.card = QFrame()
        self.card.setObjectName('card')
        self.card.hide()

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 14, 20, 14)
        card_layout.setSpacing(16)

        self.thumb = _ThumbWidget()
        card_layout.addWidget(self.thumb)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)
        meta_col.setContentsMargins(0, 4, 0, 4)

        self.title_label = QLabel('')
        self.title_label.setFont(QFont('', 14, QFont.Bold))
        self.title_label.setWordWrap(False)
        self.title_label.setStyleSheet(f'color: {_TEXT};')
        meta_col.addWidget(self.title_label)

        self.channel_label = QLabel('')
        self.channel_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        meta_col.addWidget(self.channel_label)

        self.meta_label = QLabel('')
        self.meta_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        meta_col.addWidget(self.meta_label)

        meta_col.addStretch()

        # Speed / ETA (shown during download, inside the card)
        self.speed_label = QLabel('')
        self.speed_label.setStyleSheet(
            f'color: {_ACCENT}; font-size: 12px; font-weight: bold;')
        meta_col.addWidget(self.speed_label)

        card_layout.addLayout(meta_col)
        layout.addWidget(self.card)
        layout.addSpacing(16)

        # ── Controls (save path + quality) ───────────────────────────────────
        self.controls = QWidget()
        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(10)

        ctrl_layout.addWidget(self._lbl('Save to'))
        save_row = QHBoxLayout(); save_row.setSpacing(8)
        self.save_input = QLineEdit(str(Path.home() / 'Downloads'))
        self.save_input.setMinimumHeight(44)
        save_row.addWidget(self.save_input)
        browse_btn = QPushButton('Browse')
        browse_btn.setFixedSize(80, 44)
        browse_btn.clicked.connect(self._browse)
        save_row.addWidget(browse_btn)
        ctrl_layout.addLayout(save_row)

        # Quality + browser cookies on one row
        qb_row = QHBoxLayout(); qb_row.setSpacing(12)

        qual_col = QVBoxLayout(); qual_col.setSpacing(6)
        qual_col.addWidget(self._lbl('Quality'))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['Best', '1080p', '720p', '480p'])
        self.quality_combo.setMinimumHeight(44)
        qual_col.addWidget(self.quality_combo)
        qb_row.addLayout(qual_col)

        browser_col = QVBoxLayout(); browser_col.setSpacing(6)
        browser_col.addWidget(self._lbl('Cookies from browser'))
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(_BROWSERS)
        self.browser_combo.setMinimumHeight(44)
        browser_col.addWidget(self.browser_combo)
        qb_row.addLayout(browser_col)

        ctrl_layout.addLayout(qb_row)

        # ── Advanced toggle ───────────────────────────────────────────────────
        self.adv_btn = QPushButton('▸  Advanced')
        self.adv_btn.setObjectName('adv_toggle')
        self.adv_btn.setCursor(Qt.PointingHandCursor)
        self.adv_btn.clicked.connect(self._toggle_advanced)
        ctrl_layout.addWidget(self.adv_btn)

        # ── Advanced panel (hidden by default) ────────────────────────────────
        self.adv_panel = QWidget()
        self.adv_panel.hide()
        adv = QVBoxLayout(self.adv_panel)
        adv.setContentsMargins(0, 4, 0, 0)
        adv.setSpacing(8)

        row1 = QHBoxLayout(); row1.setSpacing(12)
        fc = QVBoxLayout(); fc.setSpacing(4)
        fc.addWidget(self._lbl('Fragments'))
        self.adv_frag = QComboBox()
        self.adv_frag.addItems([x[0] for x in _ADV_FRAGMENTS])
        self.adv_frag.setCurrentIndex(_ADV_FRAG_DEFAULT)
        self.adv_frag.setMinimumHeight(38)
        fc.addWidget(self.adv_frag)
        row1.addLayout(fc)

        bc = QVBoxLayout(); bc.setSpacing(4)
        bc.addWidget(self._lbl('Buffer size'))
        self.adv_buf = QComboBox()
        self.adv_buf.addItems([x[0] for x in _ADV_BUFSIZE])
        self.adv_buf.setCurrentIndex(_ADV_BUFSIZE_DEFAULT)
        self.adv_buf.setMinimumHeight(38)
        bc.addWidget(self.adv_buf)
        row1.addLayout(bc)

        adv.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(12)
        cc = QVBoxLayout(); cc.setSpacing(4)
        cc.addWidget(self._lbl('HTTP chunk size'))
        self.adv_chunk = QComboBox()
        self.adv_chunk.addItems([x[0] for x in _ADV_CHUNK])
        self.adv_chunk.setCurrentIndex(_ADV_CHUNK_DEFAULT)
        self.adv_chunk.setMinimumHeight(38)
        cc.addWidget(self.adv_chunk)
        row2.addLayout(cc)

        tc = QVBoxLayout(); tc.setSpacing(4)
        tc.addWidget(self._lbl('Socket timeout'))
        self.adv_timeout = QComboBox()
        self.adv_timeout.addItems([x[0] for x in _ADV_TIMEOUT])
        self.adv_timeout.setCurrentIndex(_ADV_TIMEOUT_DEFAULT)
        self.adv_timeout.setMinimumHeight(38)
        tc.addWidget(self.adv_timeout)
        row2.addLayout(tc)

        adv.addLayout(row2)

        self.adv_aria2c = QCheckBox('Use aria2c (faster on high-bandwidth connections)')
        if not _ARIA2C_FOUND:
            self.adv_aria2c.setEnabled(False)
            self.adv_aria2c.setText('Use aria2c  (not found in PATH)')
        adv.addWidget(self.adv_aria2c)

        ctrl_layout.addWidget(self.adv_panel)

        self.controls.hide()
        layout.addWidget(self.controls)
        layout.addSpacing(16)

        # ── Download button ──────────────────────────────────────────────────
        self.dl_btn = QPushButton('Download')
        self.dl_btn.setObjectName('primary')
        self.dl_btn.setMinimumHeight(54)
        self.dl_btn.clicked.connect(self._start_download)
        self.dl_btn.hide()
        layout.addWidget(self.dl_btn)

        # ── Cancel button ────────────────────────────────────────────────────
        self.cancel_btn = QPushButton('✕  Cancel Download')
        self.cancel_btn.setObjectName('cancel')
        self.cancel_btn.setMinimumHeight(50)
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.hide()
        layout.addWidget(self.cancel_btn)
        layout.addSpacing(14)

        # ── Progress section ─────────────────────────────────────────────────
        self.progress_widget = QWidget()
        prog_layout = QVBoxLayout(self.progress_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)

        # Large percentage
        self.pct_big = QLabel('0%')
        self.pct_big.setAlignment(Qt.AlignCenter)
        self.pct_big.setFont(QFont('', 52, QFont.Bold))
        self.pct_big.setStyleSheet(f'color: {_ACCENT};')
        prog_layout.addWidget(self.pct_big)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(5)
        prog_layout.addWidget(self.progress_bar)

        self.overall_bar = QProgressBar()
        self.overall_bar.setObjectName('overall')
        self.overall_bar.setValue(0)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedHeight(3)
        self.overall_bar.hide()
        prog_layout.addWidget(self.overall_bar)

        self.overall_label = QLabel('')
        self.overall_label.setAlignment(Qt.AlignCenter)
        self.overall_label.setStyleSheet(
            f'color: {_SUCCESS}; font-size: 11px;')
        self.overall_label.hide()
        prog_layout.addWidget(self.overall_label)

        self.progress_widget.hide()
        layout.addWidget(self.progress_widget)

        layout.addStretch()

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

    # ── State management ───────────────────────────────────────────────────────

    def _set_idle(self):
        self.card.hide()
        self.controls.hide()
        self.dl_btn.hide()
        self.cancel_btn.hide()
        self.progress_widget.hide()
        self.overall_bar.hide()
        self.overall_label.hide()
        self._set_status('')

    def _set_fetching(self):
        self.card.hide()
        self.controls.hide()
        self.dl_btn.hide()
        self.cancel_btn.hide()
        self.progress_widget.hide()
        self._set_status('Fetching video info…', _MUTED)

    def _set_ready(self, meta: dict):
        self._meta = meta
        t = meta['title']
        self.title_label.setText(
            t if len(t) <= 52 else t[:50] + '…')
        self.channel_label.setText(meta.get('channel', ''))
        parts = []
        dur = _fmt_dur(meta.get('duration', 0))
        if dur:
            parts.append(dur)
        if meta.get('is_playlist'):
            parts.append(f"{meta['count']} videos")
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
        self.controls.hide()
        self.dl_btn.hide()
        self.cancel_btn.show()
        self.cancel_btn.setEnabled(True)
        self.progress_widget.show()
        self.thumb.setProgress(0)
        self.pct_big.setText('0%')
        self.pct_big.setStyleSheet(f'color: {_ACCENT};')
        self.progress_bar.setValue(0)
        self.speed_label.setText('')

    def _set_status(self, text: str, color: str = _MUTED):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f'color: {color}; font-size: 11px;')

    # ── URL handling & metadata fetch ──────────────────────────────────────────

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

    # ── Download ───────────────────────────────────────────────────────────────

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, 'Select folder', self.save_input.text())
        if d:
            self.save_input.setText(d)

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url or not self._meta:
            return
        self._set_downloading()
        self.thread = QThread()
        self.worker = DownloadWorker(
            url, self.save_input.text(),
            self.quality_combo.currentText(),
            self.browser_combo.currentText(),
            **self._adv_opts())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.overall.connect(self._on_overall)
        self.worker.postprocess.connect(self._on_postprocess)
        self.worker.status.connect(lambda s: self._set_status(s, _ACCENT))
        self.thread.start()

    def _cancel_download(self):
        if hasattr(self, 'worker'):
            self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self._set_status('Cancelling…', _WARN)

    def _on_progress(self, d: dict):
        pct = d['percent']
        ipct = int(pct)
        self.progress_bar.setValue(ipct)
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
            self._set_status('Finalising…', _ACCENT)

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
        self.pct_big.setStyleSheet(f'color: {_SUCCESS};')
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


if __name__ == '__main__':
    app = QApplication(sys.argv)

    from dep_check import check_deps, DepDialog
    from PyQt5.QtWidgets import QDialog
    issues = check_deps()
    if issues:
        dlg = DepDialog(issues)
        result = dlg.exec_()
        if any(d['required'] for d in issues) or result != QDialog.Accepted:
            sys.exit(1)

    apply_stylesheet(app, theme='dark_blue.xml', invert_secondary=True)
    window = YoutubeDownloaderApp()
    window.show()
    QTimer.singleShot(3000, lambda: start_update_check(window, 'youtube-downloader'))
    sys.exit(app.exec_())
