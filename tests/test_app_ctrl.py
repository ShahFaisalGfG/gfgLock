# test_app_ctrl.py - unit tests for gfglock.controllers.app_ctrl

import contextlib
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QUrl
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


@pytest.fixture
def stub_settings(monkeypatch):
    """Replace load_settings/save_settings with in-memory stand-ins."""
    store = {"theme": "system"}
    saved: list[dict] = []
    monkeypatch.setattr(app_ctrl, "load_settings", lambda: dict(store))
    monkeypatch.setattr(app_ctrl, "save_settings", lambda s: saved.append(dict(s)) or True)
    return store, saved


@pytest.fixture
def controller(monkeypatch, stub_settings):
    """AppController with system-theme detection stubbed to 'light'."""
    monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "light")
    return AppController()


class TestThemeDetection:
    """_detect_system_theme() must translate the registry value into light/dark and fail safe."""

    def test_light_value(self, monkeypatch):
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", lambda *a, **k: contextlib.nullcontext("key"))
        monkeypatch.setattr(app_ctrl.winreg, "QueryValueEx", lambda k, n: (1, 1))
        assert _detect_system_theme() == "light"

    def test_dark_value(self, monkeypatch):
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", lambda *a, **k: contextlib.nullcontext("key"))
        monkeypatch.setattr(app_ctrl.winreg, "QueryValueEx", lambda k, n: (0, 1))
        assert _detect_system_theme() == "dark"

    def test_missing_registry_value_defaults_light(self, monkeypatch):
        """A missing registry key (OSError) must fall back to 'light'."""
        monkeypatch.setattr(app_ctrl.winreg, "OpenKey", MagicMock(side_effect=FileNotFoundError()))
        assert _detect_system_theme() == "light"


class TestConstruction:
    def test_system_theme_resolved(self, monkeypatch, stub_settings):
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        assert AppController().currentTheme == "dark"

    def test_explicit_theme_bypasses_detection(self, monkeypatch, stub_settings):
        store, _ = stub_settings
        store["theme"] = "dark"
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: pytest.fail("detection must not run"))
        assert AppController().currentTheme == "dark"


class TestStaticProperties:
    def test_app_info_properties(self, controller):
        assert controller.appVersion == AppInfo.APP_VERSION
        assert controller.appName == AppInfo.APP_NAME
        assert controller.appDescription == AppInfo.APP_DESCRIPTION
        assert controller.appAuthor == AppInfo.APP_AUTHOR


class TestDetectTheme:
    """detectTheme() re-reads settings/registry and emits only on change."""

    def test_emits_when_theme_changes(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.detectTheme()
        assert controller.currentTheme == "dark"
        spy.assert_called_once_with("dark")

    def test_no_emit_when_theme_unchanged(self, controller):
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.detectTheme()
        spy.assert_not_called()


class TestApplyTheme:
    """applyTheme() persists the raw choice and resolves 'system' for display."""

    def test_explicit_theme_applied_and_saved(self, controller, stub_settings):
        _, saved = stub_settings
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.applyTheme("dark")
        assert controller.currentTheme == "dark"
        spy.assert_called_once_with("dark")
        assert saved[-1]["theme"] == "dark"

    def test_system_theme_resolved_but_raw_saved(self, controller, monkeypatch, stub_settings):
        _, saved = stub_settings
        monkeypatch.setattr(app_ctrl, "_detect_system_theme", lambda: "dark")
        controller.applyTheme("system")
        assert controller.currentTheme == "dark"
        assert saved[-1]["theme"] == "system"

    def test_failed_save_is_logged(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl, "save_settings", lambda s: False)
        log = MagicMock()
        monkeypatch.setattr(app_ctrl, "write_log", log)
        controller.applyTheme("dark")
        assert controller.currentTheme == "dark"
        log.assert_called_once()


class TestOpenedFiles:
    """Files from Explorer or a second launch reach QML through filesOpened."""

    def test_open_files_emits_mode_and_paths(self, controller):
        spy = MagicMock()
        controller.filesOpened.connect(spy)
        controller.openFiles("decrypt", ["C:\\a.gfglock"])
        spy.assert_called_once_with("decrypt", ["C:\\a.gfglock"])

    def test_is_folder_accepts_urls_and_paths(self, controller, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        assert controller.isFolder(str(tmp_path)) is True
        assert controller.isFolder(QUrl.fromLocalFile(str(tmp_path)).toString()) is True
        assert controller.isFolder(str(tmp_path / "file.txt")) is False


class TestUpdates:
    def test_open_updates_opens_browser(self, controller, monkeypatch):
        open_mock = MagicMock(return_value=True)
        monkeypatch.setattr(app_ctrl.webbrowser, "open", open_mock)
        controller.openUpdates()
        open_mock.assert_called_once_with(app_ctrl._UPDATES_URL)

    def test_browser_failure_is_logged(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl.webbrowser, "open", lambda url: False)
        log = MagicMock()
        monkeypatch.setattr(app_ctrl, "write_log", log)
        controller.openUpdates()
        log.assert_called_once()
