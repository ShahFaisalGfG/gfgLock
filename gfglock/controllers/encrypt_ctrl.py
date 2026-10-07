# encrypt_ctrl.py - one tab's file queue and the encrypt or decrypt runs over it

import os
import subprocess

from PySide6.QtCore import Property, QObject, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import (
    AlgorithmDefaults,
    DecryptionDefaults,
    EncryptionDefaults,
    NotificationDefaults,
    PerformanceDefaults,
    ReadSizeDefaults,
)
from gfglock.core.file_ops import ENCRYPTED_EXTS
from gfglock.models.file_model import STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED, STATUS_WORKING, FileListModel
from gfglock.services.folder_scanner import FolderScanWorker
from gfglock.services.notifier import send_notification
from gfglock.services.worker import OUTCOME_DONE, OUTCOME_SKIPPED, EncryptDecryptWorker
from gfglock.utils.logging import write_log, write_session_separator
from gfglock.utils.settings import load_settings

MODE_ENCRYPT = "encrypt"
MODE_DECRYPT = "decrypt"
# Settings section and defaults that hold each mode's thread count and read size.
_PERFORMANCE = {MODE_ENCRYPT: ("encryption", EncryptionDefaults), MODE_DECRYPT: ("decryption", DecryptionDefaults)}

_ALGO_NAMES = {code: label for label, code, _ in AlgorithmDefaults.OPTIONS}
_OUTCOME_STATUS = {OUTCOME_DONE: STATUS_DONE, OUTCOME_SKIPPED: STATUS_SKIPPED}


