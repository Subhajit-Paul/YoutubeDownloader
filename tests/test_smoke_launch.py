"""A live loader-error dialog must never pass the bundle smoke check."""
import pathlib
import subprocess
import sys

import pytest

from tools import smoke_launch


@pytest.mark.parametrize("program,expected,error", [
    ("import time; time.sleep(30)", False, "never reached its UI event loop"),
    ("raise SystemExit('loader failed')", False, "loader failed"),
    ("from common import signal_startup_ready; import time; "
     "print('x' * 1000000, flush=True); "
     "signal_startup_ready(); time.sleep(30)", True, ""),
])
def test_smoke_requires_readiness_and_reaps_child(
        monkeypatch, tmp_path, capsys, program, expected, error):
    real_popen = subprocess.Popen
    children = []

    def launch(args, **kwargs):
        kwargs['env']['PYTHONPATH'] = str(pathlib.Path(__file__).resolve().parent.parent)
        proc = real_popen([sys.executable, '-c', program], **kwargs)
        children.append(proc)
        return proc

    monkeypatch.setattr(smoke_launch, 'executable', lambda bundle: sys.executable)
    monkeypatch.setattr(smoke_launch.subprocess, 'Popen', launch)
    assert smoke_launch.smoke(str(tmp_path), seconds=1) is expected
    assert all(child.poll() is not None for child in children)
    assert error in capsys.readouterr().err


def test_smoke_reports_launch_failure(monkeypatch, tmp_path, capsys):
    def cannot_launch(*args, **kwargs):
        raise OSError('bad executable')

    monkeypatch.setattr(smoke_launch, 'executable', lambda bundle: 'broken.exe')
    monkeypatch.setattr(smoke_launch.subprocess, 'Popen', cannot_launch)
    assert not smoke_launch.smoke(str(tmp_path), seconds=1)
    assert 'bad executable' in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows installer layout')
def test_renamed_install_directory_skips_uninstaller(tmp_path):
    (tmp_path / 'uninstall.exe').touch()
    app = tmp_path / 'youtube-downloader.exe'
    app.touch()
    assert smoke_launch.executable(str(tmp_path)) == str(app)


def test_missing_bundle_fails_cleanly(tmp_path, capsys):
    assert not smoke_launch.smoke(str(tmp_path / 'missing'))
    assert 'no executable inside' in capsys.readouterr().err
