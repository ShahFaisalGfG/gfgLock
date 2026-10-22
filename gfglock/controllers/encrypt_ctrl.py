# encrypt_ctrl.py - one tab's file queue and the encrypt or decrypt runs over it

import ctypes
import os
import time
from ctypes import wintypes

from PySide6.QtCore import Property, QObject, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import (
    AlgorithmDefaults,
    DecryptionDefaults,
    EncryptionDefaults,
    NotificationDefaults,
    PerformanceDefaults,
    ReadSizeDefaults,
    thread_limit,
)
from gfglock.core import file_ops
from gfglock.core.format_v2 import KeyRing
from gfglock.models.file_model import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_WAITING,
    STATUS_WORKING,
    FileListModel,
)
from gfglock.services.folder_scanner import FolderScanWorker, ScanReport
from gfglock.services.notifier import notify
from gfglock.services.worker import OUTCOME_DONE, OUTCOME_SKIPPED, EncryptDecryptWorker
from gfglock.utils.logging import write_log, write_session_separator
from gfglock.utils.settings import load_settings

MODE_ENCRYPT = "encrypt"
MODE_DECRYPT = "decrypt"
# Settings section and defaults that hold each mode's thread count and read size.
_PERFORMANCE = {MODE_ENCRYPT: ("encryption", EncryptionDefaults), MODE_DECRYPT: ("decryption", DecryptionDefaults)}

_ALGO_NAMES = {option[1]: option[0] for option in AlgorithmDefaults.OPTIONS}
_OUTCOME_STATUS = {OUTCOME_DONE: STATUS_DONE, OUTCOME_SKIPPED: STATUS_SKIPPED}
# runChanged reaches QML at most this often during a run; the final state is sent at once.
_REFRESH_MS = 100
# Progress shown until the run has ended: the last files are still being flushed to disk.
_RUNNING_PROGRESS_CAP = 0.99
# A run longer than this sends its notification even while the window is in front.
_NOTIFY_AFTER_S = 10.0
# How long shutdown waits for cancelled folder scans (they stop at their next directory entry).
_SCAN_STOP_WAIT_MS = 2000

_shell32 = ctypes.WinDLL("shell32")
_shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
_shell32.ILCreateFromPathW.restype = ctypes.c_void_p
_shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
_shell32.SHOpenFolderAndSelectItems.restype = ctypes.HRESULT  # raises OSError for a failure code
_shell32.ILFree.argtypes = [ctypes.c_void_p]
_shell32.ILFree.restype = None


