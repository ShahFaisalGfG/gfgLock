# test_app.py - unit tests for gfglock.app: command-line handling and the version it shows

import os
import tempfile
import tomllib

from gfglock import app
from gfglock.config.defaults import AppInfo

_PYPROJECT = os.path.join(os.path.dirname(__file__), os.pardir, "pyproject.toml")


def test_app_version_matches_pyproject():
    """The window title and About screen show AppInfo's version; releases are named from pyproject."""
    with open(_PYPROJECT, "rb") as fh:
        assert AppInfo.APP_VERSION == tomllib.load(fh)["project"]["version"]


class TestShellListFile:
    """Only the Explorer extension's own list file is deleted after an "@file" launch."""

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
        assert app._parse_paths([f"@{listing}"]) == [str(target)]
        assert listing.exists()
