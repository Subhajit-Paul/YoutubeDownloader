#!/usr/bin/env python3
"""Render an app's mark to a square PNG, for packaging.

    make-icon.py <video|audio|tui> <size> <out.png>

The hicolor icon directories are size-specific, but logo.png is a 640x153
wordmark — installing it as 256x256/apps/<app>.png hands the desktop a
non-square image under a name that promises otherwise, and the same one for
both apps. This draws the identity mark the window itself shows, square at
whatever size is asked for.

Build-time only; nothing here ships inside a bundle.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def render(key, size, out):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QSize
    from PyQt5.QtWidgets import QApplication

    import theme

    app = QApplication.instance() or QApplication([])  # kept alive by the name
    pixmap = theme.app_icon(key, size).pixmap(QSize(size, size))
    if pixmap.isNull():
        raise SystemExit(f"render produced an empty pixmap for {key!r}")
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not pixmap.save(out, "PNG"):
        raise SystemExit(f"could not write {out}")
    assert app is not None
    return out


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__.strip())
    key, size, out = argv[1], int(argv[2]), argv[3]
    if key not in ("video", "audio", "tui"):
        raise SystemExit(f"unknown identity {key!r}")
    render(key, size, out)


if __name__ == "__main__":
    main(sys.argv)
