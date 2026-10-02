# encrypt_ctrl.py - file management and encrypt/decrypt operation controller

import os

from PySide6.QtCore import Property, QObject, QThreadPool, QUrl, Signal, Slot
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gfglock.config.defaults import NotificationDefaults, PerformanceDefaults

from gfglock.core.file_ops import ENCRYPTED_EXTS
from gfglock.models.file_model import FileListModel
from gfglock.services.notifier import send_notification
from gfglock.services.folder_scanner import FolderScanWorker
from gfglock.services.worker import EncryptDecryptWorker
from gfglock.utils.logging import write_log, write_session_separator
from gfglock.utils.settings import load_settings

_ALGO_NAMES = {
    "aes256_gcm":        "AES-256 GCM",
    "aes256_cfb":        "AES-256 CFB",
    "chacha20_poly1305": "ChaCha20-Poly1305",
}


class EncryptController(QObject):
    """Manages the file list and drives encrypt/decrypt operations."""

    # Progress and status signals (forwarded from worker)
    progressChanged = Signal(float, float)              # (processed_bytes, total_bytes)
    filesProgressChanged = Signal(int, int)            # (done_files, total_files)
    currentFileChanged = Signal(str)                   # current file path
    statusChanged = Signal(str)                        # status/log message
    errorOccurred = Signal(str)                        # error message
    operationFinished = Signal(float, int, int, int, int)  # elapsed, total, ok, fail, skip
    operationStarted = Signal()
    busyChanged = Signal(bool)
    scanChanged = Signal()                             # folder scan started/progressed/ended

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_model = FileListModel(self)
        self._threadpool = QThreadPool.globalInstance()
        self._worker: EncryptDecryptWorker | None = None
        self._scan: FolderScanWorker | None = None
        self._scan_found = 0
        self._busy = False
        self._operation_mode = "encrypt"

    # ── Properties ──────────────────────────────────────────────────────────

    @Property(QObject, constant=True)
    def fileModel(self) -> FileListModel:
        """The file list model exposed to QML."""
        return self._file_model

    @Property(bool, notify=busyChanged)
    def isBusy(self) -> bool:
        """True while an encrypt/decrypt operation is in progress."""
        return self._busy

    @Property(bool, notify=scanChanged)
    def scanning(self) -> bool:
        """True while a folder scan is adding files in the background."""
        return self._scan is not None

    @Property(int, notify=scanChanged)
    def scanFound(self) -> int:
        """Files found so far by the running folder scan."""
        return self._scan_found

    @Slot(str)
    def setMode(self, mode: str) -> None:
        """Set the operation mode ('encrypt' or 'decrypt') to gate file additions.

        A scan started for the other mode is stopped, since it filters for the wrong files.
        """
        if mode != self._operation_mode:
            self.cancelScan()
        self._operation_mode = mode

    # ── File management slots ─────────────────────────────────────────────

    @Slot(list)
    def addFiles(self, urls: list) -> None:
        """Accept file:/// URLs or plain paths; folders among them are scanned in the background."""
        try:
            paths = [self._url_to_path(u) for u in urls if u]
            folders = [p for p in paths if p and os.path.isdir(p)]
            self._file_model.addFiles([p for p in paths if p and p not in folders and self._isAllowed(p)])
            if folders:
                self._start_scan(folders)
        except Exception:
            pass

    @Slot(str)
    def addFolder(self, url: str) -> None:
        """Scan a folder and its subfolders in the background, adding results in batches."""
        try:
            folder = self._url_to_path(url)
            if folder and os.path.isdir(folder):
                self._start_scan([folder])
        except Exception:
            pass

    @Slot()
    def cancelScan(self) -> None:
        """Stop the running folder scan; files already found stay in the list."""
        if self._scan is not None:
            self._scan.cancel()

    def shutdown(self) -> None:
        """Stop background work before exit so the thread pool drains quickly."""
        self.cancelScan()
        self.cancelOperation()

    def _start_scan(self, folders: list[str]) -> None:
        """Scan folders on the thread pool, replacing any scan already running."""
        self.cancelScan()
        worker = FolderScanWorker(
            roots=folders,
            encrypted_extensions=ENCRYPTED_EXTS,
            include_encrypted=self._operation_mode == "decrypt",
        )
        queued = Qt.ConnectionType.QueuedConnection
        worker.signals.batch_found.connect(self._file_model.addScanned, queued)
        worker.signals.progress.connect(self._on_scan_progress, queued)
        worker.signals.error.connect(self.errorOccurred, queued)
        worker.signals.finished.connect(
            lambda _found, _cancelled, w=worker: self._on_scan_finished(w), queued
        )
        self._scan = worker
        self._scan_found = 0
        self.scanChanged.emit()
        self._threadpool.start(worker)

    def _on_scan_progress(self, found: int) -> None:
        """Track the running file count for the scanning indicator."""
        self._scan_found = found
        self.scanChanged.emit()

    def _on_scan_finished(self, worker: FolderScanWorker) -> None:
        """Clear the scan state once the current scan ends."""
        if self._scan is worker:
            self._scan = None
            self.scanChanged.emit()

    @Slot(str)
    def addPath(self, path: str) -> None:
        """Add a single plain path (used by CLI pre-population)."""
        try:
            if self._isAllowed(path):
                self._file_model.addFile(path)
        except Exception:
            pass

    @Slot()
    def removeSelected(self) -> None:
        """Remove currently selected files from the model."""
        try:
            self._file_model.removeSelected()
        except Exception:
            pass

    @Slot()
    def clearFiles(self) -> None:
        """Stop any folder scan and remove all files from the model."""
        try:
            self.cancelScan()
            self._file_model.clearAll()
        except Exception:
            pass

    # ── Operation slots ───────────────────────────────────────────────────

    @Slot(str, str, bool, int, "QVariant", str)
    def startOperation(
        self,
        password: str,
        mode: str,
        encrypt_name: bool,
        threads: int,
        chunk_size,
        enc_algo: str,
    ) -> None:
        """Launch the encrypt or decrypt worker on the thread pool."""
        try:
            if self._busy:
                return
            paths = self._file_model.getPaths()
            if not paths:
                return
            settings = load_settings()
            if not threads or threads < 1:
                threads = settings.get("encryption", {}).get("cpu_threads", 1)
            clamp = settings.get("advanced", {}).get(
                "clamp_cpu_threads", PerformanceDefaults.CLAMP_CPU_THREADS
            )
            cpu_total = os.cpu_count() or 1
            max_threads = max(1, cpu_total - 1) if clamp else cpu_total
            threads = min(threads, max_threads)
            if chunk_size is None:
                chunk_size = settings.get("encryption", {}).get("chunk_size", None)
            if not enc_algo:
                enc_algo = settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")

            algo_label = _ALGO_NAMES.get(enc_algo, enc_algo) if mode == "encrypt" else "auto-detect"
            start_msg = (
                f"[{mode.upper()}] {len(paths)} file(s) {self._file_model.totalSize}"
                f" | {algo_label} | {threads} thread(s)"
            )
            write_log(start_msg, "general")
            write_log(start_msg, "critical")

            self._worker = EncryptDecryptWorker(
                paths=paths,
                password=password,
                mode=mode,
                encrypt_name=encrypt_name,
                threads=threads,
                chunk_size=chunk_size,
                enc_algo=enc_algo,
            )
            self._connect_worker()
            self._set_busy(True)
            self.operationStarted.emit()
            self._threadpool.start(self._worker)
        except Exception as e:
            self.errorOccurred.emit(str(e))

    @Slot()
    def cancelOperation(self) -> None:
        """Request cancellation of the running operation."""
        try:
            if self._worker is not None:
                self._worker.cancel()
        except Exception:
            pass

    @Slot()
    def copySelectedNames(self) -> None:
        """Copy selected file names to the system clipboard."""
        try:
            text = self._file_model.getSelectedNamesText()
            if text:
                QApplication.clipboard().setText(text)
        except Exception:
            pass

    @Slot()
    def copySelectedPaths(self) -> None:
        """Copy selected file full paths to the system clipboard."""
        try:
            text = self._file_model.getSelectedPathsText()
            if text:
                QApplication.clipboard().setText(text)
        except Exception:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────

    def _isAllowed(self, path: str) -> bool:
        """Return True if the file is valid for the current operation mode."""
        try:
            is_enc = os.path.splitext(path)[1].lower() in ENCRYPTED_EXTS
            if self._operation_mode == "encrypt":
                return not is_enc
            if self._operation_mode == "decrypt":
                return is_enc
            return True
        except Exception:
            return True

    def _connect_worker(self) -> None:
        """Wire worker signals to controller signals (queued across threads)."""
        if self._worker is None:
            return
        conn = Qt.ConnectionType.QueuedConnection
        sigs = self._worker.signals
        sigs.progress.connect(self.progressChanged, conn)
        sigs.files_progress.connect(self.filesProgressChanged, conn)
        sigs.file_changed.connect(self.currentFileChanged, conn)
        sigs.status.connect(self.statusChanged, conn)
        sigs.error.connect(self.errorOccurred, conn)
        sigs.file_result.connect(self._log_file_result, conn)
        sigs.finished.connect(self._on_finished, conn)

    def _log_file_result(self, success: bool, msg: str) -> None:
        """Log per-file result to general log; failures also go to critical."""
        write_log(msg, "general")
        if not success:
            write_log(msg, "critical")


    def _on_finished(self, elapsed, total, succeeded, failed, skipped) -> None:
        """Handle worker completion, write a summary log entry, and notify if enabled."""
        try:
            self._set_busy(False)
            self._worker = None
            mode = self._operation_mode.upper()
            summary = (
                f"[{mode}] Done in {elapsed:.1f}s - "
                f"{succeeded} ok · {failed} failed · {skipped} skipped"
            )
            write_log(summary, "general")
            if failed > 0:
                write_log(summary, "critical")
            write_session_separator()
            self._notify_complete(elapsed, succeeded, failed, skipped)
            self.operationFinished.emit(elapsed, total, succeeded, failed, skipped)
        except Exception:
            pass

    def _notify_complete(self, elapsed: float, succeeded: int, failed: int, skipped: int) -> None:
        """Send a desktop toast notification if the setting is enabled."""
        try:
            settings = load_settings()
            if not settings.get("advanced", {}).get(
                "operation_notifications", NotificationDefaults.OPERATION_NOTIFICATIONS
            ):
                return
            is_enc = self._operation_mode == "encrypt"
            verb = "Encryption" if is_enc else "Decryption"
            action = "encrypted" if is_enc else "decrypted"
            if failed == 0:
                body = f"{succeeded} file(s) {action} in {elapsed:.1f}s."
            else:
                body = f"{succeeded} ok · {failed} failed · {skipped} skipped in {elapsed:.1f}s."
            send_notification(f"gfgLock - {verb} Complete", body)
        except Exception:
            pass

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    @staticmethod
    def _url_to_path(url: str) -> str:
        """Convert a file:/// URL or plain path to a local filesystem path."""
        try:
            q = QUrl(url)
            local = q.toLocalFile()
            return local if local else url
        except Exception:
            return url
