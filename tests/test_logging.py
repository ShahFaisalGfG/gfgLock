import os
import re
import threading

import pytest

from gfglock.utils import logging as log_mod

_SEP_PATTERN = re.compile(r"^─{68}\n\n$")
_LINE = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
_ALL = {"advanced": {"enable_logs": True, "log_level": "all"}}
_ERRORS_ONLY = {"advanced": {"enable_logs": True, "log_level": "critical"}}
_OFF = {"advanced": {"enable_logs": False}}


@pytest.fixture
def logs(monkeypatch, tmp_path):
    """Point both logs at tmp_path and return (critical, general) paths."""
    crit = tmp_path / "critical.log"
    gen = tmp_path / "general.log"
    monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(crit))
    monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(gen))
    return crit, gen


def _settings(monkeypatch, settings: dict) -> None:
    monkeypatch.setattr(log_mod, "load_settings", lambda: settings)


class TestGetLogsDir:
    """Logs go in a logs folder inside the app's data folder (see test_paths), created on demand."""

    def test_built_app_uses_the_data_folder(self, monkeypatch, tmp_path):
        monkeypatch.setattr(log_mod, "data_dir", lambda: str(tmp_path))
        result = log_mod.get_logs_dir()
        assert result == os.path.join(str(tmp_path), "logs")
        assert os.path.isdir(result)


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

    def test_appends_timestamped_entry(self, logs):
        """A single write must produce one timestamped line with the message."""
        crit, _gen = logs
        assert log_mod.write_critical_log("hello") is True
        assert re.match(rf"^{_LINE}hello\n$", crit.read_text(encoding="utf-8"))

    def test_appends_multiple_entries(self, logs):
        """Successive writes must append rather than overwrite."""
        crit, _gen = logs
        log_mod.write_critical_log("first")
        log_mod.write_critical_log("second")
        lines = crit.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert lines[0].endswith("first")
        assert lines[1].endswith("second")

    def test_returns_false_on_write_failure(self, monkeypatch, tmp_path):
        """An unwritable path must return False instead of raising."""
        bad_path = str(tmp_path / "missing_dir" / "critical.log")
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: bad_path)
        assert log_mod.write_critical_log("hello") is False

    def test_unencodable_file_names_are_escaped(self, logs):
        """A file name with a lone surrogate (possible on NTFS) is logged escaped, not dropped."""
        crit, _gen = logs
        assert log_mod.write_critical_log("bad \udc80 name") is True
        assert "bad \\udc80 name" in crit.read_text(encoding="utf-8")


class TestWriteGeneralLog:
    """write_general_log must append a timestamped line to the general log file."""

    def test_appends_timestamped_entry(self, logs):
        """A single write must produce one timestamped line with the message."""
        _crit, gen = logs
        assert log_mod.write_general_log("world") is True
        assert re.match(rf"^{_LINE}world\n$", gen.read_text(encoding="utf-8"))


