# Android build

> The APK is no longer built by CI or attached to releases. Everything below
> applies to a hand-built APK — see the Android note in the README.


The APK is audited on every build by `tools/check_apk.py`, which **gates the
workflow** (`--strict`). Current state: **6/6 passing**.

```
[PASS] native libs present    64 .so files
[PASS] 16 KB page alignment   32 64-bit libs aligned (32-bit ABIs exempt)
[PASS] TLS library supported  no EOL TLS
[PASS] target SDK             targetSdk=35 (Google Play requires >=35)
[PASS] not debuggable         release flags
[PASS] ffmpeg bundled         present
```

Run it yourself against any APK:

```bash
pip install androguard
python tools/check_apk.py path/to/app.apk --strict
```

## What each check exists for

| Check | Why |
|---|---|
| 16 KB page alignment | Android 15+ devices may use 16 KB memory pages; 4 KB-aligned native libs will not load there. 64-bit only — 32-bit ABIs always use 4 KB and are exempt. |
| TLS library supported | OpenSSL 1.1.1 went end-of-life 2023-09-11. It handles all HTTPS traffic. |
| target SDK | Google Play's floor; raise `MIN_TARGET_SDK` as Google raises it. |
| not debuggable | `buildozer android debug` sets `android:debuggable=true`, which must never ship. |
| ffmpeg bundled | All eight formats need it — the four MP4 options merge separate streams, the four audio options transcode. Without it none complete. |

## Signing

Release builds are signed. Set these repository secrets to use a stable key:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -w0 release.keystore` |
| `ANDROID_KEYSTORE_ALIAS` | key alias |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `ANDROID_KEY_PASSWORD` | key password |

```bash
keytool -genkeypair -v -keystore release.keystore -alias upload \
  -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 release.keystore    # -> ANDROID_KEYSTORE_BASE64
```

**Without these secrets CI signs with a throwaway key generated per build.** Such
an APK installs fine for testing but cannot be upgraded in place, because Android
requires a stable signature across versions. Set the secrets before shipping to
users. The build logs a warning when it falls back.

## Toolchain

`p4a.commit` pins python-for-android to an exact commit rather than a branch —
unpinned drift is what broke this build twice. Two things to know when bumping:

- `v2026.05.09` **cannot build this app**: its dependency install stage drops
  `--platform`/`--python-version`, so pip rejects the android-tagged wheels it
  just resolved (`charset_normalizer-…-cp314-…-android_24_arm64_v8a.whl is not a
  supported wheel on this platform`). Fixed on `develop` by
  *Remove venv creation for python package install stage* (#3366).
- The NDK is deliberately **not** pinned, so p4a's default (r27+) is used. That
  is what produces 16 KB-aligned libraries.

`android.release_artifact = apk` — buildozer otherwise emits an `.aab`, which is
Play-Store-only and cannot be sideloaded.

## Storage

Downloads go to `getExternalFilesDir()`
(`Android/data/<pkg>/files/YouTubeDownloader`), which is user-visible in a file
manager and needs no runtime permission. `Path.home()` — the previous default —
points at app-private storage on Android, where nothing can see the files.

## Not covered

The APK has **never been installed or run on a device or emulator**. Every
statement here comes from auditing the artefact and reading the source. Kivy
needs a windowing backend, so `android/main.py` is parsed and inspected
statically rather than executed.
