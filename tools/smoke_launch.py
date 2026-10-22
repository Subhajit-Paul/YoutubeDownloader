#!/usr/bin/env python3
"""Start a built bundle and confirm its UI initializes and stays up.

    smoke_launch.py <dist/name> [seconds]

CI built three apps on three platforms and never started one of them. That is
the gap this closes: a bundle whose shared libraries cannot be resolved dies at
exec time, before a line of Python runs — which is precisely how a bad ICU stub
would present, and the stub is only exercised on Linux locally.

A Windows loader error dialog can stay open indefinitely. A live process alone
is therefore insufficient: the app must also signal readiness from its UI event
loop. The TUI runs headlessly with the same composition and dependency checks.
"""
import os
import subprocess
import sys
import tempfile
import time


def executable(bundle):
    """The COLLECT output is <dir>/<name>[.exe] on every platform.

    Falls back to scanning, so a directory that was renamed still reports the
    real failure — the loader's — rather than "no executable inside".
    """
    name = os.path.basename(bundle.rstrip("/\\"))
    suffix = ".exe" if os.name == "nt" else ""
    exe = os.path.join(bundle, name + suffix)
    if os.path.exists(exe):
        return exe
    if not os.path.isdir(bundle):
        return None
    for entry in sorted(os.listdir(bundle)):
        if entry.lower() == 'uninstall.exe':
            continue
        path = os.path.join(bundle, entry)
        if os.path.isfile(path) and (entry.endswith(suffix) if suffix
                                     else os.access(path, os.X_OK)):
            return path
    return None


def smoke(bundle, seconds=12):
    bundle = os.path.abspath(bundle)
    exe = executable(bundle)
    if exe is None:
        print(f"FAIL  {bundle}: no executable inside", file=sys.stderr)
        return False

    # Exercise qwindows too; an offscreen-only check misses native plugin errors.
    platform = "windows" if os.name == "nt" else "offscreen"
    env = dict(os.environ, QT_QPA_PLATFORM=platform)
    # Qt still wants a writable runtime dir on Linux; without one it prints a
    # warning that is noise, not failure.
    env.setdefault("XDG_RUNTIME_DIR", os.path.abspath("."))

    with tempfile.TemporaryDirectory(prefix="ytd-smoke-") as tmp, \
            tempfile.TemporaryFile() as output:
        ready = os.path.join(tmp, "ready")
        env['YTD_SMOKE_READY_FILE'] = ready
        # A file avoids filling a pipe while a console app is rendering.
        try:
            proc = subprocess.Popen([exe], env=env, cwd=bundle,
                                    stdout=output, stderr=subprocess.STDOUT)
        except OSError as exc:
            print(f"FAIL  {exe}: {exc}", file=sys.stderr)
            return False

        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.25)

            if proc.poll() is not None:
                reason = f"exited early with {proc.returncode}"
            elif not os.path.exists(ready):
                reason = "never reached its UI event loop"
            else:
                print(f"ok    {exe} initialized and ran for {seconds}s")
                return True

            print(f"FAIL  {exe} {reason}", file=sys.stderr)
            output.seek(0)
            out = output.read().decode("utf-8", "replace").strip()
            if out:
                print(out, file=sys.stderr)
            return False
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def main(argv):
    if not 2 <= len(argv) <= 3:
        raise SystemExit(__doc__.strip())
    seconds = int(argv[2]) if len(argv) == 3 else 12
    raise SystemExit(0 if smoke(argv[1], seconds) else 1)


if __name__ == "__main__":
    main(sys.argv)
