#!/usr/bin/env python3
"""Audit a built APK for device-compatibility and security properties.

Usage: python tools/check_apk.py <path-to-apk> [--strict]

Checks things that only become visible in the artefact, not the source:
native-library page alignment, target SDK, bundled TLS version, debuggability.
Exits non-zero on a FAIL when --strict is given.
"""
import argparse
import re
import struct
import subprocess
import sys
import zipfile

# Android 15 may use 16 KB pages; 4 KB-aligned libs will not load there.
# This is a 64-bit-only feature — 32-bit ABIs always use 4 KB pages and are
# exempt, so only these ABI directories are checked.
REQUIRED_ALIGN = 0x4000
ABIS_64BIT = ("arm64-v8a", "x86_64", "riscv64")
# Google Play's minimum target API. Raise as Google raises it.
MIN_TARGET_SDK = 35
# OpenSSL 1.1.1 went end-of-life 2023-09-11.
EOL_TLS = re.compile(r"lib(ssl|crypto)1\.1\.so$")

results = []


def check(name, ok, detail, fatal=True):
    results.append((name, ok, detail, fatal))


def _load_align(data):
    """Smallest p_align across PT_LOAD segments of an ELF blob."""
    if data[:4] != b"\x7fELF":
        return None
    is64, little = data[4] == 2, data[5] == 1
    e = "<" if little else ">"
    if not is64:
        phoff, phentsize, phnum = (struct.unpack_from(e + "I", data, 28)[0],
                                   struct.unpack_from(e + "H", data, 42)[0],
                                   struct.unpack_from(e + "H", data, 44)[0])
        align_off, load_type_off = 28, 0
    else:
        phoff = struct.unpack_from(e + "Q", data, 32)[0]
        phentsize = struct.unpack_from(e + "H", data, 54)[0]
        phnum = struct.unpack_from(e + "H", data, 56)[0]
        align_off, load_type_off = 48, 0
    aligns = []
    for i in range(phnum):
        off = phoff + i * phentsize
        if off + phentsize > len(data):
            break
        p_type = struct.unpack_from(e + "I", data, off + load_type_off)[0]
        if p_type != 1:  # PT_LOAD
            continue
        fmt = e + ("Q" if is64 else "I")
        aligns.append(struct.unpack_from(fmt, data, off + align_off)[0])
    return min(aligns) if aligns else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    z = zipfile.ZipFile(args.apk)
    names = z.namelist()

    # ── native libraries ────────────────────────────────────────────────────
    sos = [n for n in names if n.endswith(".so")]
    check("native libs present", bool(sos), f"{len(sos)} .so files")

    sos64 = [n for n in sos if any(f"/{abi}/" in n for abi in ABIS_64BIT)]
    misaligned = []
    for n in sos64:
        a = _load_align(z.read(n))
        if a is not None and a < REQUIRED_ALIGN:
            misaligned.append((n.split("/")[-1], hex(a)))
    check(
        "16 KB page alignment",
        not misaligned,
        f"{len(sos64)} 64-bit libs aligned (32-bit ABIs exempt)" if not misaligned
        else f"{len(misaligned)}/{len(sos64)} 64-bit libs are <16KB, e.g. "
             + ", ".join(f"{n}={a}" for n, a in misaligned[:3]),
    )

    # ── end-of-life TLS ─────────────────────────────────────────────────────
    eol = sorted({n.split("/")[-1] for n in sos if EOL_TLS.search(n)})
    check("TLS library supported", not eol,
          "no EOL TLS" if not eol else f"bundles end-of-life {', '.join(eol)}")

    # ── manifest ────────────────────────────────────────────────────────────
    try:
        import logging
        from loguru import logger
        logger.remove()
        logging.disable(logging.CRITICAL)
        from androguard.core.apk import APK
        a = APK(args.apk)
        target = a.get_target_sdk_version()
        target = int(target) if target else 0
        check("target SDK", target >= MIN_TARGET_SDK,
              f"targetSdk={target} (Google Play requires >={MIN_TARGET_SDK})")
        dbg = str(a.get_attribute_value("application", "debuggable")).lower() == "true"
        check("not debuggable", not dbg,
              "release flags" if not dbg else "android:debuggable=true")
    except ImportError:
        check("manifest parsed", False, "androguard not installed", fatal=False)

    # ── ffmpeg ──────────────────────────────────────────────────────────────
    has_ffmpeg = any("ffmpeg" in n.lower() for n in names)
    check("ffmpeg bundled", has_ffmpeg,
          "present" if has_ffmpeg
          else "absent — format merging and audio extraction cannot work")

    width = max(len(n) for n, *_ in results)
    failed = 0
    for name, ok, detail, fatal in results:
        mark = "PASS" if ok else ("FAIL" if fatal else "WARN")
        print(f"[{mark}] {name.ljust(width)}  {detail}")
        if not ok and fatal:
            failed += 1

    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    if failed and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
