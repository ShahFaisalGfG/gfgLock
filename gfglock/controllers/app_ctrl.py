# app_ctrl.py - app-wide controller: theme, app information, and updates

import os
import webbrowser
import winreg

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from gfglock.config.defaults import AppInfo
from gfglock.utils.logging import write_log
from gfglock.utils.settings import load_settings, save_settings

_UPDATES_URL = "https://github.com/ShahFaisalGfG/gfgLock/releases"


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

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def detectTheme(self) -> None:
        """Re-detect the theme (called when a window regains focus) and emit themeChanged if it changed."""
        raw = load_settings().get("theme", "system")
        self._set_theme(_detect_system_theme() if raw == "system" else raw)

    @Slot(str)
    def applyTheme(self, theme: str) -> None:
        """Apply a theme choice ("system", "light", or "dark") and persist it."""
        self._set_theme(_detect_system_theme() if theme == "system" else theme)
        settings = load_settings()
        settings["theme"] = theme
        if not save_settings(settings):
            write_log("Could not save the theme choice", "critical")

    @Slot(str, list)
    def openFiles(self, mode: str, paths: list) -> None:
        """Hand files opened from outside the window (Explorer, a second launch) to QML."""
        self.filesOpened.emit(mode, list(paths))

    @Slot(str, result=bool)
    def isFolder(self, url: str) -> bool:
        """True when a dropped or opened file:/// URL (or plain path) is a folder."""
        local = QUrl(url).toLocalFile()
        return os.path.isdir(local or url)

    @Slot()
    def openUpdates(self) -> None:
        """Open the GitHub releases page in the default browser."""
        if not webbrowser.open(_UPDATES_URL):
            write_log(f"Could not open {_UPDATES_URL}", "critical")

    def _set_theme(self, theme: str) -> None:
        if theme != self._theme:
            self._theme = theme
            self.themeChanged.emit(theme)
