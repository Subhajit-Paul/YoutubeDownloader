import sys

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QComboBox,
    QFrame, QGraphicsDropShadowEffect, QCheckBox,
)
from PyQt5.QtCore import Qt, QThread, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor

from pathlib import Path

from version import __version__
from ytd_core import (
    BASE_SS, BaseDownloadWorker, BaseWindow, ThumbWidget,
    reusable_info as _reusable_info,
    _BROWSERS, _ARIA2C_FOUND,
    _ADV_FRAGMENTS, _ADV_BUFSIZE, _ADV_CHUNK, _ADV_TIMEOUT,
    _ADV_FRAG_DEFAULT, _ADV_BUFSIZE_DEFAULT, _ADV_CHUNK_DEFAULT,
    _ADV_TIMEOUT_DEFAULT,
)

from theme import (
    ACCENT as _ACCENT, TEXT as _TEXT, MUTED as _MUTED,
    SUCCESS as _SUCCESS, IDENTITY as _IDENTITY,
)

# ── What makes this the video app ─────────────────────────────────────────────

class _ThumbWidget(ThumbWidget):
    GLYPH = '▶'
    OVERLAY = (10, 10, 20, 195)


_QUALITY_MAP = {
    'Best':  'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
    '1080p': 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
    '720p':  'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
    '480p':  'bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
}


class DownloadWorker(BaseDownloadWorker):
    """Muxed video: pick a capped-height mp4 stream and merge to mp4."""

    def __init__(self, url, save_path, quality, browser='None', **kw):
        super().__init__(url, save_path, browser=browser, **kw)
        self.quality = quality

    def media_opts(self):
        return {
            'format': _QUALITY_MAP.get(self.quality, _QUALITY_MAP['Best']),
            'merge_output_format': 'mp4',
        }


# ── Main window ──────────────────────────────────────────────────────────────


class YoutubeDownloaderApp(BaseWindow):

    _SS = BASE_SS



    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(0)

        # ── App mark ─────────────────────────────────────────────────────────
        # Typographic, not a bitmap wordmark: the old logo.png was a novelty
        # face that read as clip-art, and both apps shipped the *video* one.
        ident = _IDENTITY['video']

        glyph = QLabel(ident['glyph'])
        glyph.setObjectName('appglyph')
        glyph.setFixedSize(30, 30)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            f"background: {ident['tint']}; color: {ident['on_tint']};"
            f"border-radius: 9px; font-size: 14px;")

        name = QLabel(ident['name'])
        name.setObjectName('appname')

        ver = QLabel(f'v{__version__}')
        ver.setObjectName('version')

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        hdr.addWidget(glyph)
        hdr.addWidget(name)
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
        paste_btn.setObjectName('secondary')
        paste_btn.setMinimumSize(84, 46)
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
        # QFont('') carries no family and resolves to a serif face; take the
        # inherited application font and change only what differs.
        title_font = QFont(self.title_label.font())
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
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
        browse_btn.setObjectName('secondary')
        browse_btn.setMinimumSize(92, 44)
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
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setObjectName('cancel')
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setMinimumWidth(96)
        self.cancel_btn.setMaximumWidth(120)
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.hide()

        # ── Progress section ─────────────────────────────────────────────────
        self.progress_widget = QWidget()
        prog_layout = QVBoxLayout(self.progress_widget)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)

        # A percentage reads as an annotation on the bar, not as a headline.
        # 52pt centred type made the number the loudest object in the window.
        self.pct_big = QLabel('0%')
        self.pct_big.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.pct_big.setObjectName('pct')

        pct_row = QHBoxLayout()
        pct_row.setContentsMargins(0, 0, 0, 0)
        pct_row.addWidget(self.pct_big)
        pct_row.addStretch()
        pct_row.addWidget(self.cancel_btn)
        prog_layout.addLayout(pct_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self._bar_anim = QPropertyAnimation(self.progress_bar, b'value')
        self._bar_anim.setDuration(180)
        self._bar_anim.setEasingCurve(QEasingCurve.OutCubic)
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

        # ── Empty state ──────────────────────────────────────────────────────
        # The window was ~70% dead space before a link was pasted. An empty
        # state is the app explaining itself at the only moment the user has
        # nothing to look at.
        self.empty = QWidget()
        empty_l = QVBoxLayout(self.empty)
        empty_l.setContentsMargins(0, 8, 0, 8)
        empty_l.setSpacing(6)
        empty_l.addStretch()

        _et = QLabel('Paste a link to begin')
        _et.setObjectName('empty_title')
        _et.setAlignment(Qt.AlignCenter)
        empty_l.addWidget(_et)

        _eb = QLabel('Works with videos, playlists and channels.\n'
                     'Quality options appear once the link is read.')
        _eb.setObjectName('empty_body')
        _eb.setAlignment(Qt.AlignCenter)
        empty_l.addWidget(_eb)
        empty_l.addStretch()

        layout.addWidget(self.empty, 1)

        layout.addStretch()

    # ── State management ───────────────────────────────────────────────────────

    # ── URL handling & metadata fetch ──────────────────────────────────────────

    # ── Download ───────────────────────────────────────────────────────────────

    def _start_download(self):
        url = self.url_input.text().strip()
        if not url or not self._meta:
            return
        info = _reusable_info(self._meta, url)
        self._set_downloading()
        self.thread = QThread()
        self.worker = DownloadWorker(
            url, self.save_input.text(),
            self.quality_combo.currentText(),
            self.browser_combo.currentText(),
            **self._adv_opts(), info=info)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.overall.connect(self._on_overall)
        self.worker.postprocess.connect(self._on_postprocess)
        self.worker.status.connect(lambda s: self._set_status(s, _ACCENT))
        self.thread.start()

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

    window = YoutubeDownloaderApp()
    window.show()
    # Imported inside the callback: update_ui pulls updater and
    # urllib.request (~21 ms), and nothing here runs until T+3 s.
    def _check_updates():
        from update_ui import start_update_check
        start_update_check(window, 'youtube-downloader')

    QTimer.singleShot(3000, _check_updates)
    sys.exit(app.exec_())
