[app]
title = YouTube Downloader
package.name = youtubedownloader
package.domain = com.subhajitpaul
source.dir = .
source.include_exts = py,kv
version = 1.4.0

# ponytail: no brotli - it is a C extension with no Android wheel, and p4a
# resolves deps with --only-binary=:all: --platform=android_*, so it fails the
# resolve and drops p4a into a source-build venv that then dies on its own pip.
# yt-dlp only uses brotli for 'Accept-Encoding: br' and degrades without it.
# ffmpeg: p4a's recipe builds the CLI and installs it as
# lib/<abi>/libffmpegbin.so. Without it neither stream merging nor audio
# extraction can run, i.e. none of the formats the UI offers would work.
requirements = python3,kivy,yt_dlp,certifi,websockets,mutagen,ffmpeg

orientation = portrait
fullscreen = 0

# Keep on one line: a continuation leaks its indentation into the first name,
# producing 'android.permission. READ_MEDIA_AUDIO' which Android silently drops.
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,READ_MEDIA_AUDIO,READ_MEDIA_VIDEO
android.api = 35
android.minapi = 24
# NDK left unpinned: p4a's default is r27+, which links 16 KB-aligned
# native libs (required by Android 15+ devices using 16 KB pages).

p4a.branch = develop
# Pinned to a commit, not a moving branch: unpinned p4a drift is what
# broke this build before. No release tag works — the fixes for the
# wheel-install stage landed on develop after v2026.05.09.
p4a.commit = 9d5918bf752379f4520902524c15f794e45972b4
android.gradle_dependencies =
android.enable_androidx = True

# Build both arm architectures for maximum device compatibility
# buildozer defaults release builds to .aab; we ship sideloadable APKs.
android.release_artifact = apk
android.debug_artifact = apk
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
