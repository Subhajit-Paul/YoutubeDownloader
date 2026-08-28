"""Network-only update logic — no Qt imports here."""
import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from version import GITHUB_REPO, __version__


def _parse_version(tag):
    try:
        return tuple(int(x) for x in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)


def _platform_suffix():
    if sys.platform == "win32":
        return "windows-x86_64-setup.exe"
    if sys.platform == "darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x86_64"
        return f"macos-{arch}.dmg"
    return "linux-x86_64.deb"


def _is_https(url):
    """Release metadata is untrusted input; what we download then execute must be TLS."""
    try:
        return urllib.parse.urlparse(url).scheme == "https"
    except (ValueError, AttributeError):
        return False


def _find_asset(assets, app_slug):
    suffix = _platform_suffix()
    for asset in assets:
        n = asset["name"]
        if app_slug in n and n.endswith(suffix):
            url = asset.get("browser_download_url", "")
            if not _is_https(url):
                continue
            return url, n
    return None, None


def check_update(app_slug):
    """Return (new_tag, download_url, asset_name, release_html_url) or all-None."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "YTD-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        tag = data["tag_name"]
        if _parse_version(tag) > _parse_version(__version__):
            dl_url, name = _find_asset(data["assets"], app_slug)
            # html_url is handed to webbrowser.open(); never open a scheme we
            # were told to (javascript:, file:) — fall back to the known repo.
            html = data.get("html_url", "")
            if not _is_https(html):
                html = f"https://github.com/{GITHUB_REPO}/releases/latest"
            return tag, dl_url, name, html
    except Exception as exc:
        print(f"[updater] check_update failed: {exc}", file=sys.stderr)
    return None, None, None, None


def download_file(url, dest, progress_cb=None):
    if not _is_https(url):
        raise ValueError(f"refusing to download over a non-https URL: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": "YTD-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk = 65536
        with open(dest, "wb") as f:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                downloaded += len(block)
                if progress_cb and total:
                    progress_cb(min(100, downloaded * 100 // total))


def launch_installer(path):
    if sys.platform == "win32":
        subprocess.Popen([path, "/S"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        # Try graphical sudo tools in order; fall back to browser download page
        for tool in ("pkexec", "gksudo", "kdesudo"):
            if shutil.which(tool):
                subprocess.Popen([tool, "dpkg", "-i", path])
                return
        webbrowser.open(
            f"https://github.com/{GITHUB_REPO}/releases/latest"
        )
