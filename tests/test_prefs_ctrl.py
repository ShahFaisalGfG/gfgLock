# test_prefs_ctrl.py - unit tests for gfglock.controllers.prefs_ctrl

import copy
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import AlgorithmDefaults, EncryptionDefaults, ReadSizeDefaults, ThemeDefaults
from gfglock.controllers import prefs_ctrl
from gfglock.controllers.prefs_ctrl import PrefsController
from gfglock.services.read_size_test import Choice, SpeedResult

MB = 1024 * 1024


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


def _make_settings() -> dict:
    """A fully-populated settings dict with non-default values, for property tests."""
    return {
        "theme": "dark",
        "encryption": {"cpu_threads": 4, "encrypt_filenames": True, "read_size": 0},
        "decryption": {"cpu_threads": 2, "read_size": 0},
        "advanced": {
            "encryption_mode": "chacha20_poly1305",
            "enable_logs": True,
            "log_level": "all",
            "clamp_cpu_threads": False,
            "operation_notifications": False,
        },
    }


class _Disk:
    """settings.json stand-in: load_settings returns a copy of what the last successful save wrote."""

    def __init__(self) -> None:
        self.data = _make_settings()
        self.saves = 0
        self.fail = False

    def load(self) -> dict:
        return copy.deepcopy(self.data)

    def save(self, settings: dict) -> bool:
        if self.fail:
            return False
        self.saves += 1
        self.data = copy.deepcopy(settings)
        return True


@pytest.fixture
def disk(monkeypatch) -> _Disk:
    stand_in = _Disk()
    monkeypatch.setattr(prefs_ctrl, "load_settings", stand_in.load)
    monkeypatch.setattr(prefs_ctrl, "save_settings", stand_in.save)
    monkeypatch.setattr(prefs_ctrl, "write_log", MagicMock())
    return stand_in


@pytest.fixture
def controller(disk):
    """PrefsController loaded with a known, non-default settings dict."""
    return PrefsController()


def _results(controller) -> list:
    """Record every saveFinished(success, message) the controller emits."""
    results: list = []
    controller.saveFinished.connect(lambda ok, message: results.append((ok, message)))
    return results


class _Run(QObject):
    """An EncryptController stand-in: only its busy state matters to the speed test."""

    busyChanged = Signal(bool)

    def __init__(self, busy: bool = False) -> None:
        super().__init__()
        self.busy = busy

    def start(self) -> None:
        self.busy = True
        self.busyChanged.emit(True)


class TestProperties:
    """Property getters must reflect the underlying settings dict."""

    def test_passthrough_properties(self, controller):
        assert controller.theme == "dark"
        assert controller.encThreads == 4
        assert controller.encFilenames is True
        assert controller.decThreads == 2
        assert controller.encMode == "chacha20_poly1305"
        assert controller.enableLogs is True
        assert controller.logLevel == "all"
        assert controller.clampThreads is False
        assert controller.operationNotifications is False

    def test_cpu_count_reflects_os(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl.os, "cpu_count", lambda: 8)
        assert controller.cpuCount == 8
        monkeypatch.setattr(prefs_ctrl.os, "cpu_count", lambda: None)
        assert controller.cpuCount == 1

    def test_missing_key_falls_back_to_default(self, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "load_settings", lambda: {"theme": "light"})
        assert PrefsController().encThreads == EncryptionDefaults.DEFAULT_THREADS


class TestOptions:
    """Combo box options use {label, code} so the shared StyledComboBox can show them."""

    def test_theme_options(self, controller):
        assert [o["code"] for o in controller.themeOptions] == ThemeDefaults.SUPPORTED_THEMES

    def test_algorithm_options_carry_their_explanation_and_extension(self, controller):
        options = controller.algorithmOptions
        assert [o["code"] for o in options] == AlgorithmDefaults.SUPPORTED_ALGORITHMS == ["aes256_gcm", "chacha20_poly1305"]
        assert [o["ext"] for o in options] == [".gfglock", ".gfgcha"]
        assert all(o["label"] and o["hint"] and "Files end in" not in o["hint"] for o in options)

    def test_cfb_is_no_longer_offered(self, controller):
        assert all("cfb" not in o["code"] for o in controller.algorithmOptions)

    def test_log_level_options(self, controller):
        assert [o["code"] for o in controller.logLevelOptions] == ["critical", "all"]


class TestGetSetHelpers:
    """_get()/_set() must navigate nested settings keys safely."""

    def test_get_nested_value(self, controller):
        assert controller._get("encryption", "cpu_threads") == 4

    def test_get_missing_returns_default(self, controller):
        assert controller._get("nope", "missing", default="fallback") == "fallback"

    def test_get_through_a_scalar_returns_default(self, controller):
        assert controller._get("theme", "deeper", default="fallback") == "fallback"

    def test_set_creates_nested_path(self, controller):
        controller._set(99, "new", "deep", "key")
        assert controller._settings["new"]["deep"]["key"] == 99


