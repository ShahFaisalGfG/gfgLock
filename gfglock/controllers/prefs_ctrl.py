# prefs_ctrl.py - preferences (settings) controller

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, overload

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
    thread_limit,
)
from gfglock.core.file_ops import EXTENSIONS
from gfglock.services.read_size_test import MARGIN, Choice, ReadSizeTestWorker, SpeedResult
from gfglock.utils.logging import clear_logs, get_logs_dir, write_log
from gfglock.utils.settings import get_default_settings, load_settings, save_settings

_T = TypeVar("_T")
_NOT_SAVED = "Couldn't save the preferences file, so the previous preferences are still in use."
_WAIT_FOR_RUN = "Wait for the current run to finish, then try again."
_STOPPED = "Speed test stopped."
_STOPPED_BY_RUN = "The speed test stopped because a run started. Try again when it finishes."


class RunState(Protocol):
    """What the speed test watches on an EncryptController: its busy property and busyChanged signal."""

    busy: Any
    busyChanged: Any


class PrefsController(QObject):
    """Exposes application preferences to QML."""

    settingsChanged = Signal()
    themeChanged = Signal(str)
    # (success, message): the result of saveSettings, resetDefaults, or clearLogs.
    saveFinished = Signal(bool, str)
    readSizeTestChanged = Signal()
    # (encrypt read size, decrypt read size, encrypt files at a time, decrypt files at a time, message):
    # what the speed test picked and saved; -1 when it was not measured, stopped, or refused.
    readSizeTestFinished = Signal(int, int, int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = load_settings()
        self._runs: list[RunState] = []
        self._read_size_test: ReadSizeTestWorker | None = None
        self._read_size_progress = 0.0
        self._stopped_by_run = False

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
        """Bytes read at a time when encrypting; 0 is the default (4 MB)."""
        return int(self._get("encryption", "read_size", default=ReadSizeDefaults.DEFAULT) or 0)

    @Property(int, notify=settingsChanged)
    def decReadSize(self) -> int:
        """Bytes read at a time when decrypting; 0 is the default (4 MB)."""
        return int(self._get("decryption", "read_size", default=ReadSizeDefaults.DEFAULT) or 0)

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
        """{label, code, hint, ext} entries for the algorithm combo boxes; ext is the encrypted files' extension."""
        return [{"label": label, "code": code, "hint": hint, "ext": EXTENSIONS[AlgorithmDefaults.CIPHERS[code]]}
                for label, code, hint in AlgorithmDefaults.OPTIONS]

    @Property(list, constant=True)
    def readSizeOptions(self) -> list:
        """{label, code} entries for the read size combo boxes; code 0 is the default (4 MB)."""
        return [{"label": label, "code": size} for label, size in ReadSizeDefaults.OPTIONS]

    @Property(bool, notify=readSizeTestChanged)
    def readSizeTestRunning(self) -> bool:
        """True while the speed test runs."""
        return self._read_size_test is not None

    @Property(float, notify=readSizeTestChanged)
    def readSizeTestProgress(self) -> float:
        """Fraction (0-1) of the speed test done."""
        return self._read_size_progress

    @Property(list, constant=True)
    def logLevelOptions(self) -> list:
        """{label, code} entries for the log level combo box."""
        return [{"label": label, "code": code} for label, code in LoggingDefaults.OPTIONS]

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot("QVariantMap")
    def saveSettings(self, updates: dict) -> None:
        """Apply dotted-key updates (e.g. {"encryption.cpu_threads": 4}) and save them in one write."""
        self._save(updates)

    @Slot(str, bool)
    def rememberEncryptOptions(self, algorithm: str, hide_names: bool) -> None:
        """Save the Encrypt tab's method and Hide file names choices quietly (no saveFinished on success)."""
        if algorithm not in AlgorithmDefaults.SUPPORTED_ALGORITHMS:
            write_log(f"Ignored an unknown encryption method {algorithm!r}", "critical")
            return
        current = (self._get("advanced", "encryption_mode"), self._get("encryption", "encrypt_filenames"))
        if current != (algorithm, hide_names):
            self._save({"advanced.encryption_mode": algorithm, "encryption.encrypt_filenames": hide_names}, quiet=True)

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
        """Measure the fastest read size and files at a time with `algorithm` (a settings code) in the background.

        Refused while an encrypt or decrypt run is busy, since the run would skew every timing.
        """
        if self._read_size_test is not None:
            return
        if any(bool(run.busy) for run in self._runs):
            self.readSizeTestFinished.emit(-1, -1, -1, -1, _WAIT_FOR_RUN)
            return
        cipher = AlgorithmDefaults.CIPHERS.get(algorithm, AlgorithmDefaults.CIPHERS[AlgorithmDefaults.DEFAULT_ALGORITHM])
        limit = thread_limit(self._get("advanced", "clamp_cpu_threads", default=PerformanceDefaults.CLAMP_CPU_THREADS))
        worker = ReadSizeTestWorker(cipher, limit, EncryptionDefaults.DEFAULT_THREADS)
        worker.signals.progress.connect(self._on_read_size_progress)
        worker.signals.finished.connect(self._on_read_size_finished)
        self._read_size_test = worker
        self._read_size_progress = 0.0
        self._stopped_by_run = False
        self.readSizeTestChanged.emit()
        QThreadPool.globalInstance().start(worker)

    @Slot()
    def cancelReadSizeTest(self) -> None:
        """Stop the speed test; the file it is working on stops within a block."""
        if self._read_size_test is not None:
            self._read_size_test.cancel()

    def set_run_controllers(self, runs: Sequence[RunState]) -> None:
        """The encrypt and decrypt controllers: the speed test waits for their runs and stops when one starts."""
        self._runs = list(runs)
        for run in self._runs:
            run.busyChanged.connect(self._on_run_busy)

    def shutdown(self) -> None:
        """Stop background work before the app exits."""
        self.cancelReadSizeTest()

    def _on_run_busy(self, busy: bool) -> None:
        """A run that starts during the speed test would skew its timings, so the test stops."""
        if busy and self._read_size_test is not None:
            self._stopped_by_run = True
            self._read_size_test.cancel()

    def _on_read_size_progress(self, done: int, total: int) -> None:
        self._read_size_progress = done / total if total else 0.0
        self.readSizeTestChanged.emit()

    def _on_read_size_finished(self, result: SpeedResult | None, error: str) -> None:
        """Save what the test picked and tell QML; no result and no error means the test was stopped."""
        self._read_size_test = None
        self.readSizeTestChanged.emit()
        if error:
            write_log(f"Speed test failed: {error}", "critical")
            self.readSizeTestFinished.emit(-1, -1, -1, -1, error)
        elif result is None:
            self.readSizeTestFinished.emit(-1, -1, -1, -1, _STOPPED_BY_RUN if self._stopped_by_run else _STOPPED)
        else:
            encrypt, decrypt = result.encrypt, result.decrypt
            saved = self._save({
                "encryption.read_size": encrypt.read_size,
                "encryption.cpu_threads": encrypt.threads,
                "decryption.read_size": decrypt.read_size,
                "decryption.cpu_threads": decrypt.threads,
            }, quiet=True)
            if saved:
                self.readSizeTestFinished.emit(encrypt.read_size, decrypt.read_size, encrypt.threads,
                                               decrypt.threads, _describe_test(result) + " Saved.")
            else:  # nothing changed, so the lists keep showing the values in use
                self.readSizeTestFinished.emit(-1, -1, -1, -1, _describe_test(result) + " " + _NOT_SAVED)

    def _save(self, updates: dict[str, Any], quiet: bool = False) -> bool:
        """Apply dotted-key updates on top of the settings on disk and save them; see _persist."""
        theme_before = self._get("theme")
        self._settings = load_settings()  # another window or a theme change may have saved since
        for key, value in updates.items():
            self._set(value, *key.split("."))
        saved = self._persist(quiet)
        if self._get("theme") != theme_before:
            self.themeChanged.emit(self._get("theme", default=ThemeDefaults.DEFAULT_THEME))
        return saved

    def _persist(self, quiet: bool = False) -> bool:
        """Save the current settings and tell QML how it went; quiet skips the report of a success.

        Runs read the settings from disk, so after a failed save the settings shown go back to the
        ones on disk instead of showing values that aren't in use.
        """
        saved = save_settings(self._settings)
        if saved:
            if not quiet:
                self.saveFinished.emit(True, "")
        else:
            self._settings = load_settings()
            write_log("Could not save settings", "critical")
            self.saveFinished.emit(False, _NOT_SAVED)
        self.settingsChanged.emit()
        return saved


def _describe_test(result: SpeedResult) -> str:
    """'Best on this PC: 32 MB reads and the default 4 files at a time (410 MB/s) for encrypting and ...'"""
    return (f"Best on this PC: {_describe_choice(result.encrypt, EncryptionDefaults.DEFAULT_THREADS)} for encrypting "
            f"and {_describe_choice(result.decrypt, DecryptionDefaults.DEFAULT_THREADS)} for decrypting. "
            f"A value replaces the default only when it is at least {MARGIN:.0%} faster.")


def _describe_choice(choice: Choice, default_threads: int) -> str:
    """'32 MB reads and the default 4 files at a time (410 MB/s)'."""
    size = choice.read_size or ReadSizeDefaults.DEFAULT_BYTES
    reads = f"{size // (1024 * 1024)} MB reads"
    files = f"{choice.threads} {'file' if choice.threads == 1 else 'files'} at a time"
    if choice.read_size == ReadSizeDefaults.DEFAULT:
        reads = "the default " + reads
    if choice.threads == default_threads:
        files = "the default " + files
    return f"{reads} and {files} ({choice.bytes_per_s / 1e6:.0f} MB/s)"
