# test_prefs_ctrl.py - unit tests for gfglock.controllers.prefs_ctrl

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import AlgorithmDefaults, EncryptionDefaults, ReadSizeDefaults, ThemeDefaults
from gfglock.controllers import prefs_ctrl
from gfglock.controllers.prefs_ctrl import PrefsController
from gfglock.services.read_size_test import SizeTiming


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
        "encryption": {"cpu_threads": 4, "encrypt_filenames": True},
        "decryption": {"cpu_threads": 2},
        "advanced": {
            "encryption_mode": "chacha20_poly1305",
            "enable_logs": True,
            "log_level": "all",
            "clamp_cpu_threads": False,
            "operation_notifications": False,
        },
    }


@pytest.fixture
def controller(monkeypatch):
    """PrefsController loaded with a known, non-default settings dict."""
    monkeypatch.setattr(prefs_ctrl, "load_settings", lambda: _make_settings())
    return PrefsController()


def _results(controller) -> list:
    """Record every saveFinished(success, message) the controller emits."""
    results: list = []
    controller.saveFinished.connect(lambda ok, message: results.append((ok, message)))
    return results


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

    def test_algorithm_options_carry_their_explanation(self, controller):
        options = controller.algorithmOptions
        assert [o["code"] for o in options] == AlgorithmDefaults.SUPPORTED_ALGORITHMS
        assert all(o["label"] and o["hint"] for o in options)

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

    def test_merges_and_persists(self, controller, monkeypatch):
        saved: list[dict] = []
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: saved.append(dict(s)) or True)
        results = _results(controller)
        controller.saveSettings({"encryption.cpu_threads": 7, "advanced.log_level": "critical"})
        assert controller.encThreads == 7
        assert len(saved) == 1 and saved[0]["encryption"]["cpu_threads"] == 7
        assert results == [(True, "")]

    def test_emits_theme_changed_only_on_change(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.saveSettings({"encryption.cpu_threads": 2})
        spy.assert_not_called()
        controller.saveSettings({"theme": "light"})
        spy.assert_called_once_with("light")

    def test_failed_save_is_reported(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: False)
        monkeypatch.setattr(prefs_ctrl, "write_log", MagicMock())
        results = _results(controller)
        controller.saveSettings({"theme": "light"})
        assert results == [(False, "Couldn't save the preferences file.")]


class TestResetDefaults:
    def test_restores_and_persists(self, controller, monkeypatch):
        saved: list[dict] = []
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: saved.append(dict(s)) or True)
        theme_spy = MagicMock()
        controller.themeChanged.connect(theme_spy)
        controller.resetDefaults()
        assert controller.encThreads == EncryptionDefaults.DEFAULT_THREADS
        theme_spy.assert_called_once_with(ThemeDefaults.DEFAULT_THEME)
        assert saved


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
        monkeypatch.setattr(prefs_ctrl, "write_log", MagicMock())
        results = _results(controller)
        controller.openLogsFolder()
        assert results == [(False, "Couldn't open the logs folder.")]


class TestReadSize:
    def test_read_size_defaults_to_automatic(self, controller):
        assert controller.encReadSize == 0 and controller.decReadSize == 0

    def test_saved_read_size_is_reported(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        controller.saveSettings({"encryption.read_size": 32 * 1024 * 1024})
        assert controller.encReadSize == 32 * 1024 * 1024

    def test_options_start_with_automatic(self, controller):
        options = controller.readSizeOptions
        assert options[0]["code"] == 0 and "Automatic" in options[0]["label"]
        assert [o["code"] for o in options[1:]] == ReadSizeDefaults.SIZES


class TestReadSizeTest:
    MB = 1024 * 1024

    def _finished(self, controller) -> list:
        calls: list = []
        controller.readSizeTestFinished.connect(lambda e, d, m: calls.append((e, d, m)))
        return calls

    def test_result_picks_sizes_and_describes_them(self, controller):
        calls = self._finished(controller)
        timings = [SizeTiming(4 * self.MB, 1.0, 1.0), SizeTiming(32 * self.MB, 0.5, 0.99)]
        controller._on_read_size_finished(timings, "")
        (encrypt, decrypt, message), = calls
        assert (encrypt, decrypt) == (32 * self.MB, 0)
        assert "32 MB when encrypting" in message and "Automatic when decrypting" in message
        assert not controller.readSizeTestRunning

    def test_error_is_reported(self, controller, monkeypatch):
        monkeypatch.setattr(prefs_ctrl, "write_log", MagicMock())
        calls = self._finished(controller)
        controller._on_read_size_finished([], "The test needs 768 MB of free space on the system drive.")
        assert calls == [(-1, -1, "The test needs 768 MB of free space on the system drive.")]

    def test_stopped_test_changes_nothing(self, controller):
        calls = self._finished(controller)
        controller._on_read_size_finished([], "")
        assert calls == [(-1, -1, "Speed test stopped.")]

    def test_start_runs_one_test_at_a_time(self, controller, monkeypatch):
        started = []
        monkeypatch.setattr(prefs_ctrl.QThreadPool, "globalInstance", lambda: MagicMock(start=started.append))
        controller.startReadSizeTest("chacha20_poly1305")
        controller.startReadSizeTest("aes256_gcm")
        assert len(started) == 1 and started[0].algorithm == "chacha"
        assert controller.readSizeTestRunning
        controller.cancelReadSizeTest()
        assert started[0]._cancel.is_set()