class TestSaveSettings:
    """saveSettings() must apply dotted updates, save once, and report how it went."""

    def test_merges_and_persists(self, controller, disk):
        results = _results(controller)
        controller.saveSettings({"encryption.cpu_threads": 7, "advanced.log_level": "critical"})
        assert controller.encThreads == 7
        assert disk.saves == 1 and disk.data["encryption"]["cpu_threads"] == 7
        assert results == [(True, "")]

    def test_updates_apply_on_top_of_what_is_on_disk(self, controller, disk):
        """A value another window saved meanwhile (the theme, say) isn't overwritten with a stale copy."""
        disk.data["theme"] = "light"
        controller.saveSettings({"encryption.cpu_threads": 3})
        assert disk.data["theme"] == "light" and disk.data["encryption"]["cpu_threads"] == 3

    def test_emits_theme_changed_only_on_change(self, controller):
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.saveSettings({"encryption.cpu_threads": 2})
        spy.assert_not_called()
        controller.saveSettings({"theme": "light"})
        spy.assert_called_once_with("light")

    def test_failed_save_rolls_back_to_the_file(self, controller, disk):
        """Runs read the settings from disk, so the window must not show values that aren't in use."""
        disk.fail = True
        results = _results(controller)
        changed = MagicMock()
        controller.settingsChanged.connect(changed)
        controller.saveSettings({"encryption.cpu_threads": 7, "theme": "light"})
        assert controller.encThreads == 4 and controller.theme == "dark"
        assert results == [(False, "Couldn't save the preferences file, so the previous preferences are still in use.")]
        changed.assert_called_once()


class TestRememberEncryptOptions:
    """The Encrypt tab keeps its own method and Hide file names choices, saved without a status message."""

    def test_saves_quietly(self, controller, disk):
        results = _results(controller)
        controller.rememberEncryptOptions("aes256_gcm", False)
        assert disk.data["advanced"]["encryption_mode"] == "aes256_gcm"
        assert disk.data["encryption"]["encrypt_filenames"] is False
        assert controller.encMode == "aes256_gcm" and controller.encFilenames is False
        assert results == []

    def test_unchanged_choices_are_not_written(self, controller, disk):
        controller.rememberEncryptOptions("chacha20_poly1305", True)
        assert disk.saves == 0

    def test_unknown_method_is_ignored(self, controller, disk):
        controller.rememberEncryptOptions("aes256_cfb", False)
        assert disk.saves == 0 and controller.encMode == "chacha20_poly1305"

    def test_failure_is_still_reported(self, controller, disk):
        disk.fail = True
        results = _results(controller)
        controller.rememberEncryptOptions("aes256_gcm", True)
        assert results and results[0][0] is False
        assert controller.encMode == "chacha20_poly1305"


class TestResetDefaults:
    def test_restores_and_persists(self, controller, disk):
        theme_spy = MagicMock()
        controller.themeChanged.connect(theme_spy)
        controller.resetDefaults()
        assert controller.encThreads == EncryptionDefaults.DEFAULT_THREADS
        theme_spy.assert_called_once_with(ThemeDefaults.DEFAULT_THEME)
        assert disk.saves == 1


class TestLogs:
    def test_clear_logs_reports_success(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "clear_logs", lambda: True)
        results = _results(controller)
        controller.clearLogs()
        assert results == [(True, "Logs cleared.")]

    def test_clear_logs_reports_failure(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "clear_logs", lambda: False)
        results = _results(controller)
        controller.clearLogs()
        assert results[0][0] is False

    def test_open_logs_folder_uses_explorer(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "get_logs_dir", lambda: "C:\\logs")
        start = MagicMock()
        monkeypatch.setattr(prefs_ctrl.os, "startfile", start, raising=False)
        controller.openLogsFolder()
        start.assert_called_once_with("C:\\logs")

    def test_open_logs_folder_failure_is_reported(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "get_logs_dir", lambda: "C:\\logs")
        monkeypatch.setattr(prefs_ctrl.os, "startfile", MagicMock(side_effect=OSError("denied")), raising=False)
        results = _results(controller)
        controller.openLogsFolder()
        assert results == [(False, "Couldn't open the logs folder.")]


class TestReadSize:
    def test_read_size_starts_at_the_default(self, controller):
        assert controller.encReadSize == 0 and controller.decReadSize == 0

    def test_saved_read_size_is_reported(self, controller):
        controller.saveSettings({"encryption.read_size": 32 * MB})
        assert controller.encReadSize == 32 * MB

    def test_options_start_with_the_default(self, controller):
        options = controller.readSizeOptions
        assert options[0] == {"label": "Default (4 MB)", "code": 0}
        codes = [o["code"] for o in options[1:]]
        assert ReadSizeDefaults.DEFAULT_BYTES not in codes  # offered once, as the default
        assert sorted(codes + [ReadSizeDefaults.DEFAULT_BYTES]) == ReadSizeDefaults.TEST_SIZES


