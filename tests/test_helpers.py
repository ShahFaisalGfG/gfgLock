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


class TestCpuThreadCount:
    """get_cpu_thread_count must reflect os.cpu_count(), defaulting to 0 when unknown."""

    def test_returns_reported_count(self, monkeypatch):
        """A known CPU count from os.cpu_count() must be returned unchanged."""
        monkeypatch.setattr(helpers.os, "cpu_count", lambda: 8)
        assert helpers.get_cpu_thread_count() == 8

    def test_returns_zero_when_unknown(self, monkeypatch):
        """os.cpu_count() returning None must map to 0, not None."""
        monkeypatch.setattr(helpers.os, "cpu_count", lambda: None)
        assert helpers.get_cpu_thread_count() == 0


class TestClampThreads:
    """clamp_threads must keep the thread count within [1, cpu_count - 1]."""

    def test_invalid_values_default_to_one(self):
        """Zero, negative, and non-int inputs must all clamp down to 1."""
        assert helpers.clamp_threads(0) == 1
        assert helpers.clamp_threads(-5) == 1
        assert helpers.clamp_threads("3") == 1  # type: ignore[arg-type]

    def test_clamps_to_cpu_count_minus_one(self, monkeypatch):
        """A request above the safe maximum must be capped at cpu_count() - 1."""
        monkeypatch.setattr(helpers, "cpu_count", lambda: 4)
        assert helpers.clamp_threads(10) == 3

    def test_passes_through_within_range(self, monkeypatch):
        """A request within the safe range must be returned unchanged."""
        monkeypatch.setattr(helpers, "cpu_count", lambda: 4)
        assert helpers.clamp_threads(2) == 2

    def test_falls_back_to_one_when_cpu_count_raises(self, monkeypatch):
        """If cpu_count() itself fails, the safe maximum must fall back to 1."""
        def raiser():
            raise OSError("no cpu info")
        monkeypatch.setattr(helpers, "cpu_count", raiser)
        assert helpers.clamp_threads(5) == 1


class TestFormatDuration:
    """format_duration must render seconds as seconds/minutes/hours, human-readable."""

    def test_under_a_minute(self):
        """Durations under 60 seconds render as plain seconds."""
        assert helpers.format_duration(45) == "45 seconds"
        assert helpers.format_duration(0) == "0 seconds"

    def test_minutes_and_seconds(self):
        """Durations under an hour render as minutes plus remainder seconds."""
        assert helpers.format_duration(125) == "2 mins 5 sec"

    def test_hours_minutes_seconds(self):
        """Durations of an hour or more render as hours, minutes, and seconds."""
        assert helpers.format_duration(3665) == "1 hrs 1 mins 5 sec"

    def test_truncates_fractional_seconds(self):
        """Fractional seconds must be truncated, not rounded."""
        assert helpers.format_duration(59.9) == "59 seconds"


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


class TestFormatTime:
    """format_time must render a duration as zero-padded HH:MM:SS."""

    def test_zero(self):
        """Zero seconds renders as 00:00:00."""
        assert helpers.format_time(0) == "00:00:00"

    def test_seconds_only(self):
        """Sub-minute durations still show zero-padded hours and minutes."""
        assert helpers.format_time(59) == "00:00:59"

    def test_full_hms(self):
        """A duration spanning hours, minutes, and seconds must split correctly."""
        assert helpers.format_time(3661) == "01:01:01"


class TestChooseScale:
    """choose_scale must pick a divisor keeping the scaled total inside a signed int32."""

    MAX_INT32 = 2_147_483_647

    def test_small_value_uses_byte_scale(self):
        """Values already within int32 range must use scale 1 and unit 'B'."""
        scale, unit, scaled = helpers.choose_scale(500)
        assert (scale, unit, scaled) == (1, "B", 500)

    def test_large_value_scales_down_within_int32(self):
        """A value above int32 range must be scaled down until it fits."""
        total = self.MAX_INT32 + 1_000_000
        scale, unit, scaled = helpers.choose_scale(total)
        assert scale in (1, 1024, 1024 ** 2, 1024 ** 3, 1024 ** 4)
        assert unit in ("B", "KB", "MB", "GB", "TB")
        assert scaled <= self.MAX_INT32

    def test_extreme_value_stops_at_terabytes(self):
        """A total too large to fit even after 4 divisions must stop at TB, not crash."""
        scale, unit, scaled = helpers.choose_scale(10 ** 30)
        assert unit == "TB"
        assert scale == 1024 ** 4
        assert isinstance(scaled, int)


class TestCalculateFilesTotalSize:
    """calculate_files_total_size must sum only existing regular files."""

    def test_sums_existing_files(self, tmp_path):
        """Two real files' sizes must be added together correctly."""
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"x" * 10)
        b.write_bytes(b"y" * 20)
        assert helpers.calculate_files_total_size([str(a), str(b)]) == 30

    def test_skips_missing_paths(self, tmp_path):
        """A nonexistent path must be silently skipped, not raise."""
        a = tmp_path / "a.bin"
        a.write_bytes(b"z" * 5)
        missing = str(tmp_path / "does_not_exist.bin")
        assert helpers.calculate_files_total_size([str(a), missing]) == 5

    def test_skips_directories(self, tmp_path):
        """A directory path must be excluded from the size total."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        assert helpers.calculate_files_total_size([str(sub)]) == 0

    def test_empty_list(self):
        """An empty list must total to zero."""
        assert helpers.calculate_files_total_size([]) == 0


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

    def test_keeps_stem_when_not_randomized(self):
        """encrypt_name=False must keep the original stem and swap the extension."""
        result = helpers.generate_encrypted_name("/some/dir/report.txt", False, ".gfglock")
        assert result == "report.gfglock"

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
