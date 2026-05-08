#!/usr/bin/env bash
# install-tui.sh — install youtube-tui to ~/.local/bin
# Usage: curl -fsSL https://raw.githubusercontent.com/Subhajit-Paul/YoutubeDownloader/main/install-tui.sh | bash
set -euo pipefail

REPO="Subhajit-Paul/YoutubeDownloader"
BINARY="youtube-tui"
ALIAS_NAME="ytd"
INSTALL_DIR="${HOME}/.local/bin"

# ── Detect platform ────────────────────────────────────────────────────────────
OS="$(uname -s)"

case "$OS" in
  Linux*)  ASSET="youtube-tui-linux-x86_64.tar.gz" ;;
  Darwin*) ASSET="youtube-tui-macos-arm64.tar.gz" ;;
  *)
    echo "Unsupported platform: $OS" >&2
    echo "For Windows, download the .exe from: https://github.com/$REPO/releases/latest" >&2
    exit 1
    ;;
esac

URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"

# ── Download and extract ───────────────────────────────────────────────────────
echo "Downloading $BINARY..."
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

# ── Install binary ─────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
mv "$TMP/$BINARY" "$INSTALL_DIR/$BINARY"
chmod +x "$INSTALL_DIR/$BINARY"

echo "Installed: $INSTALL_DIR/$BINARY"

# ── Shell detection → rc file, PATH line, alias line, source command ───────────
SHELL_NAME="$(basename "${SHELL:-sh}")"

case "$SHELL_NAME" in
  zsh)
    RC="${ZDOTDIR:-$HOME}/.zshrc"
    PATH_LINE="export PATH=\"\$HOME/.local/bin:\$PATH\""
    ALIAS_LINE="alias $ALIAS_NAME='$BINARY'"
    SOURCE_CMD="source $RC"
    ;;
  fish)
    RC="${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
    PATH_LINE="fish_add_path $INSTALL_DIR"
    ALIAS_LINE="alias $ALIAS_NAME $BINARY"
    SOURCE_CMD="source $RC"
    ;;
  csh|tcsh)
    RC="$HOME/.${SHELL_NAME}rc"
    PATH_LINE="setenv PATH \"\$HOME/.local/bin:\$PATH\""
    ALIAS_LINE="alias $ALIAS_NAME $BINARY"
    SOURCE_CMD="source $RC"
    ;;
  ksh|mksh|pdksh)
    RC="$HOME/.kshrc"
    PATH_LINE="export PATH=\"\$HOME/.local/bin:\$PATH\""
    ALIAS_LINE="alias $ALIAS_NAME='$BINARY'"
    SOURCE_CMD=". $RC"
    ;;
  dash|ash|sh)
    RC="$HOME/.profile"
    PATH_LINE="export PATH=\"\$HOME/.local/bin:\$PATH\""
    ALIAS_LINE="alias $ALIAS_NAME='$BINARY'"
    SOURCE_CMD=". $RC"
    ;;
  *)  # bash and anything else
    RC="$HOME/.bashrc"
    PATH_LINE="export PATH=\"\$HOME/.local/bin:\$PATH\""
    ALIAS_LINE="alias $ALIAS_NAME='$BINARY'"
    SOURCE_CMD="source $RC"
    ;;
esac

# ── Ensure ~/.local/bin is in PATH (write once) ────────────────────────────────
if ! echo ":${PATH}:" | grep -q ":${INSTALL_DIR}:"; then
  if ! grep -qF "$INSTALL_DIR" "$RC" 2>/dev/null; then
    echo "$PATH_LINE" >> "$RC"
    echo "Added PATH entry to $RC"
  fi
fi

# ── Write alias (write once) ───────────────────────────────────────────────────
if ! grep -qF "alias $ALIAS_NAME" "$RC" 2>/dev/null; then
  echo "$ALIAS_LINE" >> "$RC"
  echo "Added alias '$ALIAS_NAME' to $RC"
else
  echo "Alias '$ALIAS_NAME' already present in $RC"
fi

# ── Reload rc so the alias is live in the current session ─────────────────────
# shellcheck disable=SC1090
source "$RC" 2>/dev/null || true

echo ""
echo "Done.  Run:  $ALIAS_NAME   (or: $BINARY)"
echo ""
echo "If the alias isn't active yet, reload your shell:"
echo "  $SOURCE_CMD"