class TestSpeedTest:
    DEFAULT_THREADS = EncryptionDefaults.DEFAULT_THREADS
    # A measured count that is never this PC's default, so the message names it on its own.
    PICKED_THREADS = 3 if DEFAULT_THREADS == 2 else 2

    def _finished(self, controller) -> list:
        calls: list = []
        controller.readSizeTestFinished.connect(lambda *args: calls.append(args))
        return calls

    @pytest.fixture
    def started(self, monkeypatch) -> list:
        """Workers handed to the thread pool (never run)."""
        workers: list = []
        monkeypatch.setattr(prefs_ctrl.QThreadPool, "globalInstance", lambda: MagicMock(start=workers.append))
        return workers

    def _result(self, threads: int = PICKED_THREADS) -> SpeedResult:
        return SpeedResult(Choice(32 * MB, threads, 410e6), Choice(0, self.DEFAULT_THREADS, 395e6))

    def test_result_is_saved_and_described(self, controller, disk):
        picked = self.PICKED_THREADS
        calls = self._finished(controller)
        results = _results(controller)
        controller._on_read_size_finished(self._result(), "")
        ((encrypt, decrypt, encrypt_threads, decrypt_threads, message),) = calls
        assert (encrypt, decrypt, encrypt_threads, decrypt_threads) == (32 * MB, 0, picked, self.DEFAULT_THREADS)
        assert (controller.encReadSize, controller.decReadSize) == (32 * MB, 0)
        assert (controller.encThreads, controller.decThreads) == (picked, self.DEFAULT_THREADS)
        assert disk.data["encryption"]["read_size"] == 32 * MB and disk.data["decryption"]["cpu_threads"] == self.DEFAULT_THREADS
        assert message.startswith(f"Best on this PC: 32 MB reads and {picked} files at a time (410 MB/s) for encrypting")
        assert f"the default 4 MB reads and the default {self.DEFAULT_THREADS} files at a time (395 MB/s)" in message
        assert message.endswith("at least 5% faster. Saved.")
        assert results == []  # the speed test reports through its own signal
        assert not controller.readSizeTestRunning

    def test_one_file_at_a_time_reads_naturally(self, controller):
        calls = self._finished(controller)
        controller._on_read_size_finished(self._result(threads=1), "")
        assert "32 MB reads and 1 file at a time" in calls[0][4]

    def test_failed_save_is_reported(self, controller, disk):
        disk.fail = True
        calls = self._finished(controller)
        controller._on_read_size_finished(self._result(), "")
        assert calls[0][:4] == (-1, -1, -1, -1)  # nothing was saved, so no list changes
        assert calls[0][4].endswith("so the previous preferences are still in use.")
        assert controller.encReadSize == 0  # rolled back to the file

    def test_error_is_reported(self, controller):
        calls = self._finished(controller)
        controller._on_read_size_finished(None, "The test needs 768 MB of free space on the system drive.")
        assert calls == [(-1, -1, -1, -1, "The test needs 768 MB of free space on the system drive.")]

    def test_stopped_test_changes_nothing(self, controller, disk):
        calls = self._finished(controller)
        controller._on_read_size_finished(None, "")
        assert calls == [(-1, -1, -1, -1, "Speed test stopped.")]
        assert disk.saves == 0

    def test_start_runs_one_test_at_a_time(self, controller, started):
        controller.startReadSizeTest("chacha20_poly1305")
        controller.startReadSizeTest("aes256_gcm")
        assert len(started) == 1 and started[0].algorithm == "chacha"
        assert controller.readSizeTestRunning
        controller.cancelReadSizeTest()
        assert started[0]._stop.cancelled

    def test_files_at_a_time_is_measured_up_to_the_thread_limit(self, controller, started, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "thread_limit", lambda reserve_one: 7 if reserve_one else 8)
        controller.startReadSizeTest("aes256_gcm")
        assert (started[0].thread_limit, started[0].default_threads) == (8, self.DEFAULT_THREADS)  # clamp is off

    def test_refused_while_a_run_is_busy(self, controller, started):
        calls = self._finished(controller)
        controller.set_run_controllers([_Run(), _Run(busy=True)])
        controller.startReadSizeTest("aes256_gcm")
        assert started == []
        assert calls == [(-1, -1, -1, -1, "Wait for the current run to finish, then try again.")]
        assert not controller.readSizeTestRunning

    def test_a_run_starting_stops_the_test(self, controller, started):
        calls = self._finished(controller)
        run = _Run()
        controller.set_run_controllers([run])
        controller.startReadSizeTest("aes256_gcm")
        run.start()
        assert started[0]._stop.cancelled
        controller._on_read_size_finished(None, "")
        assert calls == [(-1, -1, -1, -1, "The speed test stopped because a run started. Try again when it finishes.")]

    def test_shutdown_stops_the_test(self, controller, started):
        controller.startReadSizeTest("aes256_gcm")
        controller.shutdown()
        assert started[0]._stop.cancelled
