#!/usr/bin/env bash
# Checks install-tui.sh picks the right release asset per platform, and refuses
# platforms with no published build instead of downloading an unusable binary.
# Run: bash test-install-tui.sh
set -uo pipefail
cd "$(dirname "$0")"

fail=0
run() { # os arch -> prints requested asset, or "REFUSED"
  local tmp; tmp="$(mktemp -d)"
  printf '#!/bin/sh\n[ "$1" = "-m" ] && echo %s || echo %s\n' "$2" "$1" > "$tmp/uname"
  # stub curl: record the URL, then fail so the install never proceeds
  printf '#!/bin/sh\nfor a; do case "$a" in https://*) echo "$a" > "%s/url";; esac; done\nexit 22\n' "$tmp" > "$tmp/curl"
  printf '#!/bin/sh\nexit 22\n' > "$tmp/wget"
  chmod +x "$tmp/uname" "$tmp/curl" "$tmp/wget"
  PATH="$tmp:$PATH" HOME="$tmp" bash install-tui.sh >/dev/null 2>&1
  if [ -f "$tmp/url" ]; then basename "$(cat "$tmp/url")"; else echo "REFUSED"; fi
  rm -rf "$tmp"
}

check() { # os arch expected
  local got; got="$(run "$1" "$2")"
  if [ "$got" = "$3" ]; then
    echo "ok    $1/$2 -> $got"
  else
    echo "FAIL  $1/$2 -> $got (expected $3)"; fail=1
  fi
}

check Linux  x86_64  youtube-tui-linux-x86_64.tar.gz
check Darwin arm64   youtube-tui-macos-arm64.tar.gz
check Darwin x86_64  REFUSED   # Intel Mac: only arm64 is published
check Linux  aarch64 REFUSED   # arm64 Linux: only x86_64 is published

exit $fail
