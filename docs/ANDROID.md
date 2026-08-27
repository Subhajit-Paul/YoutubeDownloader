# Android build — known limitations

The APK builds and installs, but it is **not fit for current Android phones**.
These findings come from auditing the built artefact (`tools/check_apk.py`),
not from running it on a device. **No emulator or device test has been done.**

Run the audit yourself against any built APK:

```bash
pip install androguard
python tools/check_apk.py path/to/app.apk
```

## Blocking

| Issue | Effect | Fix |
|---|---|---|
| Native libs are 4 KB aligned | **Will not load on Android 15+ devices using 16 KB pages.** All 20 `.so` files report `p_align = 0x1000`; 16 KB devices need `0x4000`. | Needs NDK r27+, which needs a newer python-for-android than the pinned `v2024.01.21`. |
| No ffmpeg in the APK | The four MP4 options need stream merging and the four audio options (MP3/M4A/OPUS/FLAC) need extraction — **all eight require ffmpeg, which is absent**. Only progressive single-file MP4 can download. | Add an ffmpeg recipe to `requirements`, or drop the formats that cannot work. |
| `targetSdk = 34` | Google Play requires 35+ (since Aug 2025). **Cannot be published.** | Raise `android.api`; needs a newer p4a/NDK. |
| Debug-signed, `android:debuggable=true` | Not distributable, and debuggable in a shipped build is a security problem. | `buildozer android release` plus a signing key. |

## Non-blocking but real

- **OpenSSL 1.1.1 is bundled** (`libssl1.1.so`, `libcrypto1.1.so`) — end-of-life since
  2023-09-11 and carrying unpatched CVEs. It handles all HTTPS traffic. Comes from the
  pinned p4a; a newer p4a builds OpenSSL 3.x.
- **Downloads are not user-visible.** `SAVE_DIR` is `Path.home()/Downloads/YouTubeDownloader`.
  Android has no user home directory; p4a points `HOME` at app-private storage, and the app
  uses no MediaStore or SAF API, so files never reach the shared `Downloads` folder.
  `WRITE_EXTERNAL_STORAGE` is declared but grants nothing on Android 11+.

## Why the toolchain is pinned back

`p4a.branch = v2024.01.21` is pinned because the current release cannot build this app:

- `v2026.05.09` resolves dependencies as Android wheels
  (`--only-binary=:all: --platform=android_24_*`) and then fails installing them —
  `charset_normalizer-…-cp314-…-android_24_arm64_v8a.whl is not a supported wheel on
  this platform` — because the host pip is 3.11.
- Unpinned `master` additionally fails compiling kivy against the CPython it builds.

Unblocking the items above means getting a modern p4a to build first. Setting
`LDFLAGS=-Wl,-z,max-page-size=16384` was tried and has **no effect**: p4a v2024.01.21
sets its own link flags per recipe.
