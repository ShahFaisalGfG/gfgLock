# test_app_ctrl.py - unit tests for gfglock.controllers.app_ctrl

import contextlib
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QRect, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import AppInfo
from gfglock.controllers import app_ctrl
from gfglock.controllers.app_ctrl import AppController, _detect_system_theme
from gfglock.core.file_ops import ENCRYPTED_EXTS


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def stub_settings(monkeypatch):
    """Replace load_settings with an in-memory stand-in, and record any save (there should be none)."""
    store = {"theme": "system"}
    saved: list[dict] = []
    monkeypatch.setattr(app_ctrl, "load_settings", lambda: dict(store))
    monkeypatch.setattr("gfglock.utils.settings.save_settings", lambda s: saved.append(dict(s)) or True)
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


class TestThemePreview:
    """Preferences previews a theme without saving it; closing goes back to the saved one."""

    def test_preview_shows_without_saving(self, controller, stub_settings):
        _, saved = stub_settings
        spy = MagicMock()
        controller.themeChanged.connect(spy)
        controller.previewTheme("dark")
        assert controller.currentTheme == "dark"
        spy.assert_called_once_with("dark")
        controller.previewTheme("system")
        assert controller.currentTheme == "light"
        assert saved == []

    def test_preview_survives_the_window_being_activated_again(self, controller):
        controller.previewTheme("dark")
        controller.detectTheme()  # Preferences regained focus after an Alt+Tab
        assert controller.currentTheme == "dark"

    def test_ending_the_preview_shows_the_saved_theme(self, controller, stub_settings):
        store, _ = stub_settings
        controller.previewTheme("dark")
        controller.endPreview()  # closed without saving
        assert controller.currentTheme == "light"
        store["theme"] = "dark"  # saved, then closed
        controller.previewTheme("dark")
        controller.endPreview()
        assert controller.currentTheme == "dark"


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


class TestScreens:
    """availableGeometry() lets a window centre, maximize and clamp within its own monitor."""

    def test_point_on_a_screen_gives_that_screens_work_area(self, controller):
        screen = QGuiApplication.primaryScreen()
        centre = screen.geometry().center()
        assert controller.availableGeometry(centre.x(), centre.y()) == screen.availableGeometry()

    def test_point_off_every_screen_falls_back_to_the_primary(self, controller):
        assert controller.availableGeometry(-100_000, -100_000) == QGuiApplication.primaryScreen().availableGeometry()

    def test_screen_at_the_point_is_used(self, controller, monkeypatch):
        other = MagicMock()
        other.availableGeometry.return_value = QRect(1920, 0, 1280, 984)
        monkeypatch.setattr(app_ctrl.QGuiApplication, "screenAt", lambda point: other)
        assert controller.availableGeometry(2000, 10) == QRect(1920, 0, 1280, 984)


class TestKeyboard:
    @pytest.mark.parametrize("state, expected", [(0x0001, True), (0x0000, False), (-0x7FFF, True), (-0x8000, False)])
    def test_caps_lock_reads_the_toggle_bit(self, controller, monkeypatch, state, expected):
        keys: list[int] = []
        monkeypatch.setattr(app_ctrl, "_GetKeyState", lambda key: keys.append(key) or state)
        assert controller.capsLockOn() is expected
        assert keys == [0x14]  # VK_CAPITAL


class TestEncryptedExtensions:
    def test_lists_every_encrypted_extension_once_sorted(self, controller):
        assert controller.encryptedExtensions == sorted(ENCRYPTED_EXTS)
        assert controller.encryptedExtensions == [".gfgcha", ".gfglck", ".gfglock"]


class TestNotices:
    """Start-up notices reach QML through one notice signal."""

    def _notices(self, controller) -> list:
        notices: list = []
        controller.notice.connect(notices.append)
        return notices

    def test_launch_notice_is_shown(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl, "take_read_error", lambda: False)
        notices = self._notices(controller)
        controller.show_notices("2 items couldn't be found.")
        assert notices == ["2 items couldn't be found."]

    def test_damaged_preferences_file_is_reported_with_the_launch_notice(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl, "take_read_error", lambda: True)
        notices = self._notices(controller)
        controller.show_notices("1 item couldn't be found.")
        assert notices == ["1 item couldn't be found. Your preferences file couldn't be read, so the defaults are in use."]

    def test_nothing_to_say_emits_nothing(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl, "take_read_error", lambda: False)
        notices = self._notices(controller)
        controller.show_notices("")
        assert notices == []


class TestUpdates:
    def test_open_updates_goes_through_the_shell(self, controller, monkeypatch):
        open_mock = MagicMock(return_value=True)
        monkeypatch.setattr(app_ctrl.QDesktopServices, "openUrl", open_mock)
        controller.openUpdates()
        open_mock.assert_called_once()
        assert open_mock.call_args.args[0].toString() == app_ctrl._UPDATES_URL

    def test_browser_failure_is_logged(self, controller, monkeypatch):
        monkeypatch.setattr(app_ctrl.QDesktopServices, "openUrl", lambda url: False)
        log = MagicMock()
        monkeypatch.setattr(app_ctrl, "write_log", log)
        controller.openUpdates()
        log.assert_called_once()