class TestWriteLog:
    """write_log must respect the enable_logs flag and the log_level setting."""

    def test_disabled_returns_false(self, monkeypatch, logs):
        """When logging is disabled, write_log must not write anything."""
        _settings(monkeypatch, _OFF)
        assert log_mod.write_log("msg") is False
        assert log_mod.write_log("msg", "critical") is False
        assert not any(path.exists() for path in logs)

    def test_critical_level_always_writes_when_enabled(self, monkeypatch, logs):
        """A critical-level message must write regardless of the log_level setting."""
        crit, _gen = logs
        _settings(monkeypatch, _ERRORS_ONLY)
        assert log_mod.write_log("boom", level="critical") is True
        assert "boom" in crit.read_text(encoding="utf-8")

    def test_general_level_skipped_when_log_level_critical(self, monkeypatch, logs):
        """A general-level message must be skipped when log_level is 'critical'."""
        _crit, gen = logs
        _settings(monkeypatch, _ERRORS_ONLY)
        assert log_mod.write_log("info", level="general") is False
        assert not gen.exists()

    def test_general_level_writes_when_log_level_all(self, monkeypatch, logs):
        """A general-level message must write when log_level is 'all'."""
        _crit, gen = logs
        _settings(monkeypatch, _ALL)
        assert log_mod.write_log("info", level="general") is True
        assert "info" in gen.read_text(encoding="utf-8")

    def test_settings_exception_returns_false(self, monkeypatch):
        """A failure while loading settings must be swallowed, returning False."""
        def raiser():
            raise RuntimeError("settings broken")
        monkeypatch.setattr(log_mod, "load_settings", raiser)
        assert log_mod.write_log("msg") is False

    def test_force_writes_the_critical_log_with_logging_off(self, monkeypatch, logs):
        """Startup failures are logged even when the preferences turn logging off (A12)."""
        crit, gen = logs
        _settings(monkeypatch, _OFF)
        assert log_mod.write_log("Startup failed: no display", "critical", force=True) is True
        assert "Startup failed: no display" in crit.read_text(encoding="utf-8")
        assert not gen.exists()

    def test_force_works_when_the_settings_are_unreadable(self, monkeypatch, logs):
        crit, _gen = logs

        def raiser():
            raise RuntimeError("settings broken")
        monkeypatch.setattr(log_mod, "load_settings", raiser)
        assert log_mod.write_log("Startup failed", force=True) is True
        assert "Startup failed" in crit.read_text(encoding="utf-8")


class TestRotation:
    """Each log moves to name.1 once it passes ROTATE_BYTES, keeping one backup (A8)."""

    def test_full_log_moves_to_its_backup(self, monkeypatch, logs):
        crit, _gen = logs
        monkeypatch.setattr(log_mod, "ROTATE_BYTES", 100)
        crit.write_text("x" * 100, encoding="utf-8")
        assert log_mod.write_critical_log("fresh") is True
        assert (crit.parent / "critical.log.1").read_text(encoding="utf-8") == "x" * 100
        assert crit.read_text(encoding="utf-8").endswith("fresh\n")

    def test_only_one_backup_is_kept(self, monkeypatch, logs):
        crit, _gen = logs
        monkeypatch.setattr(log_mod, "ROTATE_BYTES", 100)
        backup = crit.parent / "critical.log.1"
        backup.write_text("oldest", encoding="utf-8")
        crit.write_text("y" * 150, encoding="utf-8")
        log_mod.write_critical_log("fresh")
        assert backup.read_text(encoding="utf-8") == "y" * 150
        assert sorted(p.name for p in crit.parent.iterdir()) == ["critical.log", "critical.log.1"]

    def test_small_log_is_not_rotated(self, logs):
        crit, _gen = logs
        crit.write_text("small\n", encoding="utf-8")
        log_mod.write_critical_log("more")
        assert not (crit.parent / "critical.log.1").exists()
        assert crit.read_text(encoding="utf-8").startswith("small\n")

    def test_run_log_rotates_while_a_run_writes(self, monkeypatch, logs):
        _crit, gen = logs
        monkeypatch.setattr(log_mod, "ROTATE_BYTES", 200)
        _settings(monkeypatch, _ALL)
        with log_mod.RunLog() as log:
            for i in range(20):
                log.write(f"line {i:02d} " + "z" * 20)
        backup = gen.parent / "general.log.1"
        assert backup.exists() and gen.exists()
        assert gen.stat().st_size < 200 + 60
        assert gen.read_text(encoding="utf-8").splitlines()[-1].endswith("line 19 " + "z" * 20)


