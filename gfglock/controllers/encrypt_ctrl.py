# encrypt_ctrl.py - one tab's file queue and the encrypt, decrypt, or check runs over it

import ctypes
import os
import time
from ctypes import wintypes

from PySide6.QtCore import Property, QObject, Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import AlgorithmDefaults, NotificationDefaults
from gfglock.core import file_ops, passwords, reasons
from gfglock.core.batch import (
    MODE_DECRYPT,
    MODE_ENCRYPT,
    MODE_VERIFY,
    RunOptions,
    RunResult,
    format_time_left,
    options_from_settings,
    plural,
    run_folders,
    space_shortages,
    summarize,
    wrong_password_only,
)
from gfglock.core.file_ops import OUTCOME_DONE, OUTCOME_SKIPPED
from gfglock.core.format_v2 import KeyRing
from gfglock.models.file_model import (
    STATUS_CHECKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_WAITING,
    STATUS_WORKING,
    FileListModel,
)
from gfglock.services.folder_scanner import FolderScanWorker, ScanReport
from gfglock.services.notifier import notify
from gfglock.services.worker import EncryptDecryptWorker
from gfglock.utils.logging import write_log, write_session_separator
from gfglock.utils.settings import load_settings

_ALGO_NAMES = {option[1]: option[0] for option in AlgorithmDefaults.OPTIONS}
_CIPHER_CODES = {cipher: code for code, cipher in AlgorithmDefaults.CIPHERS.items()}
_OUTCOME_STATUS = {OUTCOME_DONE: STATUS_DONE, OUTCOME_SKIPPED: STATUS_SKIPPED}
# The Start button of each run, as the summary's next step names it.
_BUTTONS = {MODE_ENCRYPT: "Encrypt", MODE_DECRYPT: "Decrypt", MODE_VERIFY: "Check"}
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


