[app]
title = YouTube Downloader
package.name = youtubedownloader
package.domain = com.subhajitpaul
source.dir = .
source.include_exts = py,kv
version = 1.1.1

# ponytail: no brotli - it is a C extension with no Android wheel, and p4a
# resolves deps with --only-binary=:all: --platform=android_*, so it fails the
# resolve and drops p4a into a source-build venv that then dies on its own pip.
# yt-dlp only uses brotli for 'Accept-Encoding: br' and degrades without it.
requirements = python3,kivy==2.3.1,yt_dlp,certifi,websockets,mutagen

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,\
                      READ_MEDIA_AUDIO,READ_MEDIA_VIDEO
android.api = 34
android.minapi = 24
android.ndk = 25b

# ponytail: pin p4a to a release so master drift cannot break the build again.
# Bump deliberately; unpinned master broke kivy 2.3.0 compilation in Aug 2026.
p4a.branch = v2026.05.09
android.gradle_dependencies =
android.enable_androidx = True

# Build both arm architectures for maximum device compatibility
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
