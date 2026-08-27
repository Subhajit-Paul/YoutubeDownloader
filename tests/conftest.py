"""Shared test setup.

Qt must be told to use the offscreen platform before PyQt5 is imported, or
importing the GUI modules aborts on a headless CI runner.
"""
import os
import sys
import pathlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest_plugins = ["tests.conftest_media"]


def pytest_addoption(parser):
    parser.addoption(
        "--url",
        default="https://www.youtube.com/watch?v=CXkjMNHOBQI",
        help="YouTube URL for the live network matrix (-m network)",
    )
