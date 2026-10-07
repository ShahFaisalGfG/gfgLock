# prefs_ctrl.py - preferences (settings) controller

import os
from typing import Any, TypeVar, overload

from PySide6.QtCore import Property, QObject, QThreadPool, Signal, Slot

from gfglock.config.defaults import (
    AlgorithmDefaults,
    DecryptionDefaults,
    EncryptionDefaults,
    LoggingDefaults,
    NotificationDefaults,
    PerformanceDefaults,
    ReadSizeDefaults,
    ThemeDefaults,
)
from gfglock.services.read_size_test import TEST_FILE_SIZE, ReadSizeTestWorker, SizeTiming, pick_fastest
from gfglock.utils.logging import clear_logs, get_logs_dir, write_log
from gfglock.utils.settings import get_default_settings, load_settings, save_settings

_T = TypeVar("_T")


class PrefsController(QObject):
    """Exposes application preferences to QML."""

    settingsChanged = Signal()
    themeChanged = Signal(str)
    # (success, message): the result of saveSettings, resetDefaults, or clearLogs.
    saveFinished = Signal(bool, str)
    readSizeTestChanged = Signal()
    # (encrypt read size, decrypt read size, message): sizes are -1 when the test failed or stopped.
    readSizeTestFinished = Signal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = load_settings()
        self._read_size_test: ReadSizeTestWorker | None = None
        self._read_size_progress = 0.0

    # ── Settings access helpers ───────────────────────────────────────────

    @overload
    def _get(self, *keys: str, default: _T) -> _T: ...
    @overload
    def _get(self, *keys: str, default: None = ...) -> Any: ...
    def _get(self, *keys: str, default=None):
        """Navigate nested settings keys and return the value, or `default` when missing."""
        node: Any = self._settings
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def _set(self, value, *keys) -> None:
        """Set a nested settings value without saving to disk."""
        node = self._settings
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value

    # ── Properties ────────────────────────────────────────────────────────

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._get("theme", default=ThemeDefaults.DEFAULT_THEME)

    @Property(int, notify=settingsChanged)
    def encThreads(self) -> int:
        return self._get("encryption", "cpu_threads", default=EncryptionDefaults.DEFAULT_THREADS)

    @Property(int, notify=settingsChanged)
    def encReadSize(self) -> int:
        """Bytes read at a time when encrypting; 0 is Automatic."""
        return int(self._get("encryption", "read_size", default=ReadSizeDefaults.AUTOMATIC) or 0)

    @Property(int, notify=settingsChanged)
    def decReadSize(self) -> int:
        """Bytes read at a time when decrypting; 0 is Automatic."""
        return int(self._get("decryption", "read_size", default=ReadSizeDefaults.AUTOMATIC) or 0)

    @Property(bool, notify=settingsChanged)
    def encFilenames(self) -> bool:
        return self._get("encryption", "encrypt_filenames", default=EncryptionDefaults.DEFAULT_ENCRYPT_FILENAMES)

    @Property(int, notify=settingsChanged)
    def decThreads(self) -> int:
        return self._get("decryption", "cpu_threads", default=DecryptionDefaults.DEFAULT_THREADS)

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

    @Property(bool, notify=settingsChanged)
    def operationNotifications(self) -> bool:
        """True when desktop notifications fire on operation completion (default on)."""
        return self._get("advanced", "operation_notifications", default=NotificationDefaults.OPERATION_NOTIFICATIONS)

    @Property(int, constant=True)
    def cpuCount(self) -> int:
        """Logical CPU threads on this machine; the thread lists offer 1 up to this."""
        return os.cpu_count() or 1

    @Property(list, constant=True)
    def themeOptions(self) -> list:
        """{label, code} entries for the theme combo box."""
        return [{"label": label, "code": code} for label, code in ThemeDefaults.OPTIONS]

    @Property(list, constant=True)
    def algorithmOptions(self) -> list:
        """{label, code, hint} entries for the algorithm combo box."""
        return [{"label": label, "code": code, "hint": hint} for label, code, hint in AlgorithmDefaults.OPTIONS]

    @Property(list, constant=True)
    def readSizeOptions(self) -> list:
        """{label, code} entries for the read size combo boxes; code 0 is Automatic."""
        return [{"label": label, "code": size} for label, size in ReadSizeDefaults.OPTIONS]

    @Property(bool, notify=readSizeTestChanged)
    def readSizeTestRunning(self) -> bool:
        """True while the read size speed test runs."""
        return self._read_size_test is not None

    @Property(float, notify=readSizeTestChanged)
    def readSizeTestProgress(self) -> float:
        """Fraction (0-1) of the read size speed test done."""
        return self._read_size_progress

    @Property(list, constant=True)
    def logLevelOptions(self) -> list:
        """{label, code} entries for the log level combo box."""
        return [{"label": label, "code": code} for label, code in LoggingDefaults.OPTIONS]

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot("QVariantMap")
    def saveSettings(self, updates: dict) -> None:
        """Apply dotted-key updates (e.g. {"encryption.cpu_threads": 4}) and save them in one write."""
        theme_before = self._get("theme")
        for key, value in updates.items():
            keys = key.split(".")
            self._set(value, *keys)
        self._persist()
        if self._get("theme") != theme_before:
            self.themeChanged.emit(self._get("theme", default=ThemeDefaults.DEFAULT_THEME))

    @Slot()
    def resetDefaults(self) -> None:
        """Reset all settings to factory defaults and save them."""
        self._settings = get_default_settings()
        self._persist()
        self.themeChanged.emit(self._get("theme", default=ThemeDefaults.DEFAULT_THEME))

    @Slot()
    def clearLogs(self) -> None:
        """Empty the log files."""
        if clear_logs():
            self.saveFinished.emit(True, "Logs cleared.")
        else:
            self.saveFinished.emit(False, "Couldn't clear the log files; they may be open in another program.")

    @Slot()
    def openLogsFolder(self) -> None:
        """Open the logs folder in File Explorer."""
        try:
            os.startfile(get_logs_dir())  # type: ignore[attr-defined]
        except OSError as error:
            write_log(f"Could not open the logs folder: {error}", "critical")
            self.saveFinished.emit(False, "Couldn't open the logs folder.")

    @Slot(str)
    def startReadSizeTest(self, algorithm: str) -> None:
        """Time every read size with `algorithm` (a settings code) in the background."""
        if self._read_size_test is not None:
            return
        cipher = AlgorithmDefaults.CIPHERS.get(algorithm, AlgorithmDefaults.CIPHERS[AlgorithmDefaults.DEFAULT_ALGORITHM])
        worker = ReadSizeTestWorker(ReadSizeDefaults.SIZES, cipher)
        worker.signals.progress.connect(self._on_read_size_progress)
        worker.signals.finished.connect(self._on_read_size_finished)
        self._read_size_test = worker
        self._read_size_progress = 0.0
        self.readSizeTestChanged.emit()
        QThreadPool.globalInstance().start(worker)

    @Slot()
    def cancelReadSizeTest(self) -> None:
        """Stop the read size speed test before its next step."""
        if self._read_size_test is not None:
            self._read_size_test.cancel()

    def shutdown(self) -> None:
        """Stop background work before the app exits."""
        self.cancelReadSizeTest()

    def _on_read_size_progress(self, done: int, total: int) -> None:
        self._read_size_progress = done / total if total else 0.0
        self.readSizeTestChanged.emit()

    def _on_read_size_finished(self, timings: list, error: str) -> None:
        """Pick the fastest sizes and tell QML; an empty result means the test was stopped."""
        self._read_size_test = None
        self.readSizeTestChanged.emit()
        if error:
            write_log(f"Read size test failed: {error}", "critical")
            self.readSizeTestFinished.emit(-1, -1, error)
        elif not timings:
            self.readSizeTestFinished.emit(-1, -1, "Speed test stopped.")
        else:
            encrypt = pick_fastest(timings, lambda t: t.encrypt_s, ReadSizeDefaults.AUTOMATIC_BYTES)
            decrypt = pick_fastest(timings, lambda t: t.decrypt_s, ReadSizeDefaults.AUTOMATIC_BYTES)
            self.readSizeTestFinished.emit(encrypt, decrypt, _describe_test(timings, encrypt, decrypt))

    def _persist(self) -> None:
        """Save the current settings and tell QML how it went."""
        saved = save_settings(self._settings)
        self.settingsChanged.emit()
        if saved:
            self.saveFinished.emit(True, "")
        else:
            write_log("Could not save settings", "critical")
            self.saveFinished.emit(False, "Couldn't save the preferences file.")


def _describe_test(timings: list[SizeTiming], encrypt: int, decrypt: int) -> str:
    """'Fastest on this PC: 32 MB when encrypting (310 MB/s), Automatic when decrypting (295 MB/s).'"""
    labels = {size: label.split(" (")[0] for label, size in ReadSizeDefaults.OPTIONS}
    by_size = {t.read_size: t for t in timings}

    def speed(size: int, seconds_of) -> str:
        timing = by_size[size or ReadSizeDefaults.AUTOMATIC_BYTES]
        return f"{TEST_FILE_SIZE / seconds_of(timing) / 1e6:.0f} MB/s"

    return (f"Fastest on this PC: {labels[encrypt]} when encrypting ({speed(encrypt, lambda t: t.encrypt_s)}), "
            f"{labels[decrypt]} when decrypting ({speed(decrypt, lambda t: t.decrypt_s)}). "
            "Automatic is kept unless another size is at least 5% faster.")
