# test_prefs_ctrl.py - unit tests for gfglock.controllers.prefs_ctrl

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import EncryptionDefaults
from gfglock.config.ui_config import ChunkSizeOptions, EncryptionModes
from gfglock.controllers import prefs_ctrl
from gfglock.controllers.prefs_ctrl import PrefsController
from gfglock.core import native_bridge


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


def _raise(*_args, **_kwargs):
    """Stand-in for a monkeypatched call that must fail."""
    raise RuntimeError("simulated failure")


def _make_settings() -> dict:
    """A fully-populated settings dict with non-default values, for property tests."""
    return {
        "theme": "dark",
        "appearance": {"log_text_wrap": False},
        "encryption": {"cpu_threads": 4, "chunk_size": 8 * 1024 * 1024, "encrypt_filenames": True},
        "decryption": {"cpu_threads": 2, "chunk_size": None},
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


class TestProperties:
    """Property getters must reflect the underlying settings dict."""

    def test_passthrough_properties(self, controller):
        """Simple settings passthrough properties mirror the stubbed dict."""
        assert controller.theme == "dark"
        assert controller.encThreads == 4
        assert controller.encFilenames is True
        assert controller.decThreads == 2
        assert controller.encMode == "chacha20_poly1305"
        assert controller.enableLogs is True
        assert controller.logLevel == "all"
        assert controller.clampThreads is False
        assert controller.logTextWrap is False
        assert controller.operationNotifications is False

    def test_enc_chunk_size_passthrough_value(self, controller):
        """A concrete chunk size must be returned as-is (not -1)."""
        assert controller.encChunkSize == 8 * 1024 * 1024

    def test_dec_chunk_size_none_becomes_sentinel(self, controller):
        """A None chunk size must surface as the -1 QML sentinel."""
        assert controller.decChunkSize == -1

    def test_max_threads_unclamped(self, controller, monkeypatch):
        """clampThreads == False must expose the full CPU count."""
        monkeypatch.setattr(prefs_ctrl.os, "cpu_count", lambda: 6)
        assert controller.maxThreads == 6

    def test_max_threads_clamped(self, controller, monkeypatch):
        """clampThreads == True must reserve one thread for the OS."""
        controller._settings["advanced"]["clamp_cpu_threads"] = True
        monkeypatch.setattr(prefs_ctrl.os, "cpu_count", lambda: 6)
        assert controller.maxThreads == 5

    def test_encryption_mode_options_from_ui_config(self, controller):
        """encryptionModeOptions must mirror EncryptionModes.get_options()."""
        expected = [{"label": label, "value": val} for label, val in EncryptionModes.get_options()]
        assert controller.encryptionModeOptions == expected

    def test_chunk_size_options_map_none_to_sentinel(self, controller):
        """chunkSizeOptions must map the 'no chunking' entry to the -1 sentinel."""
        options = controller.chunkSizeOptions
        expected_first_label = ChunkSizeOptions.get_options()[0][0]
        assert options[0] == {"label": expected_first_label, "value": -1}
        assert all(isinstance(o["value"], int) for o in options)

    def test_native_available_reflects_bridge(self, controller, monkeypatch):
        """nativeAvailable must mirror native_bridge.NATIVE_AVAILABLE."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", True)
        assert controller.nativeAvailable is True
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        assert controller.nativeAvailable is False


class TestCoerceChunk:
    """_coerce_chunk() must translate the -1 sentinel to None, only for chunk_size."""

    def test_sentinel_becomes_none(self):
        """A -1 value under the 'chunk_size' key must become None."""
        assert PrefsController._coerce_chunk("chunk_size", -1) is None

    def test_normal_value_passthrough(self):
        """A concrete chunk_size value must pass through unchanged."""
        assert PrefsController._coerce_chunk("chunk_size", 1024) == 1024

    def test_other_keys_ignore_sentinel(self):
        """A -1 value under any other key must not be coerced."""
        assert PrefsController._coerce_chunk("cpu_threads", -1) == -1


class TestGetSetHelpers:
    """_get()/_set() must navigate nested settings keys safely."""

    def test_get_nested_value(self, controller):
        """A present nested key must return its stored value."""
        assert controller._get("encryption", "cpu_threads") == 4

    def test_get_missing_returns_default(self, controller):
        """A missing key path must return the supplied default."""
        assert controller._get("nope", "missing", default="fallback") == "fallback"

    def test_get_missing_returns_none_by_default(self, controller):
        """A missing key path with no default must return None."""
        assert controller._get("nope") is None

    def test_set_creates_nested_path(self, controller):
        """_set() must create intermediate dicts that don't exist yet."""
        controller._set(99, "new", "deep", "key")
        assert controller._settings["new"]["deep"]["key"] == 99

    def test_set_overwrites_existing_value(self, controller):
        """_set() must overwrite an already-present nested value."""
        controller._set(10, "encryption", "cpu_threads")
        assert controller._settings["encryption"]["cpu_threads"] == 10


class TestLoadSettings:
    """loadSettings() must reload from disk and notify QML."""

    def test_reloads_and_emits(self, controller, monkeypatch):
        """A successful reload must update properties and emit settingsChanged."""
        new_settings = _make_settings()
        new_settings["theme"] = "light"
        monkeypatch.setattr(prefs_ctrl, "load_settings", lambda: new_settings)
        spy = MagicMock()
        controller.settingsChanged.connect(spy)
        controller.loadSettings()
        assert controller.theme == "light"
        spy.assert_called_once()

    def test_swallows_failure(self, controller, monkeypatch):
        """A load_settings() failure must not propagate or change state."""
        old_theme = controller.theme
        monkeypatch.setattr(prefs_ctrl, "load_settings", _raise)
        try:
            controller.loadSettings()
        except Exception as exc:
            pytest.fail(f"loadSettings() must not raise: {exc}")
        assert controller.theme == old_theme


class TestSaveSettings:
    """saveSettings() must merge dot-separated updates and persist them."""

    def test_merges_and_persists(self, controller, monkeypatch):
        """A nested key update must be applied and passed to save_settings()."""
        saved: list[dict] = []
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: saved.append(dict(s)))
        spy = MagicMock()
        controller.settingsChanged.connect(spy)
        controller.saveSettings({"encryption.cpu_threads": 7})
        assert controller.encThreads == 7
        assert saved[-1]["encryption"]["cpu_threads"] == 7
        spy.assert_called_once()

    def test_coerces_chunk_sentinel(self, controller, monkeypatch):
        """A chunk_size update of -1 must be stored as None."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        controller.saveSettings({"encryption.chunk_size": -1})
        assert controller._get("encryption", "chunk_size") is None

    def test_emits_theme_changed_on_change(self, controller, monkeypatch):
        """A theme update must additionally emit themeChanged."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.saveSettings({"theme": "light"})
        spy.assert_called_once_with("light")

    def test_no_theme_emit_when_unchanged(self, controller, monkeypatch):
        """An update that doesn't touch the theme must not emit themeChanged."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.saveSettings({"encryption.cpu_threads": 2})
        spy.assert_not_called()

    def test_swallows_failure(self, controller, monkeypatch):
        """A save_settings() failure must not propagate."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", _raise)
        try:
            controller.saveSettings({"theme": "light"})
        except Exception as exc:
            pytest.fail(f"saveSettings() must not raise: {exc}")


