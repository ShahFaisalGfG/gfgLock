import os
import re

import pytest

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


class TestPredictEncryptedSize:
    """predict_encrypted_size must add the exact per-mode metadata overhead."""

    def test_gcm_overhead(self, tmp_path):
        """GCM mode overhead is salt+nonce+tag+chunk_field+null = 49 bytes."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"x" * 100)
        expected = 100 + len(b"file.txt") + 49
        assert helpers.predict_encrypted_size(str(f), "GCM") == expected

    def test_cfb_overhead(self, tmp_path):
        """CFB mode overhead is salt+iv+chunk_field+null = 37 bytes."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"x" * 100)
        expected = 100 + len(b"file.txt") + 37
        assert helpers.predict_encrypted_size(str(f), "CFB") == expected

    def test_chacha_overhead_matches_gcm(self, tmp_path):
        """CHACHA mode shares the same 49-byte overhead as GCM."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"x" * 100)
        expected = 100 + len(b"file.txt") + 49
        assert helpers.predict_encrypted_size(str(f), "CHACHA") == expected

    def test_mode_is_case_insensitive(self, tmp_path):
        """Lowercase mode strings must be normalized the same as uppercase."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"x" * 10)
        assert helpers.predict_encrypted_size(str(f), "gcm") == helpers.predict_encrypted_size(str(f), "GCM")

    def test_unknown_mode_raises(self, tmp_path):
        """An unsupported mode string must raise ValueError."""
        f = tmp_path / "file.txt"
        f.write_bytes(b"x")
        with pytest.raises(ValueError):
            helpers.predict_encrypted_size(str(f), "ROT13")


class TestDeriveKey:
    """derive_key must deterministically derive a 256-bit key from password and salt."""

    def test_key_length_is_256_bits(self):
        """The derived key must be exactly 32 bytes long."""
        key = helpers.derive_key("password", b"0" * 16, iterations=1000)
        assert len(key) == 32

    def test_deterministic_for_same_inputs(self):
        """Identical password, salt, and iterations must derive the same key."""
        key1 = helpers.derive_key("password", b"salt1234salt1234", iterations=1000)
        key2 = helpers.derive_key("password", b"salt1234salt1234", iterations=1000)
        assert key1 == key2

    def test_different_salt_changes_key(self):
        """Changing the salt must change the derived key."""
        key1 = helpers.derive_key("password", b"a" * 16, iterations=1000)
        key2 = helpers.derive_key("password", b"b" * 16, iterations=1000)
        assert key1 != key2

    def test_different_password_changes_key(self):
        """Changing the password must change the derived key."""
        key1 = helpers.derive_key("password1", b"0" * 16, iterations=1000)
        key2 = helpers.derive_key("password2", b"0" * 16, iterations=1000)
        assert key1 != key2


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
