import os
import re
import subprocess
import sys
from pathlib import Path

from gfglock.utils import helpers


class TestResourcePath:
    """resource_path must resolve relative paths against the correct base directory."""

    def test_dev_mode_resolves_against_project_root(self):
        """Without sys._MEIPASS, a known project-root file must be reachable."""
        result = helpers.resource_path("pyproject.toml")
        assert os.path.isfile(result)

    def test_normalizes_path_separators(self):
        """The returned path must be normalized (no redundant separators)."""
        result = helpers.resource_path("a/b/../c.txt")
        assert result == os.path.normpath(result)
        assert result.endswith(os.path.normpath("a/c.txt"))

    def test_frozen_mode_resolves_against_meipass(self, monkeypatch, tmp_path):
        """When sys._MEIPASS is set, paths must resolve relative to it instead."""
        monkeypatch.setattr(helpers.sys, "_MEIPASS", str(tmp_path), raising=False)
        result = helpers.resource_path("assets/icon.ico")
        assert result == os.path.normpath(os.path.join(str(tmp_path), "assets/icon.ico"))


class TestFormatBytes:
    """format_bytes must scale a byte count to the smallest fitting unit."""

    def test_bytes_and_kilobytes(self):
        """Sub-KB and simple KB values render with one decimal place."""
        assert helpers.format_bytes(500) == "500.0 B"
        assert helpers.format_bytes(1024) == "1.0 KB"
        assert helpers.format_bytes(1536) == "1.5 KB"

    def test_scales_up_through_terabytes(self):
        """Large values must keep dividing until they reach the TB/PB range."""
        assert helpers.format_bytes(1024 ** 4) == "1.0 TB"
        assert helpers.format_bytes(1024 ** 5) == "1.0 PB"

    def test_strip_zeros_removes_trailing_point_zero(self):
        """strip_zeros must turn a whole-number reading like '1.0 KB' into '1 KB'."""
        assert helpers.format_bytes(1024, strip_zeros=True) == "1 KB"

    def test_strip_zeros_keeps_significant_decimal(self):
        """strip_zeros must not touch a non-zero decimal like '1.5 KB'."""
        assert helpers.format_bytes(1536, strip_zeros=True) == "1.5 KB"

    def test_zero_bytes(self):
        """Zero must format as a valid, non-crashing byte string."""
        assert helpers.format_bytes(0) == "0.0 B"


class TestGenerateEncryptedName:
    """generate_encrypted_name must produce the on-disk name for an encrypted file."""

    def test_keeps_full_name_when_not_randomized(self):
        """encrypt_name=False must keep the full original name so report.txt and report.pdf can't collide."""
        assert helpers.generate_encrypted_name("/some/dir/report.txt", False, ".gfglock") == "report.txt.gfglock"
        assert helpers.generate_encrypted_name("/some/dir/report.pdf", False, ".gfglock") == "report.pdf.gfglock"

    def test_randomizes_name_when_requested(self):
        """encrypt_name=True must produce a timestamp_hex name hiding the original stem."""
        result = helpers.generate_encrypted_name("/some/dir/report.txt", True, ".gfglock")
        assert re.match(r"^\d{14}_[0-9a-f]{8}\.gfglock$", result)
        assert "report" not in result

    def test_randomized_names_are_unique(self):
        """Two successive randomized names must not collide."""
        first = helpers.generate_encrypted_name("/some/dir/report.txt", True, ".gfglock")
        second = helpers.generate_encrypted_name("/some/dir/report.txt", True, ".gfglock")
        assert first != second


class TestStartupImports:
    """gfglock.app imports helpers before the splash shows, so helpers must not load the engines."""

    def test_helpers_leave_the_native_module_unloaded(self):
        code = ("import sys, gfglock.utils.helpers; "
                "print(sorted(m for m in ('gfglock_native', 'gfglock.core.native_bridge') if m in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent,
                              capture_output=True, text=True, check=True)
        assert done.stdout.strip() == "[]"