def _plural(count: int, noun: str) -> str:
    """'1 file', '3 files'."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


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
        self._worker: EncryptDecryptWorker | None = None
        self._scan: FolderScanWorker | None = None
        self._scan_found = 0
        self._busy = False
        self._cancel_requested = False
        self._progress = 0.0
        self._files_done = 0
        self._files_total = 0
        self._current_file = ""
        self._summary = ""
        self._last_folder = ""
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
        """True while a folder scan is adding files in the background."""
        return self._scan is not None

    @Property(int, notify=scanChanged)
    def scanFound(self) -> int:
        """Files found so far by the running folder scan."""
        return self._scan_found

    @Property(float, notify=runChanged)
    def progress(self) -> float:
        """Progress of the current run from 0 to 1, by bytes processed."""
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
        """True after Cancel until the files already in progress finish."""
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
        """Accept file:/// URLs or plain paths; folders among them are scanned in the background."""
        paths = [self._url_to_path(u) for u in urls if u]
        folders = [p for p in paths if p and os.path.isdir(p)]
        files = [p for p in paths if p and p not in folders]
        allowed = [p for p in files if self._isAllowed(p)]
        added = self._file_model.addFiles(allowed)
        self._report_left_out(len(files) - len(allowed))
        self._report_added_while_busy(added)
        if folders:
            self._start_scan(folders)

    @Slot(str)
    def addFolder(self, url: str) -> None:
        """Scan a folder and its subfolders in the background, adding results in batches."""
        folder = self._url_to_path(url)
        if folder and os.path.isdir(folder):
            self._start_scan([folder])

    @Slot()
    def cancelScan(self) -> None:
        """Stop the running folder scan; files already found stay in the list."""
        if self._scan is not None:
            self._scan.cancel()

    @Slot()
    def clearFiles(self) -> None:
        """Stop any folder scan and remove all files from the list."""
        self.cancelScan()
        self._file_model.clearAll()
        if self._last_folder:  # "Open folder" belongs to the files just cleared
            self._last_folder = ""
            self.summaryChanged.emit()

    @Slot()
    def removeSelected(self) -> None:
        """Take the selected files off the list (nothing is deleted from disk)."""
        self._file_model.removeSelected()

    def shutdown(self) -> None:
        """Stop background work before exit so the thread pool drains quickly."""
        self.cancelScan()
        self.cancel()

    # ── Running ─────────────────────────────────────────────────────────────

    @Slot(str, bool, str)
    def start(self, password: str, encrypt_names: bool = False, algorithm: str = "") -> None:
        """Encrypt or decrypt every file that isn't finished yet with `password`."""
        if self._busy or not password:
            return
        paths = self._file_model.runnable_paths()
        if not paths:
            return
        settings = load_settings()
        section_name, defaults = _PERFORMANCE[self._mode]
        section = settings.get(section_name, {})
        threads = self._clamp_threads(int(section.get("cpu_threads", defaults.DEFAULT_THREADS)), settings)
        read_size = int(section.get("read_size", ReadSizeDefaults.DEFAULT) or 0)
        algorithm = algorithm or settings.get("advanced", {}).get("encryption_mode", AlgorithmDefaults.DEFAULT_ALGORITHM)

        algo_label = _ALGO_NAMES.get(algorithm, algorithm) if self._mode == MODE_ENCRYPT else "auto-detect"
        start_msg = (f"[{self._mode.upper()}] {_plural(len(paths), 'file')} | {algo_label} | "
                     f"{_plural(threads, 'thread')}")
        write_log(start_msg, "general")

        self._file_model.reset_for_run(paths)
        self._worker = EncryptDecryptWorker(
            paths=paths, password=password, mode=self._mode, encrypt_name=encrypt_names,
            threads=threads, read_size=read_size, enc_algo=algorithm,
        )
        self._connect_worker(self._worker)
        self._cancel_requested = False
        self._progress = 0.0
        self._files_done = 0
        self._files_total = len(paths)
        self._current_file = ""
        self._summary = ""
        self.summaryChanged.emit()
        self.runChanged.emit()
        self._set_busy(True)
        self._threadpool.start(self._worker)

    @Slot()
    def cancel(self) -> None:
        """Stop after the files in progress; files not started yet stay unchanged."""
        if self._worker is not None and not self._cancel_requested:
            self._cancel_requested = True
            self._worker.cancel()
            self.runChanged.emit()

    # ── Results and clipboard ───────────────────────────────────────────────

    @Slot(int)
    def showInFolder(self, row: int) -> None:
        """Open File Explorer with the row's file selected (the written file once done)."""
        path = self._file_model.locationAt(row)
        if not path:
            return
        try:
            if os.path.exists(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
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

    # ── Internal helpers ────────────────────────────────────────────────────

    def _isAllowed(self, path: str) -> bool:
        """True when the file belongs on this tab: plain files to encrypt, gfgLock files to decrypt."""
        is_encrypted = os.path.splitext(path)[1].lower() in ENCRYPTED_EXTS
        return is_encrypted if self._mode == MODE_DECRYPT else not is_encrypted

    def _report_added_while_busy(self, count: int) -> None:
        """Files added during a run wait for the next one; say so, since the run won't pick them up."""
        if count > 0 and self._busy:
            verb = "Encrypt" if self._mode == MODE_ENCRYPT else "Decrypt"
            self.notice.emit(f"{_plural(count, 'file')} added. {'It' if count == 1 else 'They'} will run "
                             f"when you press {verb} again after this run.")

    def _report_left_out(self, count: int) -> None:
        """Tell the user why some of the files they added aren't in the list."""
        if count <= 0:
            return
        if self._mode == MODE_ENCRYPT:
            self.notice.emit(f"{_plural(count, 'file')} already encrypted {'was' if count == 1 else 'were'} "
                             "left out. Use the Decrypt tab to open them.")
        else:
            self.notice.emit(f"{_plural(count, 'file')} not encrypted by gfgLock "
                             f"{'was' if count == 1 else 'were'} left out.")

    @staticmethod
    def _clamp_threads(threads: int, settings: dict) -> int:
        """Limit threads to the CPU, keeping one free when the preference asks for it."""
        clamp = settings.get("advanced", {}).get("clamp_cpu_threads", PerformanceDefaults.CLAMP_CPU_THREADS)
        cpu_total = os.cpu_count() or 1
        return max(1, min(threads, max(1, cpu_total - 1) if clamp else cpu_total))

    def _start_scan(self, folders: list[str]) -> None:
        """Scan folders on the thread pool, replacing any scan already running."""
        self.cancelScan()
        worker = FolderScanWorker(
            roots=folders,
            encrypted_extensions=ENCRYPTED_EXTS,
            include_encrypted=self._mode == MODE_DECRYPT,
        )
        queued = Qt.ConnectionType.QueuedConnection
        worker.signals.batch_found.connect(self._file_model.addScanned, queued)
        worker.signals.progress.connect(self._on_scan_progress, queued)
        worker.signals.error.connect(self.notice, queued)
        worker.signals.finished.connect(
            lambda found, cancelled, w=worker: self._on_scan_finished(w, found, cancelled), queued
        )
        self._scan = worker
        self._scan_found = 0
        self.scanChanged.emit()
        self._threadpool.start(worker)

    def _on_scan_progress(self, found: int) -> None:
        """Track the running file count for the scanning indicator."""
        self._scan_found = found
        self.scanChanged.emit()

    def _on_scan_finished(self, worker: FolderScanWorker, found: int, cancelled: bool) -> None:
        """Clear the scan state and say what the scan found."""
        if self._scan is not worker:
            return
        self._scan = None
        self.scanChanged.emit()
        if not cancelled and found == 0:
            self.notice.emit("No files to encrypt in that folder." if self._mode == MODE_ENCRYPT
                             else "No gfgLock-encrypted files in that folder.")
        else:
            self._report_added_while_busy(found)

    def _connect_worker(self, worker: EncryptDecryptWorker) -> None:
        """Wire worker signals to the controller (queued across threads)."""
        queued = Qt.ConnectionType.QueuedConnection
        signals = worker.signals
        signals.progress.connect(self._on_progress, queued)
        signals.files_progress.connect(self._on_files_progress, queued)
        signals.file_started.connect(self._on_file_started, queued)
        signals.file_progress.connect(self._file_model.set_progress, queued)
        signals.file_result.connect(self._on_file_result, queued)
        signals.error.connect(self.notice, queued)
        signals.finished.connect(self._on_finished, queued)

    def _on_progress(self, done: float, total: float) -> None:
        self._progress = min(1.0, done / total) if total > 0 else 0.0
        self.runChanged.emit()

    def _on_files_progress(self, done: int, total: int) -> None:
        self._files_done = done
        self._files_total = total
        self.runChanged.emit()

    def _on_file_started(self, path: str) -> None:
        self._current_file = os.path.basename(path)
        self._file_model.set_status(path, STATUS_WORKING, progress=0.0)
        self.runChanged.emit()

    def _on_file_result(self, path: str, outcome: str, reason: str, output: str, message: str) -> None:
        """Show one file's result on its row and write it to the log."""
        status = _OUTCOME_STATUS.get(outcome, STATUS_FAILED)
        shown = f"Saved as {os.path.basename(output)}" if output else reason
        self._file_model.set_status(path, status, progress=1.0, message=shown, output=output)
        if output:
            self._last_folder = os.path.dirname(output)
        write_log(message, "general")
        if status == STATUS_FAILED:
            write_log(message, "critical")

    def _on_finished(self, elapsed: float, total: int, succeeded: int, failed: int, skipped: int) -> None:
        """Summarize the run, log it, and notify if enabled."""
        self._worker = None
        cancelled = self._cancel_requested
        self._cancel_requested = False
        self._summary = self._build_summary(elapsed, total, succeeded, failed, skipped, cancelled)
        summary = f"[{self._mode.upper()}] {self._summary}"
        write_log(summary, "critical" if failed else "general")
        write_session_separator()
        self._set_busy(False)
        self.summaryChanged.emit()
        self.runChanged.emit()
        self._notify_complete(succeeded, failed)
        self.operationFinished.emit(elapsed, total, succeeded, failed, skipped)

    def _build_summary(self, elapsed: float, total: int, succeeded: int, failed: int,
                       skipped: int, cancelled: bool) -> str:
        """One line saying how the run went, e.g. '3 of 4 files encrypted in 2.1 s, 1 failed.'"""
        verb = "encrypted" if self._mode == MODE_ENCRYPT else "decrypted"
        done = succeeded + failed + skipped
        if cancelled and done < total:
            return (f"Stopped after {_plural(done, 'file')}: {succeeded} {verb}. "
                    "The rest were not changed.")
        head = (f"All {_plural(succeeded, 'file')} {verb}" if succeeded == total
                else f"{succeeded} of {_plural(total, 'file')} {verb}")
        extras = []
        if failed:
            extras.append(f"{failed} failed")
        if skipped:
            extras.append(f"{skipped} skipped")
        return f"{head} in {elapsed:.1f} s" + (f", {', '.join(extras)}." if extras else ".")

    def _notify_complete(self, succeeded: int, failed: int) -> None:
        """Send a desktop notification if the preference is on."""
        settings = load_settings()
        if not settings.get("advanced", {}).get(
            "operation_notifications", NotificationDefaults.OPERATION_NOTIFICATIONS
        ):
            return
        verb = "Encryption" if self._mode == MODE_ENCRYPT else "Decryption"
        title = f"gfgLock - {verb} complete" if failed == 0 else f"gfgLock - {verb} finished with errors"
        send_notification(title, self._summary)

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