class TestSetSetting:
    """setSetting() must persist a single dot-separated key immediately."""

    def test_persists_single_key(self, controller, monkeypatch):
        """A single-key update must be applied and saved."""
        saved: list[dict] = []
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: saved.append(dict(s)))
        spy = MagicMock()
        controller.settingsChanged.connect(spy)
        controller.setSetting("advanced.log_level", "all")
        assert controller.logLevel == "all"
        spy.assert_called_once()

    def test_theme_key_emits_theme_changed(self, controller, monkeypatch):
        """Setting the 'theme' key must additionally emit themeChanged."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.setSetting("theme", "light")
        spy.assert_called_once_with("light")

    def test_non_theme_key_no_theme_emit(self, controller, monkeypatch):
        """Setting a non-theme key must not emit themeChanged."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: True)
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.setSetting("advanced.log_level", "all")
        spy.assert_not_called()

    def test_swallows_failure(self, controller, monkeypatch):
        """A save_settings() failure must not propagate."""
        monkeypatch.setattr(prefs_ctrl, "save_settings", _raise)
        try:
            controller.setSetting("theme", "light")
        except Exception as exc:
            pytest.fail(f"setSetting() must not raise: {exc}")


class TestResetDefaults:
    """resetDefaults() must restore factory settings and persist them."""

    def test_restores_and_persists(self, controller, monkeypatch):
        """Resetting must apply real defaults and emit both signals."""
        saved: list[dict] = []
        monkeypatch.setattr(prefs_ctrl, "save_settings", lambda s: saved.append(dict(s)))
        settings_spy = MagicMock()
        theme_spy = MagicMock()
        controller.settingsChanged.connect(settings_spy)
        controller.themeChanged.connect(theme_spy)
        controller.resetDefaults()
        assert controller.encThreads == EncryptionDefaults.DEFAULT_THREADS
        settings_spy.assert_called_once()
        theme_spy.assert_called_once()
        assert saved

    def test_swallows_failure(self, controller, monkeypatch):
        """A get_default_settings() failure must not propagate."""
        monkeypatch.setattr(prefs_ctrl, "get_default_settings", _raise)
        try:
            controller.resetDefaults()
        except Exception as exc:
            pytest.fail(f"resetDefaults() must not raise: {exc}")


