# YouTube Downloader

[![Desktop Build](https://github.com/Subhajit-Paul/YoutubeDownloader/actions/workflows/build-release.yml/badge.svg)](https://github.com/Subhajit-Paul/YoutubeDownloader/actions/workflows/build-release.yml)
[![Latest Release](https://img.shields.io/github/v/release/Subhajit-Paul/YoutubeDownloader?label=latest)](https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey)

Three ways to download from YouTube — a GUI video app, a GUI audio app, and a terminal binary you put on your PATH.

| App | Best for | Formats |
|-----|----------|---------|
| **YouTube Downloader** (GUI) | Casual video downloads | MP4 — Best / 1080p / 720p / 480p |
| **YouTube Audio Downloader** (GUI) | Extracting audio | MP3, M4A, OPUS, FLAC, WAV |
| **youtube-tui** (terminal) | Scripting, SSH, power users | MP4 + all audio formats |

---

## Install

### TUI — one-line install (Linux & macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/Subhajit-Paul/YoutubeDownloader/main/install-tui.sh | bash
```

Installs to `~/.local/bin/youtube-tui`. Add an alias in your shell rc:

```bash
alias ytd='youtube-tui'
```

**Windows** — download `youtube-tui-windows-x86_64.exe` from [Releases](https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest), rename it, and add the folder to your PATH.

---

### GUI apps — Linux

```bash
# Video downloader
wget https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest/download/youtube-downloader-linux-x86_64.deb
sudo dpkg -i youtube-downloader-linux-x86_64.deb

# Audio downloader
wget https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest/download/youtube-audio-downloader-linux-x86_64.deb
sudo dpkg -i youtube-audio-downloader-linux-x86_64.deb
```

### GUI apps — Windows

Download the NSIS setup installers from [Releases](https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest):

- `youtube-downloader-windows-x86_64-setup.exe`
- `youtube-audio-downloader-windows-x86_64-setup.exe`

### GUI apps — macOS

Download the DMG files from [Releases](https://github.com/Subhajit-Paul/YoutubeDownloader/releases/latest):

- `youtube-downloader-macos-arm64.dmg`
- `youtube-audio-downloader-macos-arm64.dmg`

> **Intel Mac?** The ARM64 binary runs transparently via Rosetta 2 — no separate Intel build is needed.

---

## Features

### All apps
- **Resumable downloads** — a per-directory `.ytdl-archive` skips already-downloaded videos on restart; interrupted mid-file downloads continue from where they left off
- **Parallel fragment downloads** — YouTube DASH segments fetched concurrently (default 4–8 threads) for 2–4× speed on fast connections
- **Playlist support** — videos saved into `<PlaylistTitle>/` subdirectories automatically; single videos stay flat
- **Automatic retries** — 10 retries on transient network errors before failing a video
- **Post-processor status** — "Converting: title…" shown while ffmpeg runs so the UI doesn't appear frozen

### GUI apps (Desktop)
- Thumbnail preview card with left-to-right download-wipe reveal effect
- Metadata and thumbnail fetched automatically on URL paste
- Cancel button — turns red while active, amber "Cancelled" on stop
- **Advanced panel** (hidden by default) — concurrent fragments, buffer size, HTTP chunk size, socket timeout, optional aria2c external downloader
- **Browser cookie support** — Chrome, Firefox, Brave, Safari, Opera, Edge, Chromium, Vivaldi
- Startup dependency checker with per-dep install commands
- Background auto-update checker

### TUI (`youtube-tui`)
- Keyboard + mouse via [Textual](https://github.com/Textualize/textual)
- Video and audio in one binary — toggle with Radio buttons
- Real-time per-file progress bar and playlist progress bar
- Log panel hidden by default — `Ctrl+L` to toggle
- Advanced options panel — `Ctrl+A` to toggle
- Key bindings: `Ctrl+D` download · `Ctrl+X` cancel · `Ctrl+L` log · `Ctrl+A` advanced · `Ctrl+Q` quit

---

## Requirements

FFmpeg is required for video merging and audio extraction. The bundled binaries include ffmpeg — no separate install needed. If running from source:

| Platform | Command |
|----------|---------|
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install ffmpeg` or `choco install ffmpeg` |

---

## Build

CI runs on every tag push via GitHub Actions across five platform targets:

| Platform | Runner | GUI artifacts | TUI artifact |
|----------|--------|---------------|--------------|
| Linux x86_64 | `ubuntu-latest` | `.deb` × 2 | `tar.gz` binary |
| Windows x86_64 | `windows-latest` | NSIS `.exe` × 2 | raw `.exe` |
| macOS arm64 | `macos-14` | `.dmg` × 2 | `tar.gz` binary |

All three publish to the same GitHub Release for each version tag.

### Build locally

```bash
git clone https://github.com/Subhajit-Paul/YoutubeDownloader
cd YoutubeDownloader

pip install -r requirements-build.txt

# GUI apps (produce dist/youtube-downloader and dist/youtube-audio-downloader)
pyinstaller youtube-downloader.spec --noconfirm
pyinstaller youtube-audio-downloader.spec --noconfirm

# TUI binary (produces dist/youtube-tui)
pyinstaller youtube-tui.spec --noconfirm
```

---

## Development

```bash
git clone https://github.com/Subhajit-Paul/YoutubeDownloader
cd YoutubeDownloader

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

python ytd.py          # video GUI
python ytd_audio.py    # audio GUI
python ytd_tui.py      # TUI
```

**Android** — the Kivy app in `android/` is no longer built or published; no
APK ships with a release. The source is kept and still builds by hand:

```bash
pip install buildozer==1.5.0 cython==3.0.11
cd android
buildozer android debug
```

See [docs/ANDROID.md](docs/ANDROID.md) for the permission audit.

---

## License

[MIT](LICENSE)
