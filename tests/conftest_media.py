"""Shared fixtures for integration tests that really download something."""
import functools
import http.server
import os
import shutil
import subprocess
import threading

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory):
    """A directory holding a tiny real mp4, generated with ffmpeg."""
    if not HAS_FFMPEG:
        # Skipping locally is fine; skipping in CI would quietly delete the
        # only tests that download anything.
        if os.environ.get("CI"):
            pytest.fail("ffmpeg missing in CI — integration tests would be skipped")
        pytest.skip("ffmpeg not installed")
    d = tmp_path_factory.mktemp("media")
    out = d / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=128x96:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", "-y", str(out)],
        check=True,
    )
    # a second file used for playlist-ish / archive tests
    shutil.copy(out, d / "clip2.mp4")
    return d


@pytest.fixture(scope="session")
def media_server(media_dir):
    """Serve media_dir over HTTP on an ephemeral port; yields the base URL."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(media_dir))

    class Quiet(handler.func):
        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(media_dir)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
