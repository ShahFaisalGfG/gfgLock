# prefs_ctrl.py — preferences (settings) controller

import os
import subprocess
import sys
from typing import Any, TypeVar, overload

from PySide6.QtCore import Property, QObject, Signal, Slot

_T = TypeVar("_T")

from gfglock.config.defaults import (
    AlgorithmDefaults,
    EncryptionDefaults,
    DecryptionDefaults,
    LoggingDefaults,
    PerformanceDefaults,
    ThemeDefaults,
)
from gfglock.config.ui_config import EncryptionModes, ChunkSizeOptions
from gfglock.utils.logging import clear_logs, get_logs_dir
from gfglock.utils.settings import get_default_settings, load_settings, save_settings


class PrefsController(QObject):
    """Exposes application preferences to QML."""

    settingsChanged = Signal()
    themeChanged = Signal(str)
    logsCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = load_settings()

    # ── Settings access helpers ───────────────────────────────────────────

    @overload
    def _get(self, *keys: str, default: _T) -> _T: ...
    @overload
    def _get(self, *keys: str, default: None = ...) -> Any: ...
    def _get(self, *keys: str, default=None):
        """Navigate nested settings keys and return the value."""
        try:
            val = self._settings
            for k in keys:
                val = val[k]
            return val
        except Exception:
            return default

    def _set(self, value, *keys) -> None:
        """Set a nested settings value without saving to disk."""
        try:
            node = self._settings
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
        except Exception:
            pass

    # ── Properties ────────────────────────────────────────────────────────

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._get("theme", default=ThemeDefaults.DEFAULT_THEME)

    @Property(int, notify=settingsChanged)
    def encThreads(self) -> int:
        return self._get("encryption", "cpu_threads", default=EncryptionDefaults.DEFAULT_THREADS)

    @Property(object, notify=settingsChanged)
    def encChunkSize(self):
        return self._get("encryption", "chunk_size", default=EncryptionDefaults.DEFAULT_CHUNK_SIZE)

    @Property(bool, notify=settingsChanged)
    def encFilenames(self) -> bool:
        return self._get("encryption", "encrypt_filenames", default=False)

    @Property(int, notify=settingsChanged)
    def decThreads(self) -> int:
        return self._get("decryption", "cpu_threads", default=DecryptionDefaults.DEFAULT_THREADS)

    @Property(object, notify=settingsChanged)
    def decChunkSize(self):
        return self._get("decryption", "chunk_size", default=DecryptionDefaults.DEFAULT_CHUNK_SIZE)

    @Property(bool, notify=settingsChanged)
    def decFilenames(self) -> bool:
        return self._get("decryption", "encrypt_filenames", default=DecryptionDefaults.DEFAULT_ENCRYPT_FILENAMES)

    @Property(str, notify=settingsChanged)
    def encMode(self) -> str:
        return self._get("advanced", "encryption_mode", default=AlgorithmDefaults.DEFAULT_ALGORITHM)

    @Property(bool, notify=settingsChanged)
    def enableLogs(self) -> bool:
        return self._get("advanced", "enable_logs", default=LoggingDefaults.ENABLE_LOGS)

    @Property(str, notify=settingsChanged)
    def logLevel(self) -> str:
        return self._get("advanced", "log_level", default=LoggingDefaults.DEFAULT_LOG_LEVEL)

    @Property(bool, notify=settingsChanged)
    def clampThreads(self) -> bool:
        """True when one CPU thread is reserved for the OS (default on)."""
        return self._get("advanced", "clamp_cpu_threads", default=PerformanceDefaults.CLAMP_CPU_THREADS)

    @Property(int, notify=settingsChanged)
    def maxThreads(self) -> int:
        """Maximum selectable thread count, respecting the clamping setting."""
        total = os.cpu_count() or 1
        return max(1, total - 1) if self.clampThreads else total

    @Property(list, constant=True)
    def encryptionModeOptions(self) -> list:
        """Return list of {label, value} dicts for encryption algorithm dropdown."""
        return [{"label": label, "value": val} for label, val in EncryptionModes.get_options()]

    @Property(list, constant=True)
    def chunkSizeOptions(self) -> list:
        """Return list of {label, value} dicts for chunk size dropdown."""
        return [
            {"label": label, "value": val if val is not None else -1}
            for label, val in ChunkSizeOptions.get_options()
        ]

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot()
    def loadSettings(self) -> None:
        """Reload settings from disk and notify QML."""
        try:
            self._settings = load_settings()
            self.settingsChanged.emit()
        except Exception:
            pass

    @Slot("QVariantMap")
    def saveSettings(self, updates: dict) -> None:
        """Merge updates dict into current settings and persist."""
        try:
            theme_before = self._get("theme")
            for key, value in updates.items():
                keys = key.split(".")
                self._set(value, *keys)
            save_settings(self._settings)
            self.settingsChanged.emit()
            if self._get("theme") != theme_before:
                self.themeChanged.emit(self._get("theme", default="system"))
        except Exception:
            pass

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value) -> None:
        """Set a single dot-separated key and persist immediately."""
        try:
            keys = key.split(".")
            self._set(value, *keys)
            save_settings(self._settings)
            self.settingsChanged.emit()
            if key == "theme":
                self.themeChanged.emit(str(value))
        except Exception:
            pass

    @Slot()
    def resetDefaults(self) -> None:
        """Reset all settings to factory defaults and persist."""
        try:
            self._settings = get_default_settings()
            save_settings(self._settings)
            self.settingsChanged.emit()
            self.themeChanged.emit(self._settings.get("theme", "system"))
        except Exception:
            pass

    @Slot()
    def clearLogs(self) -> None:
        """Delete all log file contents."""
        try:
            clear_logs()
            self.logsCleared.emit()
        except Exception:
            pass

    @Slot()
    def openLogsFolder(self) -> None:
        """Open the logs directory in the OS file manager."""
        try:
            logs_dir = get_logs_dir()
            if sys.platform == "win32":
                subprocess.run(["explorer", logs_dir], check=False)
            else:
                subprocess.run(["xdg-open", logs_dir], check=False)
        except Exception:
            pass
