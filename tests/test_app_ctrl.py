# test_app_ctrl.py - unit tests for gfglock.controllers.app_ctrl

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import AppInfo
from gfglock.controllers import app_ctrl
from gfglock.controllers.app_ctrl import AppController, _detect_system_theme


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


def _raise(*_args, **_kwargs):
    """Stand-in for a monkeypatched call that must fail."""
    raise RuntimeError("simulated failure")


@pytest.fixture
def stub_settings(monkeypatch):
    """Replace load_settings/save_settings with in-memory stand-ins."""
    store = {"theme": "system"}
    saved: list[dict] = []
    monkeypatch.setattr(app_ctrl, "load_settings", lambda: dict(store))
    monkeypatch.setattr(app_ctrl, "save_settings", lambda s: saved.append(dict(s)))
    return store, saved


@pytest.fixture
def controller(monkeypatch, stub_settings):
    """AppController with system-theme detection stubbed to 'light'."""
    monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "light")
    return AppController()


class TestThemeDetection:
    """_detect_system_theme() must translate the registry value into light/dark and fail safe."""

    def test_light_value(self, monkeypatch):
        """AppsUseLightTheme == 1 must resolve to 'light'."""
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", lambda *a, **k: object())
        monkeypatch.setattr(app_ctrl.winreg, "QueryValueEx", lambda k, n: (1, 1))
        monkeypatch.setattr(app_ctrl.winreg, "CloseKey", lambda k: None)
        assert _detect_system_theme() == "light"

    def test_dark_value(self, monkeypatch):
        """AppsUseLightTheme == 0 must resolve to 'dark'."""
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", lambda *a, **k: object())
        monkeypatch.setattr(app_ctrl.winreg, "QueryValueEx", lambda k, n: (0, 1))
        monkeypatch.setattr(app_ctrl.winreg, "CloseKey", lambda k: None)
        assert _detect_system_theme() == "dark"

    def test_registry_failure_defaults_light(self, monkeypatch):
        """Any registry access failure must fall back to 'light'."""
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", _raise)
        assert _detect_system_theme() == "light"


class TestConstruction:
    """Constructor resolves the initial theme from settings."""

    def test_system_theme_resolved(self, monkeypatch, stub_settings):
        """theme == 'system' must trigger _detect_system_theme()."""
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        ctrl = AppController()
        assert ctrl.currentTheme == "dark"

    def test_explicit_theme_bypasses_detection(self, monkeypatch, stub_settings):
        """An explicit stored theme must be used as-is, skipping detection."""
        store, _ = stub_settings
        store["theme"] = "dark"

        def _fail_if_called():
            pytest.fail("system detection should not run for an explicit theme")

        monkeypatch.setattr(app_ctrl, "_detect_system_theme", _fail_if_called)
        ctrl = AppController()
        assert ctrl.currentTheme == "dark"


class TestStaticProperties:
    """Constant properties must mirror AppInfo / os.cpu_count()."""

    def test_app_info_properties(self, controller):
        """appVersion/appName/appDescription/appAuthor mirror AppInfo constants."""
        assert controller.appVersion == AppInfo.APP_VERSION
        assert controller.appName == AppInfo.APP_NAME
        assert controller.appDescription == AppInfo.APP_DESCRIPTION
        assert controller.appAuthor == AppInfo.APP_AUTHOR

    def test_cpu_count_reflects_os(self, controller, monkeypatch):
        """cpuCount mirrors os.cpu_count(), falling back to 1 when None."""
        monkeypatch.setattr(app_ctrl.os, "cpu_count", lambda: 8)
        assert controller.cpuCount == 8
        monkeypatch.setattr(app_ctrl.os, "cpu_count", lambda: None)
        assert controller.cpuCount == 1


class TestDetectTheme:
    """detectTheme() re-reads settings/registry and emits only on change."""

    def test_emits_when_theme_changes(self, controller, monkeypatch):
        """A different resolved theme must update currentTheme and emit themeChanged."""
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.detectTheme()
        assert controller.currentTheme == "dark"
        spy.assert_called_once_with("dark")

    def test_no_emit_when_theme_unchanged(self, controller, monkeypatch):
        """Detecting the same theme again must not emit themeChanged."""
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "light")
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.detectTheme()
        spy.assert_not_called()

    def test_swallows_settings_failure(self, controller, monkeypatch):
        """A load_settings() failure must not propagate or change the theme."""
        monkeypatch.setattr(app_ctrl, "load_settings", _raise)
        try:
            controller.detectTheme()
        except Exception as exc:
            pytest.fail(f"detectTheme() must not raise: {exc}")
        assert controller.currentTheme == "light"