class TestRunLog:
    """A run's lines go through handles opened once, flushed after every line (A8)."""

    def test_lines_are_on_disk_before_the_run_log_closes(self, monkeypatch, logs):
        crit, gen = logs
        _settings(monkeypatch, _ALL)
        log = log_mod.RunLog()
        log.write("Encrypted: a.txt -> a.txt.gfglock")
        log.write("Critical error while encrypting b.txt: disk full", critical=True)
        assert gen.read_text(encoding="utf-8").count("\n") == 2
        assert re.match(rf"^{_LINE}Critical error while encrypting b.txt: disk full\n$",
                        crit.read_text(encoding="utf-8"))
        log.close()

    def test_errors_only_level_writes_only_critical_lines(self, monkeypatch, logs):
        crit, gen = logs
        _settings(monkeypatch, _ERRORS_ONLY)
        with log_mod.RunLog() as log:
            log.write("Encrypted: a.txt -> a.txt.gfglock")
            log.write("failed", critical=True)
        assert not gen.exists()
        assert "failed" in crit.read_text(encoding="utf-8")

    def test_logging_off_writes_nothing(self, monkeypatch, logs):
        _settings(monkeypatch, _OFF)
        with log_mod.RunLog() as log:
            log.write("anything", critical=True)
        assert not any(path.exists() for path in logs)

    def test_settings_are_read_once_per_run(self, monkeypatch, logs):
        reads = []
        monkeypatch.setattr(log_mod, "load_settings", lambda: reads.append(1) or _ALL)
        with log_mod.RunLog() as log:
            for i in range(50):
                log.write(f"line {i}")
        assert reads == [1]

    def test_lines_from_several_threads_stay_whole(self, monkeypatch, logs):
        _crit, gen = logs
        _settings(monkeypatch, _ALL)
        with log_mod.RunLog() as log:
            threads = [threading.Thread(target=lambda n=n: [log.write(f"thread {n} line {i}") for i in range(100)])
                       for n in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        lines = gen.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 400 and all(re.match(rf"^{_LINE}thread \d line \d+$", line) for line in lines)

    def test_write_error_drops_the_rest_without_raising(self, monkeypatch, tmp_path):
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(tmp_path / "missing" / "general.log"))
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(tmp_path / "critical.log"))
        _settings(monkeypatch, _ALL)
        with log_mod.RunLog() as log:
            log.write("first")
            log.write("second", critical=True)
        assert "second" in (tmp_path / "critical.log").read_text(encoding="utf-8")


class TestWriteSessionSeparator:
    """write_session_separator must append a divider, gated by the same settings."""

    def test_noop_when_disabled(self, monkeypatch, logs):
        """Disabled logging must leave no separator written anywhere."""
        _settings(monkeypatch, _OFF)
        log_mod.write_session_separator()
        assert not any(path.exists() for path in logs)

    def test_writes_critical_only_by_default(self, monkeypatch, logs):
        """log_level='critical' must write the separator to the critical log only."""
        crit, gen = logs
        _settings(monkeypatch, _ERRORS_ONLY)
        log_mod.write_session_separator()
        assert _SEP_PATTERN.match(crit.read_text(encoding="utf-8"))
        assert not gen.exists()

    def test_writes_both_logs_when_level_all(self, monkeypatch, logs):
        """log_level='all' must write the separator to both log files."""
        crit, gen = logs
        _settings(monkeypatch, _ALL)
        log_mod.write_session_separator()
        assert _SEP_PATTERN.match(crit.read_text(encoding="utf-8"))
        assert _SEP_PATTERN.match(gen.read_text(encoding="utf-8"))


class TestClearLogs:
    """clear_logs must truncate existing log files, delete their backups, and leave missing ones alone."""

    def test_truncates_existing_files_and_deletes_backups(self, logs):
        """Pre-populated log files must be emptied, not deleted; their backups go."""
        crit, gen = logs
        crit.write_text("old critical data", encoding="utf-8")
        gen.write_text("old general data", encoding="utf-8")
        (crit.parent / "critical.log.1").write_text("older", encoding="utf-8")
        assert log_mod.clear_logs() is True
        assert crit.read_text(encoding="utf-8") == ""
        assert gen.read_text(encoding="utf-8") == ""
        assert not (crit.parent / "critical.log.1").exists()

    def test_missing_files_are_left_untouched(self, logs):
        """Files that don't exist must not be created by clear_logs."""
        assert log_mod.clear_logs() is True
        assert not any(path.exists() for path in logs)

    def test_returns_false_when_truncation_fails(self, monkeypatch, tmp_path):
        """A path that can't be opened for writing must make clear_logs return False."""
        monkeypatch.setattr(log_mod, "get_critical_log_file", lambda: str(tmp_path))
        monkeypatch.setattr(log_mod, "get_general_log_file", lambda: str(tmp_path / "general.log"))
        assert log_mod.clear_logs() is False