def _were(count: int) -> str:
    """'was' for one, 'were' for any other count."""
    return "was" if count == 1 else "were"


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
    """Owns one tab's file list and runs encryption (or decryption, or a check) over it."""

    busyChanged = Signal(bool)
    scanChanged = Signal()                 # folder scan started/progressed/ended
    runChanged = Signal()                  # progress, file counts, or current file changed
    summaryChanged = Signal()
    notice = Signal(str)                   # a short message for the user (shown as a toast)
    operationFinished = Signal(float, int, int, int, int)  # elapsed, total, ok, failed, skipped

    def __init__(self, mode: str = MODE_ENCRYPT, parent=None):
        super().__init__(parent)
        self._mode = MODE_DECRYPT if mode == MODE_DECRYPT else MODE_ENCRYPT
        self._run_mode = self._mode  # a Check run on the Decrypt tab is MODE_VERIFY
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
        self._eta = -1.0
        self._files_done = 0
        self._files_total = 0
        self._current_file = ""
        self._summary = ""
        self._summary_error = False
        self._outputs: list[str] = []
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
        """True while files are being encrypted, decrypted, or checked."""
        return self._busy

    @Property(bool, notify=busyChanged)
    def checking(self) -> bool:
        """True while the run is a Check: nothing is written."""
        return self._busy and self._run_mode == MODE_VERIFY

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

    @Property(str, notify=runChanged)
    def timeLeft(self) -> str:
        """'about 3 min left' during a long run, "" while it is too early to tell."""
        return format_time_left(self._eta) if self._busy and not self._cancel_requested else ""

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
        """How the last run went, or why it couldn't start ("" before the first)."""
        return self._summary

    @Property(bool, notify=summaryChanged)
    def summaryIsError(self) -> bool:
        """True when the summary reports failures, or a run that couldn't start or stopped itself."""
        return self._summary_error

    @Property(list, notify=summaryChanged)
    def lastFolders(self) -> list:
        """The folders the last run wrote into, for "Open folder"."""
        return run_folders(self._outputs)

    @Property(str, notify=summaryChanged)
    def lastFile(self) -> str:
        """The file the last run wrote when it wrote exactly one, for "Open file"."""
        return self._outputs[0] if len(self._outputs) == 1 else ""

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
        if self._outputs:  # "Open folder" belongs to the files just cleared
            self._outputs = []
            self.summaryChanged.emit()

    def shutdown(self) -> None:
        """Stop background work before exit: scans stop at once, files in progress stop unchanged."""
        self.cancelScan()
        self.cancel()
        self._scan_pool.waitForDone(_SCAN_STOP_WAIT_MS)

    # ── Running ─────────────────────────────────────────────────────────────

    @Slot(str, str, bool, result=str)
    def passwordBlocker(self, password: str, confirm: str, confirm_finished: bool) -> str:
        """What is still wrong with the typed password(s) before this tab can start, or ""."""
        return passwords.blocker(self._mode, password, confirm, confirm_finished)

    @Slot(str, str, bool, result=bool)
    def passwordMismatch(self, password: str, confirm: str, confirm_finished: bool) -> bool:
        """True when the confirmation box is complete enough to tell, and differs from the password."""
        return self._mode == MODE_ENCRYPT and passwords.mismatch(password, confirm, confirm_finished)

    @Slot(str, bool, str)
    def start(self, password: str, encrypt_names: bool = False, algorithm: str = "") -> None:
        """Encrypt or decrypt every file that isn't finished yet with `password`."""
        self._start_run(self._mode, password, encrypt_names, algorithm)

    @Slot(str)
    def check(self, password: str) -> None:
        """Check the password and the data of every file not finished yet, changing nothing."""
        if self._mode == MODE_DECRYPT:
            self._start_run(MODE_VERIFY, password)

    def _start_run(self, mode: str, password: str, encrypt_names: bool = False, algorithm: str = "") -> None:
        """Start a run of `mode` over the runnable files, unless something stops it before it begins."""
        if self._busy or not password:
            return
        items = self._file_model.runnable_items()
        if not items:
            return
        try:
            keys = KeyRing(password)
        except ValueError as error:  # a password that can't be turned into a key
            reason = str(error)
            self.notice.emit(f"{reason[:1].upper()}{reason[1:]}.")
            return
        options = options_from_settings(mode, load_settings(), algorithm=algorithm, hide_names=encrypt_names)
        problem = self._cannot_start(items, options)
        if problem:
            self._set_summary(problem, error=True)
            return

        if mode == MODE_ENCRYPT:
            label = _ALGO_NAMES.get(_CIPHER_CODES.get(options.algorithm, ""), options.algorithm)
        else:
            label = "auto-detect"
        write_log(f"[{mode.upper()}] {plural(len(items), 'file')} | {label} | {plural(options.threads, 'thread')}",
                  "general")

        paths = [path for path, _size in items]
        self._file_model.reset_for_run(paths)
        self._run_mode = mode
        self._worker = EncryptDecryptWorker(paths, keys, options)
        self._connect_worker(self._worker)
        self._cancel_requested = False
        self._progress = 0.0
        self._eta = -1.0
        self._files_done = 0
        self._files_total = len(paths)
        self._current_file = ""
        self._outputs = []
        self._set_summary("")
        self._emit_run()
        self._set_busy(True)
        self._threadpool.start(self._worker)

    def _cannot_start(self, items: list[tuple[str, int]], options: RunOptions) -> str:
        """Why a run can't start (the output folder can't be made, a drive is too full), or ""."""
        if options.output_dir:
            try:
                os.makedirs(options.output_dir, exist_ok=True)
            except OSError as error:
                write_log(f"Could not create {options.output_dir}: {error}", "critical")
                return (f"Couldn't use the folder {options.output_dir} to save into "
                        f"({reasons.label(reasons.categorize(error))}). Choose another one in Options.")
        return " ".join(shortage.text() for shortage in space_shortages(items, options))

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
        self._show_file(self._file_model.locationAt(row))

    @Slot(int)
    def openRow(self, row: int) -> None:
        """A finished row's default action: open the decrypted file, or show the encrypted one."""
        output = self._file_model.outputAt(row)
        if not output:
            return
        if self._mode == MODE_DECRYPT:
            self._open(output, "Couldn't open that file. It may have been moved or deleted.")
        else:
            self._show_file(output)

    @Slot()
    def openLastFile(self) -> None:
        """Open the one file the last run decrypted, or show the one it encrypted."""
        path = self._outputs[0] if len(self._outputs) == 1 else ""
        if path and self._mode == MODE_DECRYPT:
            self._open(path, "Couldn't open that file. It may have been moved or deleted.")
        elif path:
            self._show_file(path)

    @Slot(str)
    def openFolder(self, folder: str) -> None:
        """Open one of the folders the last run wrote into."""
        self._open(folder, "Couldn't open that folder. It may have been moved or deleted.")

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

    @Slot()
    def copyResults(self) -> None:
        """Copy every file with its status and result, one per line, to the clipboard."""
        text = self._file_model.resultsText()
        if text:
            QApplication.clipboard().setText(text)
            self.notice.emit(f"Copied the results of {plural(len(text.splitlines()), 'file')}.")

    def _show_file(self, path: str) -> None:
        """Select a file in File Explorer, or open its folder when the file is gone."""
        if not path:
            return
        try:
            if os.path.exists(path):
                _select_in_explorer(os.path.normpath(path))
            elif os.path.isdir(os.path.dirname(path)):
                os.startfile(os.path.dirname(path))  # type: ignore[attr-defined]
            else:
                self.notice.emit("That file and its folder were moved or deleted.")
        except OSError as error:
            write_log(f"Could not open File Explorer for {path}: {error}", "critical")
            self.notice.emit("Couldn't open File Explorer for that file.")

    def _open(self, path: str, failure: str) -> None:
        """Open a file or folder with its usual program, saying so when it can't be."""
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as error:
            write_log(f"Could not open {path}: {error}", "critical")
            self.notice.emit(failure)

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
                         else f"Couldn't open {plural(report.failed_roots, 'folder')}.")
        if report.unreadable:
            parts.append(f"{plural(report.unreadable, 'folder')} inside couldn't be opened and "
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
            parts.append(plural(folders, "system or app folder"))
        if files:
            parts.append(plural(files, "system or app file"))
        return f"{' and '.join(parts)} {_were(folders + files)} left out."

    def _left_out_text(self, count: int) -> str:
        """Why files added directly aren't in the list: they belong on the other tab."""
        if self._mode == MODE_ENCRYPT:
            return (f"{plural(count, 'file')} already encrypted {_were(count)} left out. "
                    f"Use the Decrypt tab to open {'it' if count == 1 else 'them'}.")
        return f"{plural(count, 'file')} not encrypted by gfgLock {_were(count)} left out."

    def _added_while_busy_text(self, count: int) -> str:
        """Files added during a run wait for the next one; say so, since the run won't pick them up."""
        verb = _BUTTONS[self._mode]
        return (f"{plural(count, 'file')} added. {'It' if count == 1 else 'They'} will run "
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
        signals.finished.connect(self._on_finished, queued)

    def _on_progress(self, done: float, total: float, eta: float) -> None:
        self._progress = min(_RUNNING_PROGRESS_CAP, done / total) if total > 0 else 0.0
        self._eta = eta
        self._schedule_run()

    def _on_file_started(self, path: str) -> None:
        self._current_file = os.path.basename(path)
        self._file_model.set_status(path, STATUS_WORKING, progress=0.0)
        self._schedule_run()

    def _on_file_result(self, path: str, outcome: str, category: str, reason: str, output: str) -> None:
        """Show one file's result on its row (the run has logged it) and count it as done.

        A file that Stop ended is unchanged, so it waits for the next run instead of counting as
        finished; a checked file can still be decrypted.
        """
        status = _OUTCOME_STATUS.get(outcome, STATUS_FAILED)
        if outcome == OUTCOME_SKIPPED and category == reasons.STOPPED:
            status = STATUS_WAITING
        elif outcome == OUTCOME_DONE and self._run_mode == MODE_VERIFY:
            status = STATUS_CHECKED
        if output:
            shown = f"Saved as {os.path.basename(output)}" + (f". {reason}" if reason else "")
            self._outputs.append(output)
        else:
            shown = reason
        self._file_model.set_status(path, status, progress=1.0, message=shown, output=output)
        self._files_done += 1
        self._schedule_run()

    def _on_temps_removed(self, count: int) -> None:
        self.notice.emit(f"Removed {plural(count, 'temporary file')} left by an earlier run that didn't finish.")

    def _on_finished(self, result: RunResult) -> None:
        """Summarize the run, log it, and notify if enabled."""
        self._worker = None
        self._cancel_requested = False
        if not result.cancelled:
            self._progress = 1.0
        summary = summarize(result, f"press {_BUTTONS[result.mode]}")
        if wrong_password_only(result):
            summary += f" Type it again and press {_BUTTONS[result.mode]}."
        self._set_summary(summary, error=bool(result.failed or result.halt or result.error), emit=False)
        write_log(f"[{result.mode.upper()}] {self._summary}", "critical" if result.failed else "general")
        write_session_separator()
        if result.failed and result.total >= 10:
            self._file_model.move_failed_first()  # in a big list, the files that need attention come first
        self._file_model.flush_counts()
        self._set_busy(False)
        self.summaryChanged.emit()
        self._emit_run()
        self._notify_complete(result)
        self.operationFinished.emit(result.elapsed, result.total, result.done, result.failed, result.skipped)

    def _notify_complete(self, result: RunResult) -> None:
        """Send a desktop notification when the preference is on and the user may have looked away:
        the window isn't in front, or the run took long enough to switch to something else."""
        settings = load_settings()
        if not settings.get("advanced", {}).get(
            "operation_notifications", NotificationDefaults.OPERATION_NOTIFICATIONS
        ):
            return
        in_front = QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        if in_front and result.elapsed <= _NOTIFY_AFTER_S:
            return
        verb = {MODE_ENCRYPT: "Encryption", MODE_DECRYPT: "Decryption", MODE_VERIFY: "Check"}[result.mode]
        if result.cancelled:
            title = f"{verb} stopped"
        elif result.failed:
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

    def _set_summary(self, text: str, error: bool = False, emit: bool = True) -> None:
        self._summary = text
        self._summary_error = error and bool(text)
        if emit:
            self.summaryChanged.emit()

    def _clear_summary(self) -> None:
        if self._summary and not self._busy:
            self._set_summary("")

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    @staticmethod
    def _url_to_path(url: str) -> str:
        """Convert a file:/// URL or plain path to a local filesystem path."""
        local = QUrl(url).toLocalFile()
        return os.path.normpath(local) if local else url
