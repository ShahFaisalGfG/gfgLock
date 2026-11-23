# app_ctrl.py - app-wide controller: theme, app information, screens, and start-up notices

import ctypes
import os
import winreg

from PySide6.QtCore import Property, QObject, QPoint, QRect, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from gfglock.config.defaults import AppInfo, UpdateInfo
from gfglock.core import passwords
from gfglock.core.file_ops import ENCRYPTED_EXTS
from gfglock.utils.settings import load_settings, take_read_error

_SETTINGS_RESET = "Your preferences file couldn't be read, so the defaults are in use."
_VK_CAPITAL = 0x14

_GetKeyState = ctypes.WinDLL("user32").GetKeyState
_GetKeyState.argtypes = [ctypes.c_int]
_GetKeyState.restype = ctypes.c_short


def _detect_system_theme() -> str:
    """Read Windows registry to determine light or dark mode."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except OSError:  # the value is missing on some Windows editions; light is Windows' default
        return "light"


class AppController(QObject):
    """Exposes app-wide state and actions to QML."""

    themeChanged = Signal(str)
    # (mode, paths): files opened from Explorer or passed on by a second launch. The window
    # switches to that mode's tab and adds them.
    filesOpened = Signal(str, list)
    # A second launch asked this window to come to the front.
    activateRequested = Signal()
    # A start-up message for the user (launch paths not found, an unreadable file list, the
    # preferences file reset); the window shows it as a toast.
    notice = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        raw = load_settings().get("theme", "system")
        self._theme = _detect_system_theme() if raw == "system" else raw

    # ── Properties ──────────────────────────────────────────────────────────

    @Property(str, notify=themeChanged)
    def currentTheme(self) -> str:
        """Current resolved theme name ("light" or "dark")."""
        return self._theme

    @Property(str, constant=True)
    def appVersion(self) -> str:
        """Application version string."""
        return AppInfo.APP_VERSION

    @Property(str, constant=True)
    def appName(self) -> str:
        """Application display name."""
        return AppInfo.APP_NAME

    @Property(str, constant=True)
    def appDescription(self) -> str:
        """Short application description."""
        return AppInfo.APP_DESCRIPTION

    @Property(str, constant=True)
    def appAuthor(self) -> str:
        """Application author."""
        return AppInfo.APP_AUTHOR

    @Property(str, constant=True)
    def privacyUrl(self) -> str:
        """The privacy policy on the project's site."""
        return UpdateInfo.PRIVACY_URL

    @Property(str, constant=True)
    def licensesUrl(self) -> str:
        """The licences of gfgLock and the software it includes."""
        return UpdateInfo.LICENSES_URL

    @Property(str, constant=True)
    def issuesUrl(self) -> str:
        """Where to report a problem."""
        return UpdateInfo.ISSUES_URL

    @Property(list, constant=True)
    def encryptedExtensions(self) -> list:
        """The extensions of gfgLock's encrypted files, sorted (".gfgcha", ".gfglck", ".gfglock")."""
        return sorted(ENCRYPTED_EXTS)

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def detectTheme(self) -> None:
        """Re-detect the theme (a window regained focus, or Preferences saved a new one) and emit
        themeChanged if it changed."""
        raw = load_settings().get("theme", "system")
        self._set_theme(_detect_system_theme() if raw == "system" else raw)

    @Slot(str, list)
    def openFiles(self, mode: str, paths: list) -> None:
        """Hand files opened from outside the window (Explorer, a second launch) to QML."""
        self.filesOpened.emit(mode, list(paths))

    @Slot(str, result=bool)
    def isFolder(self, url: str) -> bool:
        """True when a dropped or opened file:/// URL (or plain path) is a folder."""
        local = QUrl(url).toLocalFile()
        return os.path.isdir(local or url)

    @Slot(int, int, result=QRect)
    def availableGeometry(self, x: int, y: int) -> QRect:
        """The area windows may use (without the taskbar) on the screen at (x, y), else the primary screen."""
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    @Slot(str, result=int)
    def passwordStrength(self, password: str) -> int:
        """0 empty, 1 very weak, 2 weak, 3 fair, 4 good, 5 strong (core/passwords.py)."""
        return passwords.strength(password)

    @Slot(result=bool)
    def capsLockOn(self) -> bool:
        """True while Caps Lock is on, for the hint under a password field."""
        return bool(_GetKeyState(_VK_CAPITAL) & 1)

    def show_notices(self, *notices: str) -> None:
        """Show the start-up notices as one toast, adding one when the preferences file couldn't be read."""
        if take_read_error():
            notices = (*notices, _SETTINGS_RESET)
        text = " ".join(notice for notice in notices if notice)
        if text:
            self.notice.emit(text)

    def _set_theme(self, theme: str) -> None:
        if theme != self._theme:
            self._theme = theme
            self.themeChanged.emit(theme)
