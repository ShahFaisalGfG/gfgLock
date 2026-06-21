# worker.py - background encryption/decryption worker (PySide6)

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core import aes256_gcm_cfb as aes_core
from gfglock.core import chacha20_poly1305 as xchacha_core
from gfglock.utils import load_settings, predict_encrypted_size


class WorkerSignals(QObject):
    progress = Signal(float, float)
    # files_progress: (completed_files, total_files)
    files_progress = Signal(int, int)
    file_changed = Signal(str)
    status = Signal(str)
    error = Signal(str)
    # file_result: (success, message) - emitted once per file on completion
    file_result = Signal(bool, str)
    # finished: (elapsed_time, total_files, succeeded, failed, skipped)
    finished = Signal(float, int, int, int, int)


class EncryptDecryptWorker(QRunnable):
    def __init__(
        self,
        paths,
        password,
        mode: str = "encrypt",
        encrypt_name: bool = False,
        threads: int = 1,
        chunk_size=None,
        show_password: bool = False,
        enc_algo: str | None = None,
    ):
        super().__init__()
        self.paths = list(paths)
        self.password = password
        self.mode = mode
        self.encrypt_name = encrypt_name
        self.threads = int(threads)
        self.chunk_size = None if chunk_size is None else int(chunk_size)
        self._cancelled = False
        self.enc_algo = enc_algo
        self.total_bytes = float(self._calc_total_size())
        self.processed_bytes = 0.0
        self._files_completed = 0
        self.signals = WorkerSignals()

    def _calc_total_size(self) -> float:
        """Calculate total bytes to process for progress tracking."""
        total = 0.0
        self._per_file_sizes: dict = {}
        if self.mode == "encrypt":
            algo = self.enc_algo
            if not algo:
                try:
                    settings = load_settings()
                    algo = settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                except Exception:
                    algo = "aes256_gcm"
            size_mode = {"aes256_cfb": "CFB", "chacha20_poly1305": "CHACHA"}.get(algo, "GCM")
            for path in self.paths:
                if os.path.exists(path) and os.path.isfile(path):
                    try:
                        predicted = float(predict_encrypted_size(path, size_mode))
                        total += predicted
                        self._per_file_sizes[path] = predicted
                    except Exception:
                        try:
                            fs = float(os.path.getsize(path))
                        except Exception:
                            fs = 0.0
                        total += fs
                        self._per_file_sizes[path] = fs
        else:
            for path in self.paths:
                if os.path.exists(path) and os.path.isfile(path):
                    try:
                        fs = float(os.path.getsize(path))
                        total += fs
                        self._per_file_sizes[path] = fs
                    except Exception:
                        self._per_file_sizes[path] = 0.0
        return max(total, 1.0)

    def _make_progress_callback(self, file_index: int, total_files: int) -> Callable[[float], None]:
        """Create a per-file chunk progress callback."""
        def callback(chunk_bytes: float) -> None:
            self.processed_bytes = min(
                self.processed_bytes + float(chunk_bytes), self.total_bytes
            )
            self.signals.progress.emit(self.processed_bytes, self.total_bytes)
        return callback

    @Slot()
    def cancel(self) -> None:
        """Request cancellation of the running operation."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the encrypt/decrypt operation on the thread pool."""
        total = len(self.paths)
        done = 0
        start_time = time.time()
        succeeded = failed = skipped_already_encrypted = 0
        failed_files: list = []

        try:
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                future_to_path: dict = {}
                for file_index, p in enumerate(self.paths):
                    if self._cancelled:
                        break
                    progress_cb = self._make_progress_callback(file_index, len(self.paths))
                    job = self._build_job(p, progress_cb)
                    fut = executor.submit(job)
                    future_to_path[fut] = p

                for fut in as_completed(future_to_path):
                    if self._cancelled:
                        break
                    p = future_to_path.get(fut, "")
                    try:
                        result = fut.result()
                        success, msg = result if isinstance(result, tuple) else (bool(result), "")
                        if msg:
                            self.signals.status.emit(msg)
                        if success:
                            succeeded += 1
                            if msg:
                                self.signals.file_result.emit(True, msg)
                        else:
                            if self._is_skip(p, msg):
                                skipped_already_encrypted += 1
                                if msg:
                                    self.signals.file_result.emit(True, msg)
                            else:
                                failed += 1
                                failed_files.append(p)
                                if msg:
                                    self.signals.file_result.emit(False, msg)
                    except Exception as e:
                        failed += 1
                        failed_files.append(p)
                        err_msg = f"Critical error while processing {p}: {e}"
                        self.signals.error.emit(str(e))
                        self.signals.file_result.emit(False, err_msg)

                    done += 1
                    self._files_completed += 1
                    try:
                        self.signals.progress.emit(self.processed_bytes, self.total_bytes)
                        self.signals.files_progress.emit(self._files_completed, total)
                    except Exception:
                        pass
                    self.signals.file_changed.emit(p)

        except Exception as e:
            self.signals.error.emit(str(e))

        try:
            self.signals.progress.emit(self.total_bytes, self.total_bytes)
        except Exception:
            pass
        elapsed = time.time() - start_time
        self.signals.status.emit(f"Completed in {elapsed:.1f}s")
        self.signals.finished.emit(elapsed, total, succeeded, failed, skipped_already_encrypted)

    def _build_job(self, p: str, progress_cb: Callable) -> Callable:
        """Return the correct encrypt/decrypt callable for the file."""
        if self.mode == "encrypt":
            algo = self.enc_algo
            if not algo:
                try:
                    settings = load_settings()
                    algo = settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                except Exception:
                    algo = "aes256_gcm"
            if algo == "aes256_cfb":
                return partial(aes_core.encrypt_file, p, self.password,
                               self.encrypt_name, self.chunk_size, False, progress_cb)
            elif algo == "chacha20_poly1305":
                return partial(xchacha_core.encrypt_file, p, self.password,
                               self.encrypt_name, self.chunk_size, progress_cb)
            else:
                return partial(aes_core.encrypt_file, p, self.password,
                               self.encrypt_name, self.chunk_size, True, progress_cb)
        else:
            low = (p or "").lower()
            if low.endswith(".gfglock") or low.endswith(".gfglck"):
                return partial(aes_core.decrypt_file, p, self.password, self.chunk_size, progress_cb)
            elif low.endswith(".gfgcha"):
                return partial(xchacha_core.decrypt_file, p, self.password, self.chunk_size, progress_cb)
            else:
                def _unknown(path, password, chunk_size=None):
                    return False, f"Skipping unknown encrypted file format: {path}"
                return partial(_unknown, p, self.password, self.chunk_size)

    def _is_skip(self, p: str, msg: str) -> bool:
        """Determine if a failed result is a skip (not an actual error)."""
        low = (p or "").lower()
        encrypted_exts = (".gfglock", ".gfglck", ".gfgcha")
        if self.mode == "encrypt":
            return (bool(msg) and "already encrypted" in msg.lower()) or low.endswith(encrypted_exts)
        else:
            return (bool(msg) and "already decrypted" in msg.lower()) or not low.endswith(encrypted_exts)
