#!/usr/bin/env bash
# Usage: bash make-deb.sh <app-name> <display-name> <version>
# Example: bash make-deb.sh youtube-downloader "YouTube Downloader" 1.0.1
set -euo pipefail

APP="$1"
DISPLAY="$2"
VERSION="$3"
DESC="${4:-Download videos and audio from YouTube using yt-dlp.}"
ARCH="amd64"
PKG="${APP}_${VERSION}_${ARCH}"

mkdir -p "${PKG}/DEBIAN"
mkdir -p "${PKG}/usr/bin"
mkdir -p "${PKG}/usr/share/applications"
mkdir -p "${PKG}/usr/share/icons/hicolor/256x256/apps"

# Application directory.
# PyInstaller now emits onedir (a onefile bootloader re-extracts the whole
# archive on every launch — 1298 ms vs ~390 ms to first paint), so the payload
# is a directory under /usr/lib with a launcher on PATH.
mkdir -p "${PKG}/usr/lib/${APP}"
cp -a "dist/${APP}/." "${PKG}/usr/lib/${APP}/"
chmod 755 "${PKG}/usr/lib/${APP}/${APP}"

cat > "${PKG}/usr/bin/${APP}" <<LAUNCH
#!/bin/sh
exec /usr/lib/${APP}/${APP} "\$@"
LAUNCH
chmod 755 "${PKG}/usr/bin/${APP}"

# Desktop entry
install -m 644 "packaging/linux/${APP}.desktop" "${PKG}/usr/share/applications/"

# Icon
if [ -f logo.png ]; then
  install -m 644 logo.png "${PKG}/usr/share/icons/hicolor/256x256/apps/${APP}.png"
fi

cat > "${PKG}/DEBIAN/control" <<EOF
Package: ${APP}
Version: ${VERSION}
Architecture: ${ARCH}
Maintainer: Subhajit Paul <test.dev.paul@gmail.com>
Description: ${DISPLAY}
 ${DESC}
EOF

cat > "${PKG}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor
fi
EOF
chmod 755 "${PKG}/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "${PKG}"
echo "Built: ${PKG}.deb"
