# test_app.py - unit tests for gfglock.app: command-line handling, start-up, and the version it shows

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from unittest.mock import MagicMock

import pytest

from gfglock import app
from gfglock.config.defaults import AppInfo
from gfglock.utils.single_instance import LaunchRequest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYPROJECT = os.path.join(_REPO, "pyproject.toml")


@pytest.fixture
def shell_temp(monkeypatch, tmp_path):
    """Make tmp_path the temp folder, where the Explorer extension writes its file lists."""
    monkeypatch.setattr(app.tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def test_app_version_matches_pyproject():
    """The window title and About screen show AppInfo's version; releases are named from pyproject."""
    with open(_PYPROJECT, "rb") as fh:
        assert AppInfo.APP_VERSION == tomllib.load(fh)["project"]["version"]


def test_importing_the_app_leaves_the_engine_to_the_boot_thread():
    """The engine (and its OpenSSL DLL) loads while the splash shows, not before it; multiprocessing isn't used."""
    engine = ["gfglock.core.native_bridge", "gfglock.core.file_ops", "gfglock.core.py_cipher", "multiprocessing"]
    code = f"import json, sys, gfglock.app; print(json.dumps([m for m in {engine!r} if m in sys.modules]))"
    out = subprocess.run([sys.executable, "-c", code], cwd=_REPO, capture_output=True, text=True, check=True,
                         env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}).stdout
    assert json.loads(out.strip().splitlines()[-1]) == []