class TestClearLogs:
    """clearLogs() must delete log files and notify QML."""

    def test_calls_util_and_emits(self, controller, monkeypatch):
        """A successful clear must call clear_logs() and emit logsCleared."""
        clear_mock = MagicMock()
        monkeypatch.setattr(prefs_ctrl, "clear_logs", clear_mock)
        spy = MagicMock()
        controller.logsCleared.connect(spy)
        controller.clearLogs()
        clear_mock.assert_called_once()
        spy.assert_called_once()

    def test_swallows_failure(self, controller, monkeypatch):
        """A clear_logs() failure must not propagate."""
        monkeypatch.setattr(prefs_ctrl, "clear_logs", _raise)
        try:
            controller.clearLogs()
        except Exception as exc:
            pytest.fail(f"clearLogs() must not raise: {exc}")


class TestOpenLogsFolder:
    """openLogsFolder() must launch the correct OS file manager per platform."""

    def test_windows(self, controller, monkeypatch):
        """On win32, it must launch explorer on the logs directory."""
        monkeypatch.setattr(prefs_ctrl.sys, "platform", "win32")
        monkeypatch.setattr(prefs_ctrl, "get_logs_dir", lambda: "C:\\logs")
        run_mock = MagicMock()
        monkeypatch.setattr(prefs_ctrl.subprocess, "run", run_mock)
        controller.openLogsFolder()
        run_mock.assert_called_once_with(["explorer", "C:\\logs"], check=False)

    def test_non_windows(self, controller, monkeypatch):
        """On non-win32 platforms, it must launch xdg-open."""
        monkeypatch.setattr(prefs_ctrl.sys, "platform", "linux")
        monkeypatch.setattr(prefs_ctrl, "get_logs_dir", lambda: "/tmp/logs")
        run_mock = MagicMock()
        monkeypatch.setattr(prefs_ctrl.subprocess, "run", run_mock)
        controller.openLogsFolder()
        run_mock.assert_called_once_with(["xdg-open", "/tmp/logs"], check=False)

    def test_swallows_failure(self, controller, monkeypatch):
        """A failure locating the logs folder must not propagate."""
        monkeypatch.setattr(prefs_ctrl, "get_logs_dir", _raise)
        try:
            controller.openLogsFolder()
        except Exception as exc:
            pytest.fail(f"openLogsFolder() must not raise: {exc}")
