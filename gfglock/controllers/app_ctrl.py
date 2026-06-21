# app_ctrl.py - main window controller (theme, logs, about, updates)

import os
import subprocess
import sys
import webbrowser
import winreg

from PySide6.QtCore import Property, QObject, Signal, Slot

from gfglock.config.defaults import AppInfo
from gfglock.utils.logging import clear_logs, get_logs_dir
from gfglock.utils.settings import load_settings, save_settings

_UPDATES_URL = "https://github.com/ShahFaisalGfG/gfgLock/releases"


def _detect_system_theme() -> str:
    """Read Windows registry to determine light or dark mode."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        return "light"


class AppController(QObject):
    """Exposes main-window logic to QML."""

    themeChanged = Signal(str)
    logAppended = Signal(str)
    logsCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logs: list[str] = []
        settings = load_settings()
        raw = settings.get("theme", "system")
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

    @Property(int, constant=True)
    def cpuCount(self) -> int:
        """Number of logical CPU threads available on this machine."""
        return os.cpu_count() or 1

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def detectTheme(self) -> None:
        """Re-detect system theme and emit themeChanged if it changed."""
        try:
            settings = load_settings()
            raw = settings.get("theme", "system")
            new_theme = _detect_system_theme() if raw == "system" else raw
            if new_theme != self._theme:
                self._theme = new_theme
                self.themeChanged.emit(self._theme)
        except Exception:
            pass

    @Slot(str)
    def applyTheme(self, theme: str) -> None:
        """Apply a specific theme and persist it."""
        try:
            resolved = _detect_system_theme() if theme == "system" else theme
            if resolved != self._theme:
                self._theme = resolved
                self.themeChanged.emit(self._theme)
            settings = load_settings()
            settings["theme"] = theme
            save_settings(settings)
        except Exception:
            pass

    @Slot(str)
    def appendLog(self, message: str) -> None:
        """Add a message to the logs panel."""
        try:
            self._logs.append(message)
            self.logAppended.emit(message)
        except Exception:
            pass

    @Slot()
    def clearLogs(self) -> None:
        """Clear in-memory and on-disk logs."""
        try:
            self._logs.clear()
            clear_logs()
            self.logsCleared.emit()
        except Exception:
            pass

    @Slot()
    def openUpdates(self) -> None:
        """Open the GitHub releases page in the default browser."""
        try:
            webbrowser.open(_UPDATES_URL)
        except Exception:
            pass

    @Slot()
    def openLogsFolder(self) -> None:
        """Open the logs directory in Windows Explorer."""
        try:
            logs_dir = get_logs_dir()
            if sys.platform == "win32":
                subprocess.run(["explorer", logs_dir], check=False)
            else:
                subprocess.run(["xdg-open", logs_dir], check=False)
        except Exception:
            pass
