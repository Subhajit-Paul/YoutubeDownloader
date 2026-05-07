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
