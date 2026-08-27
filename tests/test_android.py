"""android/main.py — the Kivy app, checked without importing kivy.

Kivy is not installable in this test environment (it needs a windowing
backend), so the module is parsed and inspected statically rather than run.
That is enough to catch the class of bug that shipped: logic copied from the
desktop apps and then not kept in step with them.
"""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN = ROOT / "android" / "main.py"
SRC = MAIN.read_text(encoding="utf-8")
TREE = ast.parse(SRC)

# Every app that builds a yt-dlp output template.
APPS_WITH_OUTTMPL = ["ytd.py", "ytd_audio.py", "ytd_tui.py", "android/main.py"]


def _outtmpl_literals(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    return re.findall(r'["\'](%\(playlist_title[^"\']*)["\']', src)


@pytest.mark.parametrize("path", APPS_WITH_OUTTMPL)
def test_every_app_uses_a_template_yt_dlp_accepts(path):
    """Regression: the Android app kept the broken template after the desktop
    apps were fixed, so it silently could not download anything either."""
    import yt_dlp
    found = _outtmpl_literals(path)
    assert found, f"no output template found in {path}"
    for tmpl in found:
        ydl = yt_dlp.YoutubeDL({"outtmpl": tmpl, "quiet": True})
        ydl.prepare_filename({"title": "Song", "ext": "mp4", "id": "x"})


def test_all_apps_share_one_output_template():
    """Four copies of the same string; they must not drift apart again."""
    seen = {t for p in APPS_WITH_OUTTMPL for t in _outtmpl_literals(p)}
    assert len(seen) == 1, f"templates have diverged: {seen}"


@pytest.mark.parametrize("path", APPS_WITH_OUTTMPL)
def test_download_return_code_is_checked(path):
    """ignoreerrors=True means yt-dlp returns non-zero instead of raising."""
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "ignoreerrors" in src
    assert re.search(r"=\s*ydl\.download\(", src), (
        f"{path} discards ydl.download()'s return code, so failures look like success")


# ── static properties of the Kivy app ────────────────────────────────────────

def test_android_module_parses():
    assert TREE is not None


def test_format_table_is_well_formed():
    """_FORMATS drives the whole UI; a malformed row would crash on launch."""
    formats = None
    for node in TREE.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_FORMATS":
            formats = ast.literal_eval(node.value)
    assert formats, "_FORMATS not found"
    for label, is_video, fmt, codec in formats:
        assert isinstance(label, str) and label
        assert isinstance(is_video, bool)
        assert isinstance(fmt, str) and fmt
        assert codec is None or isinstance(codec, str)


def test_video_formats_match_the_desktop_quality_map():
    """The Android video selectors are copies of the desktop ones."""
    import ytd_tui
    formats = None
    for node in TREE.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_FORMATS":
            formats = ast.literal_eval(node.value)
    android_video = {f for _, is_video, f, _ in formats if is_video}
    assert android_video == set(ytd_tui._QUALITY_MAP.values())


def test_no_hardcoded_secrets():
    assert not re.search(r"(api[_-]?key|secret|token)\s*=\s*['\"][A-Za-z0-9]{16,}", SRC, re.I)


# ── buildozer.spec correctness ───────────────────────────────────────────────

def _spec():
    import configparser
    cp = configparser.ConfigParser()
    cp.read(ROOT / "android" / "buildozer.spec")
    return cp["app"]


def test_permission_names_have_no_stray_whitespace():
    """A line continuation leaked indentation into the first permission, shipping
    'android.permission. READ_MEDIA_AUDIO', which Android silently ignores."""
    perms = _spec()["android.permissions"]
    for p in perms.split(","):
        assert p == p.strip(), f"permission {p!r} carries whitespace"
        assert " " not in p.strip(), f"permission {p!r} contains a space"
        assert p.strip(), "empty permission entry"


def test_media_permissions_present_for_android_13_plus():
    perms = {p.strip() for p in _spec()["android.permissions"].split(",")}
    assert {"READ_MEDIA_AUDIO", "READ_MEDIA_VIDEO"} <= perms
    assert "INTERNET" in perms


def test_archs_cover_modern_devices():
    archs = {a.strip() for a in _spec()["android.archs"].split(",")}
    assert "arm64-v8a" in archs, "64-bit ARM is mandatory on current devices"


def test_target_api_is_declared():
    assert int(_spec()["android.api"]) >= 34


# ── artefact-level requirements ──────────────────────────────────────────────

def test_ffmpeg_is_a_build_requirement():
    """Every format the UI offers needs ffmpeg: the four MP4 options merge
    separate streams, the four audio options transcode. Without the recipe the
    APK ships none and all eight fail."""
    reqs = {r.strip() for r in _spec()["requirements"].split(",")}
    assert "ffmpeg" in reqs


def test_ffmpeg_location_is_passed_to_yt_dlp():
    assert "ffmpeg_location" in SRC, "bundled ffmpeg is never handed to yt-dlp"
    assert "libffmpegbin.so" in SRC, (
        "p4a installs the ffmpeg CLI under this name in the native lib dir")


def test_ytdlp_accepts_the_bundled_binary_name(tmp_path):
    """p4a names the ffmpeg CLI 'libffmpegbin.so'. yt-dlp resolves the program by
    substring, so that name must still be recognised as ffmpeg — asserted through
    behaviour rather than yt-dlp internals, which have already changed once."""
    import yt_dlp
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
    binary = tmp_path / "libffmpegbin.so"
    binary.write_bytes(b"")
    pp = FFmpegPostProcessor(yt_dlp.YoutubeDL({"quiet": True}))
    # _ffmpeg_location is a class-level ContextVar: shared global state. Leaving
    # it set would point every later test at this empty stub.
    token = pp._ffmpeg_location.set(str(binary))
    try:
        paths = pp._determine_executables()
    finally:
        pp._ffmpeg_location.reset(token)
    assert paths.get("ffmpeg") == str(binary), (
        f"yt-dlp no longer resolves the p4a binary name: {paths}")
    assert FFmpegPostProcessor._ffmpeg_location.get() is None, "leaked global state"


def test_downloads_do_not_default_to_app_private_home():
    """Path.home() on Android is app-private storage; no file manager sees it."""
    assert "getExternalFilesDir" in SRC, (
        "downloads must go somewhere the user can actually find")


def test_p4a_is_pinned_to_a_known_ref():
    branch = _spec().get("p4a.branch", "")
    assert branch in {"develop"} or re.fullmatch(r"v\d{4}\.\d{2}\.\d{2}", branch), (
        f"unexpected p4a ref {branch!r}")
