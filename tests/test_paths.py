# test_paths.py - unit tests for gfglock.utils.paths: where settings and logs are kept

import os
import sys

import pytest

from gfglock.utils import paths


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    """Each test resolves the data folder anew, with APPDATA inside tmp_path."""
    monkeypatch.setattr(paths, "_data_dir", paths._UNSET)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def _frozen(monkeypatch, exe_dir, onefile: bool):
    """Pretend to be a PyInstaller build: one-file unpacks to a temp folder, one-folder to _internal."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", os.path.join(str(exe_dir), "gfgLock.exe"))
    bundle = os.path.join(str(exe_dir), "temp", "_MEI1234") if onefile else os.path.join(str(exe_dir), "_internal")
    monkeypatch.setattr(sys, "_MEIPASS", bundle, raising=False)


def test_running_from_source_has_no_data_folder():
    assert paths.data_dir() is None


def test_installed_app_uses_appdata(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path / "Program Files" / "gfgLock", onefile=False)
    assert not paths.is_portable()
    assert paths.data_dir() == os.path.join(str(tmp_path / "appdata"), "gfgLock")
    assert os.path.isdir(paths.data_dir())


def test_portable_exe_keeps_its_data_next_to_itself(monkeypatch, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    _frozen(monkeypatch, usb, onefile=True)
    assert paths.is_portable()
    assert paths.data_dir() == os.path.join(str(usb), paths.PORTABLE_FOLDER)
    assert os.listdir(paths.data_dir()) == []  # the write test leaves nothing behind


def test_portable_first_start_takes_over_earlier_settings(monkeypatch, tmp_path):
    old = tmp_path / "appdata" / "gfgLock"
    old.mkdir(parents=True)
    (old / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    usb = tmp_path / "usb"
    usb.mkdir()
    _frozen(monkeypatch, usb, onefile=True)
    copied = os.path.join(paths.data_dir(), "settings.json")
    assert open(copied, encoding="utf-8").read() == '{"theme": "dark"}'


def test_portable_on_a_read_only_drive_falls_back_to_appdata(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path / "cd", onefile=True)
    monkeypatch.setattr(paths, "_writable", lambda folder: False)
    assert paths.data_dir() == os.path.join(str(tmp_path / "appdata"), "gfgLock")
