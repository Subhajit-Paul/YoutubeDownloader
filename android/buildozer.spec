[app]
title = YouTube Downloader
package.name = youtubedownloader
package.domain = com.subhajitpaul
source.dir = .
source.include_exts = py,kv
version = 1.1.1

requirements = python3,kivy==2.3.0,yt_dlp,certifi,websockets,brotli,mutagen

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,\
                      READ_MEDIA_AUDIO,READ_MEDIA_VIDEO
android.api = 34
android.minapi = 24
android.ndk = 25b
android.gradle_dependencies =
android.enable_androidx = True

# Build both arm architectures for maximum device compatibility
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
