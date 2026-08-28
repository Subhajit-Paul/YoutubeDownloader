"""Security properties.

The update path is the sharp edge: the app downloads a file over the network
and then executes it — on Linux through pkexec, i.e. as root. Everything that
feeds that path is treated as untrusted here.
"""
import os
import pathlib
import re
import subprocess
import sys

import pytest

import updater

pytestmark = pytest.mark.security

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = sorted(ROOT.glob("*.py")) + [ROOT / "android" / "main.py"]


def _src(p):
    return p.read_text(encoding="utf-8")


# ── static properties ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_shell_true_subprocess(path):
    assert "shell=True" not in _src(path)


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_tls_verification_is_never_disabled(path):
    src = _src(path)
    for bad in ("_create_unverified_context", "CERT_NONE",
                "check_hostname = False", "verify=False"):
        assert bad not in src, f"{path.name} weakens TLS with {bad}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_dynamic_code_execution(path):
    src = _src(path)
    assert not re.search(r"\beval\s*\(", src)
    assert not re.search(r"\bexec\s*\(", src)


def test_update_endpoint_is_https():
    assert "https://api.github.com" in _src(ROOT / "updater.py")
    assert "http://" not in _src(ROOT / "updater.py")


def test_installer_is_launched_without_a_shell():
    """Popen must take a list; a string would go through the shell on some paths."""
    src = _src(ROOT / "updater.py")
    for call in re.findall(r"subprocess\.Popen\((.*?)\)", src, re.S):
        assert call.lstrip().startswith("["), f"Popen not given a list: {call!r}"


# ── untrusted release metadata ───────────────────────────────────────────────

MALICIOUS_ASSETS = [
    {"name": "youtube-downloader-linux-x86_64.deb",
     "browser_download_url": "http://evil.example/payload.deb"},
]


def test_plain_http_download_url_is_rejected(monkeypatch):
    """A downgraded URL in the release metadata must not be downloaded."""
    monkeypatch.setattr(updater.sys, "platform", "linux")
    url, name = updater._find_asset(MALICIOUS_ASSETS, "youtube-downloader")
    assert url is None, "http:// download URL was accepted"


@pytest.mark.parametrize("scheme", ["http://", "javascript:", "file://", "ftp://"])
def test_non_https_release_page_is_rejected(monkeypatch, scheme):
    """html_url is opened in a browser — it must be https, not javascript:."""
    import json
    import io

    class R(io.BytesIO):
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    payload = json.dumps({
        "tag_name": "v9.9.9",
        "assets": [],
        "html_url": f"{scheme}evil.example/x",
    }).encode()
    monkeypatch.setattr(updater, "__version__", "1.1.1")
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: R(payload))
    tag, url, name, html = updater.check_update("youtube-downloader")
    assert html.startswith("https://github.com/"), (
        f"{scheme} release page was passed through to webbrowser.open: {html!r}")


def test_download_file_refuses_non_https(tmp_path):
    with pytest.raises(ValueError):
        updater.download_file("http://evil.example/x.deb", str(tmp_path / "o"))


# ── filesystem safety ────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "../../../../etc/cron.d/pwned",
    "..\\..\\..\\Windows\\System32\\evil",
    "/etc/passwd",
    "a/b/c",
])
def test_hostile_video_title_cannot_escape_the_save_directory(title):
    """The title comes from the remote site; it must not steer the output path."""
    import yt_dlp
    import ytd
    import ytd_core
    from unittest import mock

    class Rec:
        def __call__(self, opts):
            self.opts = opts
            return self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def download(self, urls): return 0

    rec = Rec()
    w = ytd.DownloadWorker("https://x/1", "/tmp/dl", "Best")
    with mock.patch.object(ytd_core.yt_dlp, "YoutubeDL", rec):
        w.run()

    ydl = yt_dlp.YoutubeDL({"outtmpl": rec.opts["outtmpl"], "quiet": True})
    out = pathlib.Path(ydl.prepare_filename(
        {"title": title, "ext": "mp4", "id": "x"})).resolve()
    base = pathlib.Path("/tmp/dl").resolve()
    assert base in out.parents or out.parent == base, (
        f"title {title!r} escaped the save directory: {out}")


def test_cookies_are_not_read_unless_the_user_opts_in():
    """Browser cookie extraction reads credentials — it must never be implicit."""
    from unittest import mock
    import ytd
    import ytd_core

    class Rec:
        def __call__(self, opts):
            self.opts = opts
            return self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def download(self, urls): return 0

    for browser in (None, "", "None"):
        rec = Rec()
        w = ytd.DownloadWorker("https://x/1", "/tmp/dl", "Best", browser=browser)
        with mock.patch.object(ytd_core.yt_dlp, "YoutubeDL", rec):
            w.run()
        assert "cookiesfrombrowser" not in rec.opts


# ── installer script ─────────────────────────────────────────────────────────

def test_install_script_uses_https_only():
    src = _src(ROOT / "install-tui.sh")
    assert "http://" not in src


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell script")
def test_install_script_cannot_be_tricked_into_writing_outside_its_targets(tmp_path):
    """A malicious release tarball must not drop files elsewhere on disk."""
    import io
    import tarfile

    victim = tmp_path / "victim"
    victim.mkdir()
    tarball = tmp_path / "evil.tar.gz"

    payload = b"#!/bin/sh\ntrue\n"
    evil = b"pwned"
    with tarfile.open(tarball, "w:gz") as tf:
        ti = tarfile.TarInfo("youtube-tui")
        ti.size, ti.mode = len(payload), 0o755
        tf.addfile(ti, io.BytesIO(payload))
        # absolute path and traversal members, the two classic tar escapes
        for name in (str(victim / "pwned.txt"), "../../victim/escaped.txt"):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode = len(evil), 0o644
            tf.addfile(ti, io.BytesIO(evil))

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "curl").write_text(
        f'#!/bin/sh\nfor a; do case "$a" in -o) shift; cp "{tarball}" "$1"; exit 0;; esac; done\nexit 1\n')
    (fake / "uname").write_text(
        '#!/bin/sh\n[ "$1" = "-m" ] && echo x86_64 || echo Linux\n')
    for f in ("curl", "uname"):
        (fake / f).chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    subprocess.run(
        ["bash", str(ROOT / "install-tui.sh")],
        env={**os.environ, "PATH": f"{fake}:/usr/bin:/bin", "HOME": str(home),
             "SHELL": "/bin/bash"},
        capture_output=True, timeout=120)

    assert not (victim / "pwned.txt").exists(), "absolute-path member escaped"
    assert not (victim / "escaped.txt").exists(), "traversal member escaped"