class TestApplyTheme:
    """applyTheme() persists the raw choice and resolves 'system' for display."""

    def test_explicit_theme_applied_and_saved(self, controller, stub_settings):
        """Applying 'dark' must update currentTheme, emit themeChanged, and persist 'dark'."""
        _, saved = stub_settings
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.applyTheme("dark")
        assert controller.currentTheme == "dark"
        spy.assert_called_once_with("dark")
        assert saved[-1]["theme"] == "dark"

    def test_system_theme_resolved_but_raw_saved(self, controller, monkeypatch, stub_settings):
        """Applying 'system' must persist the literal 'system' while resolving currentTheme."""
        _, saved = stub_settings
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        controller.applyTheme("system")
        assert controller.currentTheme == "dark"
        assert saved[-1]["theme"] == "system"

    def test_no_emit_when_resolved_theme_unchanged(self, controller):
        """Re-applying the already-active theme must not emit themeChanged."""
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.applyTheme("light")
        spy.assert_not_called()

    def test_swallows_save_failure(self, controller, monkeypatch):
        """A save_settings() failure must not propagate."""
        monkeypatch.setattr(app_ctrl, "save_settings", _raise)
        try:
            controller.applyTheme("dark")
        except Exception as exc:
            pytest.fail(f"applyTheme() must not raise: {exc}")


class TestLogs:
    """appendLog()/clearLogs() must mutate in-memory logs and emit signals."""

    def test_append_log_emits_message(self, controller):
        """appendLog() appends to the internal list and emits logAppended."""
        spy = MagicMock()
        controller.logAppended.connect(spy)
        controller.appendLog("hello")
        assert controller._logs == ["hello"]
        spy.assert_called_once_with("hello")

    def test_clear_logs_resets_state(self, controller, monkeypatch):
        """clearLogs() empties the list, calls clear_logs(), and emits logsCleared."""
        controller.appendLog("one")
        clear_mock = MagicMock()
        monkeypatch.setattr(app_ctrl, "clear_logs", clear_mock)
        spy = MagicMock()
        controller.logsCleared.connect(spy)
        controller.clearLogs()
        assert controller._logs == []
        clear_mock.assert_called_once()
        spy.assert_called_once()

    def test_clear_logs_swallows_failure(self, controller, monkeypatch):
        """A clear_logs() failure on disk must not propagate."""
        monkeypatch.setattr(app_ctrl, "clear_logs", _raise)
        try:
            controller.clearLogs()
        except Exception as exc:
            pytest.fail(f"clearLogs() must not raise: {exc}")


class TestExternalActions:
    """openUpdates()/openLogsFolder() must call the OS-facing APIs with expected arguments."""

    def test_open_updates_opens_browser(self, controller, monkeypatch):
        """openUpdates() must open the GitHub releases URL."""
        open_mock = MagicMock()
        monkeypatch.setattr(app_ctrl.webbrowser, "open", open_mock)
        controller.openUpdates()
        open_mock.assert_called_once_with(app_ctrl._UPDATES_URL)

    def test_open_updates_swallows_failure(self, controller, monkeypatch):
        """A browser-launch failure must not propagate."""
        monkeypatch.setattr(app_ctrl.webbrowser, "open", _raise)
        try:
            controller.openUpdates()
        except Exception as exc:
            pytest.fail(f"openUpdates() must not raise: {exc}")

    def test_open_logs_folder_windows(self, controller, monkeypatch):
        """On win32, openLogsFolder() must launch explorer on the logs directory."""
        monkeypatch.setattr(app_ctrl.sys, "platform", "win32")
        monkeypatch.setattr(app_ctrl, "get_logs_dir", lambda: "C:\\logs")
        run_mock = MagicMock()
        monkeypatch.setattr(app_ctrl.subprocess, "run", run_mock)
        controller.openLogsFolder()
        run_mock.assert_called_once_with(["explorer", "C:\\logs"], check=False)

    def test_open_logs_folder_non_windows(self, controller, monkeypatch):
        """On non-win32 platforms, openLogsFolder() must launch xdg-open."""
        monkeypatch.setattr(app_ctrl.sys, "platform", "linux")
        monkeypatch.setattr(app_ctrl, "get_logs_dir", lambda: "/tmp/logs")
        run_mock = MagicMock()
        monkeypatch.setattr(app_ctrl.subprocess, "run", run_mock)
        controller.openLogsFolder()
        run_mock.assert_called_once_with(["xdg-open", "/tmp/logs"], check=False)

    def test_open_logs_folder_swallows_failure(self, controller, monkeypatch):
        """A failure locating/opening the logs folder must not propagate."""
        monkeypatch.setattr(app_ctrl, "get_logs_dir", _raise)
        try:
            controller.openLogsFolder()
        except Exception as exc:
            pytest.fail(f"openLogsFolder() must not raise: {exc}")