def _plural(count: int, noun: str) -> str:
    """'1 file', '3 files'."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _were(count: int) -> str:
    """'was' for one, 'were' for any other count."""
    return "was" if count == 1 else "were"


def _duration(seconds: float) -> str:
    """'under 0.1 s', '2.1 s', '3 min 5 s', or '1 h 2 min'."""
    if seconds < 0.1:
        return "under 0.1 s"
    if round(seconds, 1) < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min" + (f" {secs} s" if secs else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h" + (f" {minutes} min" if minutes else "")


def _lower_first(text: str) -> str:
    """A sentence made to continue another one: 'Wrong password' -> 'wrong password' (not 'NTFS')."""
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


def _select_in_explorer(path: str) -> None:
    """Open File Explorer at the file's folder with the file selected; raises OSError on failure.

    The shell call needs COM, which Qt has already initialised on the GUI thread.
    """
    item = _shell32.ILCreateFromPathW(path)
    if not item:
        raise OSError(f"File Explorer can't find {path}")
    try:
        _shell32.SHOpenFolderAndSelectItems(item, 0, None, 0)
    finally:
        _shell32.ILFree(item)


class EncryptController(QObject):
    """Owns one tab's file list and runs encryption (or decryption) over it."""

    busyChanged = Signal(bool)
    scanChanged = Signal()                 # folder scan started/progressed/ended
    runChanged = Signal()                  # progress, file counts, or current file changed
    summaryChanged = Signal()
    notice = Signal(str)                   # a short message for the user (shown as a toast)
    operationFinished = Signal(float, int, int, int, int)  # elapsed, total, ok, failed, skipped

    def __init__(self, mode: str = MODE_ENCRYPT, parent=None):
        super().__init__(parent)
        self._mode = MODE_DECRYPT if mode == MODE_DECRYPT else MODE_ENCRYPT
        self._file_model = FileListModel(self)
        self._threadpool = QThreadPool.globalInstance()
        # Scans get their own pool so a run (or a speed test) never holds them up.
        self._scan_pool = QThreadPool(self)
        self._worker: EncryptDecryptWorker | None = None
        self._scans: dict[int, FolderScanWorker] = {}  # every scan until its finished signal arrives
        self._scan: FolderScanWorker | None = None     # the scan new files and folders join
        self._scan_report = ScanReport()
        self._scan_found = 0
        self._scan_added = 0
        self._busy = False
        self._cancel_requested = False
        self._progress = 0.0
        self._files_done = 0
        self._files_total = 0
        self._current_file = ""
        self._failure_reasons: set[str] = set()
        self._files_stopped = 0  # files of the current run that Stop ended unchanged
        self._summary = ""
        self._last_folder = ""
        self._run_timer = QTimer(self)
        self._run_timer.setSingleShot(True)
        self._run_timer.setInterval(_REFRESH_MS)
        self._run_timer.timeout.connect(self._emit_run)
        self._run_sent = 0.0
        # The last run's summary describes the list as it was; adding or removing files ends that.
        self._file_model.countChanged.connect(self._clear_summary)

    # ── Properties ──────────────────────────────────────────────────────────

    @Property(str, constant=True)
    def mode(self) -> str:
        """"encrypt" or "decrypt"."""
        return self._mode

    @Property(QObject, constant=True)
    def fileModel(self) -> FileListModel:
        """The file list model exposed to QML."""
        return self._file_model

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        """True while files are being encrypted or decrypted."""
        return self._busy

    @Property(bool, notify=scanChanged)
    def scanning(self) -> bool:
        """True while added files and folders are being checked in the background."""
        return any(not scan.cancelled for scan in self._scans.values())

    @Property(int, notify=scanChanged)
    def scanFound(self) -> int:
        """Files found so far by the running scan, across every folder that joined it."""
        return self._scan_found

    @Property(float, notify=runChanged)
    def progress(self) -> float:
        """Progress of the current run from 0 to 1, by bytes read; 1 only once the run has ended."""
        return self._progress

    @Property(int, notify=runChanged)
    def filesDone(self) -> int:
        """Files finished in the current run."""
        return self._files_done

    @Property(int, notify=runChanged)
    def filesTotal(self) -> int:
        """Files in the current run."""
        return self._files_total

    @Property(str, notify=runChanged)
    def currentFile(self) -> str:
        """Name of the file most recently started."""
        return self._current_file

    @Property(bool, notify=runChanged)
    def cancelling(self) -> bool:
        """True after Cancel until the files in progress have stopped."""
        return self._busy and self._cancel_requested

    @Property(str, notify=summaryChanged)
    def summary(self) -> str:
        """One-line result of the last run ("" before the first)."""
        return self._summary

    @Property(str, notify=summaryChanged)
    def lastFolder(self) -> str:
        """Folder of the last file written, for "Open folder"."""
        return self._last_folder

    # ── Adding files ────────────────────────────────────────────────────────

    @Slot(list)
    def addFiles(self, urls: list) -> None:
        """Accept file:/// URLs or plain paths; files and folders are checked in the background."""
        paths = (self._url_to_path(url) for url in urls if url)
        self._scan_paths(list(dict.fromkeys(path for path in paths if path)))

    @Slot(str)
    def addFolder(self, url: str) -> None:
        """Scan a folder and its subfolders in the background, adding results in batches."""
        folder = self._url_to_path(url)
        if folder:
            self._scan_paths([folder])

    @Slot()
    def cancelScan(self) -> None:
        """Stop the running scan; files already in the list stay there."""
        if not self.scanning:
            return
        for scan in self._scans.values():
            scan.cancel()
        self._scan = None
        self.scanChanged.emit()

    @Slot()
    def clearFiles(self) -> None:
        """Stop any folder scan and remove all files from the list."""
        self.cancelScan()
        self._file_model.clearAll()
        if self._last_folder:  # "Open folder" belongs to the files just cleared
            self._last_folder = ""
            self.summaryChanged.emit()

    def shutdown(self) -> None:
        """Stop background work before exit: scans stop at once, files in progress stop unchanged."""
        self.cancelScan()
        self.cancel()
        self._scan_pool.waitForDone(_SCAN_STOP_WAIT_MS)

    # ── Running ─────────────────────────────────────────────────────────────

    @Slot(str, bool, str)
    def start(self, password: str, encrypt_names: bool = False, algorithm: str = "") -> None:
        """Encrypt or decrypt every file that isn't finished yet with `password`."""
        if self._busy or not password:
            return
        paths = self._file_model.runnable_paths()
        if not paths:
            return
        try:
            keys = KeyRing(password)
        except ValueError as error:  # a password that can't be turned into a key
            reason = str(error)
            self.notice.emit(f"{reason[:1].upper()}{reason[1:]}.")
            return
        settings = load_settings()
        section_name, defaults = _PERFORMANCE[self._mode]
        section = settings.get(section_name, {})
        threads = self._clamp_threads(int(section.get("cpu_threads", defaults.DEFAULT_THREADS)), settings)
        read_size = int(section.get("read_size", ReadSizeDefaults.DEFAULT) or 0)
        choice, cipher = self._cipher(algorithm or settings.get("advanced", {}).get("encryption_mode", ""))

        algo_label = _ALGO_NAMES.get(choice, choice) if self._mode == MODE_ENCRYPT else "auto-detect"
        start_msg = (f"[{self._mode.upper()}] {_plural(len(paths), 'file')} | {algo_label} | "
                     f"{_plural(threads, 'thread')}")
        write_log(start_msg, "general")

        self._file_model.reset_for_run(paths)
        self._worker = EncryptDecryptWorker(
            paths=paths, keys=keys, mode=self._mode, encrypt_name=encrypt_names,
            threads=threads, read_size=read_size, algorithm=cipher,
        )
        self._connect_worker(self._worker)
        self._cancel_requested = False
        self._progress = 0.0
        self._files_done = 0
        self._files_total = len(paths)
        self._current_file = ""
        self._failure_reasons = set()
        self._files_stopped = 0
        self._summary = ""
        self.summaryChanged.emit()
        self._emit_run()
        self._set_busy(True)
        self._threadpool.start(self._worker)

    @Slot()
    def cancel(self) -> None:
        """Stop the run: the files in progress stop and stay unchanged, and no new files start."""
        if self._worker is not None and not self._cancel_requested:
            self._cancel_requested = True
            self._worker.cancel()
            self._emit_run()

    # ── Results and clipboard ───────────────────────────────────────────────

    @Slot(int)
    def showInFolder(self, row: int) -> None:
        """Open File Explorer with the row's file selected (the written file once done)."""
        path = self._file_model.locationAt(row)
        if not path:
            return
        try:
            if os.path.exists(path):
                _select_in_explorer(os.path.normpath(path))
            elif os.path.isdir(os.path.dirname(path)):
                os.startfile(os.path.dirname(path))  # type: ignore[attr-defined]
        except OSError as error:
            write_log(f"Could not open File Explorer for {path}: {error}", "critical")
            self.notice.emit("Couldn't open File Explorer for that file.")

    @Slot()
    def openLastFolder(self) -> None:
        """Open the folder of the last file written."""
        if not self._last_folder:
            return
        try:
            os.startfile(self._last_folder)  # type: ignore[attr-defined]
        except OSError as error:
            write_log(f"Could not open {self._last_folder}: {error}", "critical")
            self.notice.emit("Couldn't open that folder.")

    @Slot()
    def copySelectedNames(self) -> None:
        """Copy selected file names to the system clipboard."""
        text = self._file_model.getSelectedNamesText()
        if text:
            QApplication.clipboard().setText(text)

    @Slot()
    def copySelectedPaths(self) -> None:
        """Copy selected file full paths to the system clipboard."""
        text = self._file_model.getSelectedPathsText()
        if text:
            QApplication.clipboard().setText(text)

    # ── Scanning ────────────────────────────────────────────────────────────

    def _scan_paths(self, paths: list[str]) -> None:
        """Check files and walk folders in the background; they join the scan already running."""
        if not paths or (self._scan is not None and self._scan.add_roots(paths)):
            return
        if not self.scanning:  # a new scanning session: its counts and notices start over
            self._scan_report = ScanReport()
            self._scan_found = 0
            self._scan_added = 0
        scan = FolderScanWorker(paths, file_ops.ENCRYPTED_EXTS, include_encrypted=self._mode == MODE_DECRYPT)
        queued = Qt.ConnectionType.QueuedConnection
        scan.signals.batch_found.connect(self._on_scan_batch, queued)
        scan.signals.finished.connect(self._on_scan_finished, queued)
        self._scans[scan.scan_id] = scan
        self._scan = scan
        self.scanChanged.emit()
        self._scan_pool.start(scan)

    def _on_scan_batch(self, scan_id: int, batch: list) -> None:
        """Add a scan's rows, unless the scan was cancelled (Stop or Clear) since it sent them."""
        scan = self._scans.get(scan_id)
        if scan is None or scan.cancelled:
            return
        self._scan_found += len(batch)
        self._scan_added += self._file_model.add_scanned(batch)
        self.scanChanged.emit()

    def _on_scan_finished(self, scan_id: int, report: ScanReport) -> None:
        """Release a finished scan; when the session's last one ends, say what was left out."""
        scan = self._scans.pop(scan_id, None)
        if scan is None:
            return
        if self._scan is scan:
            self._scan = None
        if scan.cancelled:
            return  # cancelScan already ended the session
        self._scan_report.add(report)
        if self.scanning:
            return
        self.scanChanged.emit()
        message = self._scan_notice(self._scan_report)
        if message:
            self.notice.emit(message)

    def _scan_notice(self, report: ScanReport) -> str:
        """One notice for what a scanning session left out or couldn't read ("" when nothing was)."""
        parts = []
        if report.folders and self._scan_found == 0:
            where = "that folder" if report.folders == 1 else "those folders"
            parts.append(f"No files to encrypt in {where}." if self._mode == MODE_ENCRYPT
                         else f"No gfgLock-encrypted files in {where}.")
        if report.failed_roots:
            parts.append("Couldn't open that folder." if report.failed_roots == 1 and not report.folders
                         else f"Couldn't open {_plural(report.failed_roots, 'folder')}.")
        if report.unreadable:
            parts.append(f"{_plural(report.unreadable, 'folder')} inside couldn't be opened and "
                         f"{_were(report.unreadable)} skipped.")
        if report.protected_folders or report.protected_files:
            parts.append(self._protected_text(report.protected_folders, report.protected_files))
        if report.other_type:
            parts.append(self._left_out_text(report.other_type))
        if report.error:
            parts.append(f"The scan stopped early: {report.error}")
        if self._busy and self._scan_added:
            parts.append(self._added_while_busy_text(self._scan_added))
        return " ".join(parts)

    @staticmethod
    def _protected_text(folders: int, files: int) -> str:
        """Say that system and app locations were left out, which only Encrypt does."""
        parts = []
        if folders:
            parts.append(_plural(folders, "system or app folder"))
        if files:
            parts.append(_plural(files, "system or app file"))
        return f"{' and '.join(parts)} {_were(folders + files)} left out."

    def _left_out_text(self, count: int) -> str:
        """Why files added directly aren't in the list: they belong on the other tab."""
        if self._mode == MODE_ENCRYPT:
            return (f"{_plural(count, 'file')} already encrypted {_were(count)} left out. "
                    f"Use the Decrypt tab to open {'it' if count == 1 else 'them'}.")
        return f"{_plural(count, 'file')} not encrypted by gfgLock {_were(count)} left out."

    def _added_while_busy_text(self, count: int) -> str:
        """Files added during a run wait for the next one; say so, since the run won't pick them up."""
        verb = "Encrypt" if self._mode == MODE_ENCRYPT else "Decrypt"
        return (f"{_plural(count, 'file')} added. {'It' if count == 1 else 'They'} will run "
                f"when you press {verb} again after this run.")

    # ── Run updates ─────────────────────────────────────────────────────────

    def _connect_worker(self, worker: EncryptDecryptWorker) -> None:
        """Wire worker signals to the controller (queued across threads)."""
        queued = Qt.ConnectionType.QueuedConnection
        signals = worker.signals
        signals.progress.connect(self._on_progress, queued)
        signals.file_started.connect(self._on_file_started, queued)
        signals.file_progress.connect(self._file_model.set_progress, queued)
        signals.file_result.connect(self._on_file_result, queued)
        signals.temps_removed.connect(self._on_temps_removed, queued)
        signals.error.connect(self.notice, queued)
        signals.finished.connect(self._on_finished, queued)

    def _on_progress(self, done: float, total: float) -> None:
        self._progress = min(_RUNNING_PROGRESS_CAP, done / total) if total > 0 else 0.0
        self._schedule_run()

    def _on_file_started(self, path: str) -> None:
        self._current_file = os.path.basename(path)
        self._file_model.set_status(path, STATUS_WORKING, progress=0.0)
        self._schedule_run()

    def _on_file_result(self, path: str, outcome: str, reason: str, output: str) -> None:
        """Show one file's result on its row (the worker has logged it) and count it as done.

        A file that Stop ended is unchanged, so it waits for the next run instead of counting as finished.
        """
        status = _OUTCOME_STATUS.get(outcome, STATUS_FAILED)
        if outcome == OUTCOME_SKIPPED and reason == file_ops.STOPPED_REASON:
            status = STATUS_WAITING
            self._files_stopped += 1
        if output:
            shown = f"Saved as {os.path.basename(output)}" + (f". {reason}" if reason else "")
            self._last_folder = os.path.dirname(output)
        else:
            shown = reason
        self._file_model.set_status(path, status, progress=1.0, message=shown, output=output)
        if status == STATUS_FAILED:
            self._failure_reasons.add(reason)
        self._files_done += 1
        self._schedule_run()

    def _on_temps_removed(self, count: int) -> None:
        self.notice.emit(f"Removed {_plural(count, 'temporary file')} left by an earlier run that didn't finish.")

    def _on_finished(self, elapsed: float, total: int, succeeded: int, failed: int, skipped: int) -> None:
        """Summarize the run, log it, and notify if enabled."""
        self._worker = None
        skipped -= self._files_stopped  # those wait for the next run
        # A Stop pressed after the last file ended changed nothing: the run counts as complete.
        stopped = self._cancel_requested and succeeded + failed + skipped < total
        self._cancel_requested = False
        if not stopped:
            self._progress = 1.0
        self._summary = self._build_summary(elapsed, total, succeeded, failed, skipped, stopped)
        write_log(f"[{self._mode.upper()}] {self._summary}", "critical" if failed else "general")
        write_session_separator()
        self._file_model.flush_counts()
        self._set_busy(False)
        self.summaryChanged.emit()
        self._emit_run()
        self._notify_complete(elapsed, failed, stopped)
        self.operationFinished.emit(elapsed, total, succeeded, failed, skipped)

    def _build_summary(self, elapsed: float, total: int, succeeded: int, failed: int,
                       skipped: int, cancelled: bool) -> str:
        """One line saying how the run went, e.g. '3 of 4 files encrypted in 2.1 s, 1 failed.'

        When every failure has the same reason (a wrong password, say), it follows the failure count.
        """
        verb = "encrypted" if self._mode == MODE_ENCRYPT else "decrypted"
        if cancelled:
            head = f"Stopped: {succeeded} of {_plural(total, 'file')} {verb}"
        elif succeeded == total:
            files = f"All {_plural(total, 'file')}" if total > 1 else _plural(total, "file")
            head = f"{files} {verb} in {_duration(elapsed)}"
        else:
            head = f"{succeeded} of {_plural(total, 'file')} {verb} in {_duration(elapsed)}"
        extras = [f"{skipped} skipped"] if skipped else []
        if failed:
            reason = next(iter(self._failure_reasons)) if len(self._failure_reasons) == 1 else ""
            extras.append(f"{failed} failed" + (f": {_lower_first(reason)}" if reason else ""))
        tail = " The rest were not changed." if cancelled and succeeded + failed + skipped < total else ""
        return head + "".join(f", {extra}" for extra in extras) + "." + tail

    def _notify_complete(self, elapsed: float, failed: int, stopped: bool) -> None:
        """Send a desktop notification when the preference is on and the user may have looked away:
        the window isn't in front, or the run took long enough to switch to something else."""
        settings = load_settings()
        if not settings.get("advanced", {}).get(
            "operation_notifications", NotificationDefaults.OPERATION_NOTIFICATIONS
        ):
            return
        in_front = QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        if in_front and elapsed <= _NOTIFY_AFTER_S:
            return
        verb = "Encryption" if self._mode == MODE_ENCRYPT else "Decryption"
        if stopped:
            title = f"{verb} stopped"
        elif failed:
            title = f"{verb} finished with errors"
        else:
            title = f"{verb} complete"
        notify(title, self._summary)

    def _schedule_run(self) -> None:
        """Send runChanged at most every _REFRESH_MS: now when the last one is that old, else at the
        interval (checked here too, since a flood of queued results can hold timers back)."""
        if time.monotonic() - self._run_sent >= _REFRESH_MS / 1000:
            self._emit_run()
        elif not self._run_timer.isActive():
            self._run_timer.start()

    def _emit_run(self) -> None:
        """Send runChanged now, dropping a scheduled one."""
        self._run_timer.stop()
        self._run_sent = time.monotonic()
        self.runChanged.emit()

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _cipher(choice: str) -> tuple[str, str]:
        """The settings code and engine cipher to encrypt with. Anything else, including the
        decrypt-only CFB, means the default algorithm."""
        cipher = AlgorithmDefaults.CIPHERS.get(choice, "")
        if cipher not in file_ops.ENCRYPT_ALGORITHMS:
            choice = AlgorithmDefaults.DEFAULT_ALGORITHM
            cipher = AlgorithmDefaults.CIPHERS[choice]
        return choice, cipher

    @staticmethod
    def _clamp_threads(threads: int, settings: dict) -> int:
        """Limit threads to the CPU, keeping one free when the preference asks for it."""
        clamp = settings.get("advanced", {}).get("clamp_cpu_threads", PerformanceDefaults.CLAMP_CPU_THREADS)
        return max(1, min(threads, thread_limit(clamp)))

    def _clear_summary(self) -> None:
        if self._summary and not self._busy:
            self._summary = ""
            self.summaryChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    @staticmethod
    def _url_to_path(url: str) -> str:
        """Convert a file:/// URL or plain path to a local filesystem path."""
        local = QUrl(url).toLocalFile()
        return os.path.normpath(local) if local else url
