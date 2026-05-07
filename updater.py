"""Network-only update logic — no Qt imports here."""
import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request

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


def _find_asset(assets, app_slug):
    suffix = _platform_suffix()
    for asset in assets:
        n = asset["name"]
        if app_slug in n and n.endswith(suffix):
            return asset["browser_download_url"], n
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
            return tag, dl_url, name, data["html_url"]
    except Exception:
        pass
    return None, None, None, None


def download_file(url, dest, progress_cb=None):
    def _hook(block, block_size, total):
        if progress_cb and total > 0:
            progress_cb(min(100, block * block_size * 100 // total))
    urllib.request.urlretrieve(url, dest, _hook)


def launch_installer(path):
    if sys.platform == "win32":
        subprocess.Popen([path, "/S"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["pkexec", "dpkg", "-i", path])