class TestParseLaunch:
    """Paths arrive exactly as given: a trailing apostrophe must not turn one folder into its sibling."""

    def test_no_arguments_ask_for_nothing(self):
        assert app.parse_launch([]) == LaunchRequest()

    def test_trailing_apostrophe_in_an_argument_is_kept(self, tmp_path):
        folder = tmp_path / "Teachers'"
        folder.mkdir()
        (tmp_path / "Teachers").mkdir()  # the sibling that stripping the apostrophe would pick
        assert app.parse_launch(["encrypt", str(folder)]) == LaunchRequest("encrypt", (str(folder),))

    def test_trailing_apostrophe_in_a_list_file_is_kept(self, tmp_path):
        folder = tmp_path / "Teachers'"
        folder.mkdir()
        (tmp_path / "Teachers").mkdir()
        listing = tmp_path / "list.txt"
        listing.write_bytes(f"{folder}\r\n".encode("utf-8"))
        assert app.parse_launch(["encrypt", f"@{listing}"]).paths == (str(folder),)

    def test_without_a_mode_files_default_to_encrypt(self, tmp_path):
        plain, locked = tmp_path / "a.txt", tmp_path / "b.txt.gfglock"
        plain.write_text("x")
        locked.write_text("x")
        # The window still sends the encrypted file to the Decrypt tab.
        assert app.parse_launch([str(plain), str(locked)]) == LaunchRequest("encrypt", (str(plain), str(locked)))

    def test_mode_is_case_insensitive(self, tmp_path):
        assert app.parse_launch(["DECRYPT", str(tmp_path)]).mode == "decrypt"

    def test_missing_paths_are_counted(self, tmp_path):
        present = tmp_path / "a.txt"
        present.write_text("x")
        request = app.parse_launch(["encrypt", str(present), str(tmp_path / "gone1"), str(tmp_path / "gone2")])
        assert request == LaunchRequest("encrypt", (str(present),), "2 items couldn't be found.")
        assert app.parse_launch(["encrypt", str(tmp_path / "gone")]).notice == "1 item couldn't be found."

    def test_relative_paths_resolve_against_the_launch_folder(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("x")
        monkeypatch.chdir(tmp_path)
        assert app.parse_launch(["encrypt", "a.txt"]).paths == (str(tmp_path / "a.txt"),)

    def test_unquoted_path_split_at_spaces_is_rejoined(self, tmp_path):
        folder = tmp_path / "My Files"
        folder.mkdir()
        assert app.parse_launch(["encrypt", str(tmp_path / "My"), "Files"]).paths == (str(folder),)


class TestListFile:
    """An "@list" argument names a UTF-8 file with one path per line."""

    def test_crlf_lines_and_byte_order_mark_are_read(self, tmp_path):
        first, second = tmp_path / "a.txt", tmp_path / "b c.txt"
        first.write_text("x")
        second.write_text("x")
        listing = tmp_path / "list.txt"
        listing.write_bytes(f"\ufeff{first}\r\n\r\n{second}\n".encode("utf-8"))
        assert app.parse_launch(["encrypt", f"@{listing}"]).paths == (str(first), str(second))

    def test_a_list_that_isnt_utf8_is_reported_instead_of_crashing(self, tmp_path):
        listing = tmp_path / "list.txt"
        listing.write_bytes("C:\\Résumé.docx\r\n".encode("cp1252"))
        assert app.parse_launch(["encrypt", f"@{listing}"]) == LaunchRequest(
            "encrypt", (), "The file list from Explorer couldn't be read.")

    def test_a_missing_list_is_reported(self, tmp_path):
        assert app.parse_launch(["decrypt", f"@{tmp_path / 'gone.tmp'}"]).notice == (
            "The file list from Explorer couldn't be read.")

    def test_extension_list_file_is_recognised(self):
        assert app._is_shell_list_file(os.path.join(tempfile.gettempdir(), "gfgA1F.tmp"))

    def test_other_files_are_not(self, tmp_path):
        assert not app._is_shell_list_file(str(tmp_path / "gfgA1F.tmp"))  # not the temp folder
        assert not app._is_shell_list_file(os.path.join(tempfile.gettempdir(), "notes.txt"))

    def test_list_outside_temp_is_read_but_kept(self, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        listing = tmp_path / "list.txt"
        listing.write_text(f"{target}\n", encoding="utf-8")
        assert app.parse_launch(["encrypt", f"@{listing}"]).paths == (str(target),)
        assert listing.exists()

    def test_extension_list_file_is_deleted_after_reading(self, shell_temp):
        target = shell_temp / "a.txt"
        target.write_text("x")
        listing = shell_temp / "gfgA1F.tmp"
        listing.write_text(f"{target}\n", encoding="utf-8")
        assert app.parse_launch(["encrypt", f"@{listing}"]).paths == (str(target),)
        assert not listing.exists()

    def test_unreadable_extension_list_file_is_deleted_too(self, shell_temp):
        listing = shell_temp / "gfgB2.tmp"
        listing.write_bytes(b"\xff\xfe\x00bad")
        assert app.parse_launch(["encrypt", f"@{listing}"]).notice
        assert not listing.exists()


class TestLaunchFolder:
    """After the arguments are read, nothing may resolve against the folder gfgLock was started in."""

    def test_frozen_app_moves_to_its_own_folder(self, tmp_path, monkeypatch):
        launch_folder = tmp_path / "Downloads"
        launch_folder.mkdir()
        monkeypatch.chdir(launch_folder)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "gfgLock.exe"))
        app._leave_launch_folder()
        assert os.getcwd() == str(tmp_path)

    def test_running_from_source_keeps_the_folder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        app._leave_launch_folder()
        assert os.getcwd() == str(tmp_path)


class TestStartupFailure:
    def test_splash_closes_before_the_error_dialog_and_the_failure_is_logged(self, monkeypatch):
        calls: list[str] = []
        startup = object.__new__(app._Startup)  # no splash window or boot thread
        startup._splash = MagicMock(close=lambda: calls.append("splash closed"))
        startup._app = MagicMock()
        monkeypatch.setattr(app.QMessageBox, "critical", lambda *args: calls.append("dialog"))
        log = MagicMock()
        monkeypatch.setattr(app, "write_log", log)
        startup._on_failed("The user interface failed to load.")
        assert calls == ["splash closed", "dialog"]
        log.assert_called_once_with("Startup failed: The user interface failed to load.", "critical", force=True)
        startup._app.exit.assert_called_once_with(-1)
