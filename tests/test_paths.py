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
    folder = paths.data_dir()
    assert folder == os.path.join(str(tmp_path / "appdata"), "gfgLock")
    assert folder is not None and os.path.isdir(folder)


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
    folder = paths.data_dir()
    assert folder is not None
    with open(os.path.join(folder, "settings.json"), encoding="utf-8") as copied:
        assert copied.read() == '{"theme": "dark"}'


def test_one_folder_build_with_the_marker_is_portable(monkeypatch, tmp_path):
    """The portable .7z ships the one-folder build with gfgLock-portable.txt next to the exe."""
    usb = tmp_path / "usb" / "gfgLock"
    usb.mkdir(parents=True)
    (usb / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    _frozen(monkeypatch, usb, onefile=False)
    assert paths.is_portable()
    assert paths.data_dir() == os.path.join(str(usb), paths.PORTABLE_FOLDER)


def test_marker_elsewhere_doesnt_make_the_installed_app_portable(monkeypatch, tmp_path):
    install = tmp_path / "Program Files" / "gfgLock"
    (install / "_internal").mkdir(parents=True)
    (install / "_internal" / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    _frozen(monkeypatch, install, onefile=False)
    assert not paths.is_portable()


class TestAppFolder:
    """The folder of the app's own files, which encrypting leaves alone."""

    def test_one_folder_build_is_its_install_folder(self, monkeypatch, tmp_path):
        install = tmp_path / "Program Files" / "gfgLock"
        _frozen(monkeypatch, install, onefile=False)
        assert paths.app_folder() == str(install)

    def test_one_file_exe_is_its_unpack_folder_not_downloads(self, monkeypatch, tmp_path):
        downloads = tmp_path / "Downloads"
        _frozen(monkeypatch, downloads, onefile=True)
        assert paths.app_folder() == os.path.join(str(downloads), "temp", "_MEI1234")

    def test_running_from_source_has_none(self):
        assert paths.app_folder() is None


def test_running_from_source_ignores_the_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    (tmp_path / paths.PORTABLE_MARKER).write_text("", encoding="utf-8")
    assert not paths.is_portable()


def test_portable_on_a_read_only_drive_falls_back_to_appdata(monkeypatch, tmp_path):
    _frozen(monkeypatch, tmp_path / "cd", onefile=True)
    monkeypatch.setattr(paths, "_writable", lambda folder: False)
    assert paths.data_dir() == os.path.join(str(tmp_path / "appdata"), "gfgLock")
