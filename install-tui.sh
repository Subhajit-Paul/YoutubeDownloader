#!/usr/bin/env bash
# install-tui.sh — install youtube-tui to ~/.local/bin
# Usage: curl -fsSL https://raw.githubusercontent.com/Subhajit-Paul/YoutubeDownloader/main/install-tui.sh | bash
set -euo pipefail

REPO="Subhajit-Paul/YoutubeDownloader"
BINARY="youtube-tui"
INSTALL_DIR="${HOME}/.local/bin"

# ── Detect platform ────────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux*)
    ASSET="youtube-tui-linux-x86_64.tar.gz"
    ;;
  Darwin*)
    if [ "$ARCH" = "arm64" ]; then
      ASSET="youtube-tui-macos-arm64.tar.gz"
    else
      ASSET="youtube-tui-macos-x86_64.tar.gz"
    fi
    ;;
  *)
    echo "Unsupported platform: $OS" >&2
    echo "For Windows, download the .exe from:" >&2
    echo "  https://github.com/$REPO/releases/latest" >&2
    exit 1
    ;;
esac

URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"

# ── Download and extract ───────────────────────────────────────────────────────
echo "Downloading $BINARY ($ASSET)..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if command -v curl &>/dev/null; then
  curl -fsSL "$URL" -o "$TMP/$ASSET"
elif command -v wget &>/dev/null; then
  wget -qO "$TMP/$ASSET" "$URL"
else
  echo "Error: curl or wget is required." >&2
  exit 1
fi

tar -xzf "$TMP/$ASSET" -C "$TMP"

# ── Install ────────────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
mv "$TMP/$BINARY" "$INSTALL_DIR/$BINARY"
chmod +x "$INSTALL_DIR/$BINARY"

echo "Installed: $INSTALL_DIR/$BINARY"

# ── PATH hint ─────────────────────────────────────────────────────────────────
if ! echo ":${PATH}:" | grep -q ":${INSTALL_DIR}:"; then
  echo ""
  echo "$INSTALL_DIR is not in your PATH. Add it:"
  echo "  bash/zsh:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
  echo "  zsh only:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
  echo "  fish:      fish_add_path ~/.local/bin"
fi

echo ""
echo "Run:   $BINARY"
echo "Alias: alias ytd='$BINARY'   (add to ~/.bashrc or ~/.zshrc)"
