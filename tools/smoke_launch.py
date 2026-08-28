#!/usr/bin/env python3
"""Start a built bundle and confirm it stays up.

    smoke_launch.py <dist/name> [seconds]

CI built three apps on three platforms and never started one of them. That is
the gap this closes: a bundle whose shared libraries cannot be resolved dies at
exec time, before a line of Python runs — which is precisely how a bad ICU stub
would present, and the stub is only exercised on Linux locally.

A GUI app has nothing to exit for, so "still running when the clock runs out"
is the pass condition. Anything else — a non-zero exit, an immediate clean exit,
a loader message on stderr — is a failure, and its output is printed.
"""
import os
import subprocess
import sys
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
    for entry in sorted(os.listdir(bundle)):
        path = os.path.join(bundle, entry)
        if os.path.isfile(path) and (entry.endswith(suffix) if suffix
                                     else os.access(path, os.X_OK)):
            return path
    return None


def smoke(bundle, seconds=12):
    exe = executable(bundle)
    if exe is None:
        print(f"FAIL  {bundle}: no executable inside", file=sys.stderr)
        return False

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    # Qt still wants a writable runtime dir on Linux; without one it prints a
    # warning that is noise, not failure.
    env.setdefault("XDG_RUNTIME_DIR", os.path.abspath("."))

    proc = subprocess.Popen([exe], env=env, cwd=bundle,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            out = proc.communicate()[0].decode("utf-8", "replace")
            print(f"FAIL  {exe} exited early with {proc.returncode}",
                  file=sys.stderr)
            if out.strip():
                print(out.strip(), file=sys.stderr)
            return False
        time.sleep(0.25)

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    print(f"ok    {exe} ran for {seconds}s")
    return True


def main(argv):
    if not 2 <= len(argv) <= 3:
        raise SystemExit(__doc__.strip())
    seconds = int(argv[2]) if len(argv) == 3 else 12
    raise SystemExit(0 if smoke(argv[1], seconds) else 1)


if __name__ == "__main__":
    main(sys.argv)
