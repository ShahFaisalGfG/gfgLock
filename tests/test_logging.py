import os
import re

import pytest

from gfglock.utils import logging as log_mod

_SEP_PATTERN = re.compile(r"^─{68}\n\n$")


class TestGetLogsDir:
    """get_logs_dir must resolve to the frozen-app data directory and create it."""

    def test_frozen_uses_appdata(self, monkeypatch, tmp_path):
        """When frozen, logs dir must be <APPDATA>/gfgLock/logs and must exist on disk."""
        monkeypatch.setattr(log_mod.sys, "frozen", True, raising=False)
        monkeypatch.setenv("APPDATA", str(tmp_path))
        result = log_mod.get_logs_dir()
        assert result == os.path.join(str(tmp_path), "gfgLock", "logs")
        assert os.path.isdir(result)

    def test_frozen_without_appdata_falls_back_to_home(self, monkeypatch, tmp_path):
        """Missing APPDATA must fall back to the user home directory."""
        monkeypatch.setattr(log_mod.sys, "frozen", True, raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(log_mod.os.path, "expanduser", lambda _p: str(tmp_path))
        result = log_mod.get_logs_dir()
        assert result == os.path.join(str(tmp_path), "gfgLock", "logs")


class TestLogFilePaths:
    """get_critical_log_file / get_general_log_file must name files under the logs dir."""

    def test_critical_log_file_name(self, monkeypatch, tmp_path):
        """The critical log file must be named gfglock_critical.log."""
        monkeypatch.setattr(log_mod, "get_logs_dir", lambda: str(tmp_path))
        result = log_mod.get_critical_log_file()
        assert result == os.path.join(str(tmp_path), "gfglock_critical.log")

    def test_general_log_file_name(self, monkeypatch, tmp_path):
        """The general log file must be named gfglock_full_activity.log."""
        monkeypatch.setattr(log_mod, "get_logs_dir", lambda: str(tmp_path))
        result = log_mod.get_general_log_file()
        assert result == os.path.join(str(tmp_path), "gfglock_full_activity.log")


class TestWriteCriticalLog:
    """write_critical_log must append a timestamped line to the critical log file."""

    def test_appends_timestamped_entry(self, monkeypatch, tmp_path):
        """A single write must produce one timestamped line with the message."""
        target = tmp_path / "critical.log"
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(target))
        assert log_mod.write_critical_log("hello") is True
        content = target.read_text(encoding="utf-8")
        assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] hello\n$", content)

    def test_appends_multiple_entries(self, monkeypatch, tmp_path):
        """Successive writes must append rather than overwrite."""
        target = tmp_path / "critical.log"
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(target))
        log_mod.write_critical_log("first")
        log_mod.write_critical_log("second")
        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert lines[0].endswith("first")
        assert lines[1].endswith("second")

    def test_returns_false_on_write_failure(self, monkeypatch, tmp_path):
        """An unwritable path must return False instead of raising."""
        bad_path = str(tmp_path / "missing_dir" / "critical.log")
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: bad_path)
        assert log_mod.write_critical_log("hello") is False


class TestWriteGeneralLog:
    """write_general_log must append a timestamped line to the general log file."""

    def test_appends_timestamped_entry(self, monkeypatch, tmp_path):
        """A single write must produce one timestamped line with the message."""
        target = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(target))
        assert log_mod.write_general_log("world") is True
        content = target.read_text(encoding="utf-8")
        assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] world\n$", content)


class TestWriteLog:
    """write_log must respect the enable_logs flag and the log_level setting."""

    def test_disabled_returns_false(self, monkeypatch):
        """When logging is disabled, write_log must not write anything."""
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": False}})
        assert log_mod.write_log("msg") is False

    def test_critical_level_always_writes_when_enabled(self, monkeypatch, tmp_path):
        """A critical-level message must write regardless of the log_level setting."""
        target = tmp_path / "critical.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "critical"}})
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(target))
        assert log_mod.write_log("boom", level="critical") is True
        assert "boom" in target.read_text(encoding="utf-8")

    def test_general_level_skipped_when_log_level_critical(self, monkeypatch, tmp_path):
        """A general-level message must be skipped when log_level is 'critical'."""
        target = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "critical"}})
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(target))
        assert log_mod.write_log("info", level="general") is False
        assert not target.exists()

    def test_general_level_writes_when_log_level_all(self, monkeypatch, tmp_path):
        """A general-level message must write when log_level is 'all'."""
        target = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "all"}})
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(target))
        assert log_mod.write_log("info", level="general") is True
        assert "info" in target.read_text(encoding="utf-8")

    def test_settings_exception_returns_false(self, monkeypatch):
        """A failure while loading settings must be swallowed, returning False."""
        def raiser():
            raise RuntimeError("settings broken")
        monkeypatch.setattr(log_mod, "load_settings", raiser)
        assert log_mod.write_log("msg") is False


class TestWriteSessionSeparator:
    """write_session_separator must append a divider, gated by the same settings."""

    def test_noop_when_disabled(self, monkeypatch, tmp_path):
        """Disabled logging must leave no separator written anywhere."""
        crit = tmp_path / "critical.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": False}})
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
        log_mod.write_session_separator()
        assert not crit.exists()

    def test_writes_critical_only_by_default(self, monkeypatch, tmp_path):
        """log_level='critical' must write the separator to the critical log only."""
        crit = tmp_path / "critical.log"
        gen = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "critical"}})
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(gen))
        log_mod.write_session_separator()
        assert _SEP_PATTERN.match(crit.read_text(encoding="utf-8"))
        assert not gen.exists()

    def test_writes_both_logs_when_level_all(self, monkeypatch, tmp_path):
        """log_level='all' must write the separator to both log files."""
        crit = tmp_path / "critical.log"
        gen = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "all"}})
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(gen))
        log_mod.write_session_separator()
        assert _SEP_PATTERN.match(crit.read_text(encoding="utf-8"))
        assert _SEP_PATTERN.match(gen.read_text(encoding="utf-8"))


class TestClearLogs:
    """clear_logs must truncate existing log files and leave missing ones alone."""

    def test_truncates_existing_files(self, monkeypatch, tmp_path):
        """Pre-populated log files must be emptied, not deleted."""
        crit = tmp_path / "critical.log"
        gen = tmp_path / "general.log"
        crit.write_text("old critical data", encoding="utf-8")
        gen.write_text("old general data", encoding="utf-8")
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(gen))
        assert log_mod.clear_logs() is True
        assert crit.read_text(encoding="utf-8") == ""
        assert gen.read_text(encoding="utf-8") == ""

    def test_missing_files_are_left_untouched(self, monkeypatch, tmp_path):
        """Files that don't exist must not be created by clear_logs."""
        crit = tmp_path / "critical.log"
        gen = tmp_path / "general.log"
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(gen))
        assert log_mod.clear_logs() is True
        assert not crit.exists()
        assert not gen.exists()

    def test_returns_false_when_truncation_fails(self, monkeypatch, tmp_path):
        """A path that can't be opened for writing must make clear_logs return False."""
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(tmp_path))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(tmp_path / "general.log"))
        assert log_mod.clear_logs() is False
