import importlib.util
import os
import shutil
import sys


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_ffmpeg_location():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return None


def check_ffmpeg_available():
    if hasattr(sys, '_MEIPASS'):
        return any(
            os.path.exists(os.path.join(sys._MEIPASS, n))
            for n in ('ffmpeg', 'ffmpeg.exe')
        )
    return shutil.which('ffmpeg') is not None


def lazy_import(name):
    """Import `name` but defer executing it until an attribute is touched.

    yt-dlp costs ~64 ms of a ~120 ms cold start and is not needed until a
    download actually begins, so paying for it before the window is on screen
    is wasted latency. Returns None when the module is absent, matching the
    try/except ImportError the callers already handle.
    """
    if name in sys.modules:
        return sys.modules[name]
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or spec.loader is None:
        return None
    spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        return None
    return module


# ── User-facing errors ────────────────────────────────────────────────────────
# yt-dlp reports failures as extractor strings ("ERROR: [youtube] dQw4w9WgXcQ:
# Video unavailable"). Both front-ends put that straight in front of the user,
# which says what broke but never what to do about it — and the two most common
# failures (bot checks and 403s) have the same one-click fix nobody was told
# about. Recognised failures become a sentence plus the next step; anything
# unrecognised is cleaned up and passed through rather than guessed at.

_ERROR_HINTS = (
    ("sign in to confirm",   "YouTube wants to verify this request. Choose your "
                             "browser under “Cookies from browser” and try again."),
    ("http error 403",       "YouTube refused the request. Choosing your browser "
                             "under “Cookies from browser” usually fixes this."),
    ("http error 429",       "YouTube is rate-limiting this connection. Wait a few "
                             "minutes and try again."),
    ("private video",        "This video is private, so it can’t be downloaded."),
    ("members-only",         "This video is for channel members only."),
    ("video unavailable",    "YouTube says this video is unavailable — it may be "
                             "deleted, private or blocked in your region."),
    ("unsupported url",      "That link isn’t one this app can read. Paste a video, "
                             "playlist or channel URL."),
    ("is not a valid url",   "That doesn’t look like a link. Paste a video, playlist "
                             "or channel URL."),
    ("name resolution",      "No connection — that address couldn’t be looked up. "
                             "Check your network and try again."),
    ("timed out",            "The connection timed out. Check your network and try "
                             "again."),
    ("connection reset",     "The connection dropped. Try again."),
    ("connection refused",   "The connection was refused. Check your network and try "
                             "again."),
    ("no space left",        "The disk is full. Free some space and try again."),
    ("permission denied",    "That save folder can’t be written to. Choose another "
                             "folder."),
    ("read-only file system", "That save folder is read-only. Choose another folder."),
    ("ffprobe",              "ffmpeg is needed to finish this download and wasn’t "
                             "found. Install it and try again."),
    ("ffmpeg",               "ffmpeg is needed to finish this download and wasn’t "
                             "found. Install it and try again."),
)


def friendly_error(raw):
    """A sentence the user can act on, from a raw yt-dlp/OS error string.

    Ordered longest-lived cause first: a bot check also mentions "sign in", and
    a 403 also mentions "http error", so the specific needles must be tested
    before the general ones.
    """
    text = (raw or "").strip()
    if not text:
        return "Something went wrong. Try again."
    lowered = text.lower()
    for needle, message in _ERROR_HINTS:
        if needle in lowered:
            return message
    # Unrecognised: show what yt-dlp said, minus its prefix and traceback tail.
    first = text.split("\n")[0]
    for prefix in ("ERROR: ", "error: "):
        if first.startswith(prefix):
            first = first[len(prefix):]
    return first[:160]


def save_path_problem(path):
    """Why this folder cannot be downloaded into, or None if it can.

    yt-dlp creates missing directories, so a path that does not exist yet is
    fine — what matters is whether the nearest existing ancestor can be written
    to. The GUI used to find this out only after a metadata fetch and a failed
    write, and reported it as whatever yt-dlp happened to say.
    """
    path = (path or "").strip()
    if not path:
        return "Choose a folder to save into."

    probe = os.path.abspath(os.path.expanduser(path))
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:            # walked to the root without finding one
            return "That folder path isn’t valid."
        probe = parent

    if not os.path.isdir(probe):
        return "That’s a file, not a folder."
    if not os.access(probe, os.W_OK | os.X_OK):
        return "That folder can’t be written to. Choose another."
    return None
