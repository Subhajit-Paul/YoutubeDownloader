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
