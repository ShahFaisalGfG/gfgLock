# worker.py
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import Callable

from PyQt6 import QtCore
from core import aes256_gcm_cfb as aes_core
from core import chacha20_poly1305 as xchacha_core
from utils import load_settings
from utils import predict_encrypted_size


class WorkerSignals(QtCore.QObject):
    # Use object type for progress to avoid 32-bit overflow when sending byte counts
    progress = QtCore.pyqtSignal(object, object)
    # File-level progress: number of completed files, total files
    files_progress = QtCore.pyqtSignal(int, int)
    file_changed = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(float, int, int, int, int)   # elapsed_time, total_files, succeeded, failed, skipped_already_encrypted


class EncryptDecryptWorker(QtCore.QRunnable):
    def __init__(self, paths, password, mode="encrypt",
                 encrypt_name=False, threads=1, chunk_size=None,
                 show_password=False, enc_algo: str | None = None):
        super().__init__()
        self.paths = list(paths)
        self.password = password
        self.mode = mode
        self.encrypt_name = encrypt_name
        self.threads = int(threads)
        # Accept None to indicate non-chunked processing
        self.chunk_size = None if chunk_size is None else int(chunk_size)
        self._cancelled = False
        # enc_algo: 'aes256_gcm' | 'aes256_cfb' | 'chacha20_poly1305'
        self.enc_algo = enc_algo

        # Calculate total size for progress tracking (in bytes)
        self.total_bytes = float(self._calculate_total_size())
        self.processed_bytes = 0.0  # Track bytes with float for precision
        self._files_completed = 0  # Track number of completed files (int)

        self.signals = WorkerSignals()

    def _calculate_total_size(self) -> float:
        """
        Calculate total size that will be processed.
        For encryption: use predicted encrypted file size.
        For decryption: use actual file size.
        Returns total bytes.
        """
        total = 0.0
        # per-file predicted sizes to avoid re-checking files after they may be removed
        self._per_file_sizes = {}
        
        if self.mode == "encrypt":
            # Determine algorithm to use for size prediction
            algo = self.enc_algo
            if not algo:
                try:
                    settings = load_settings()
                    algo = settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                except Exception:
                    algo = "aes256_gcm"
            
            # Map algorithm to predict_encrypted_size mode parameter
            if algo == "aes256_cfb":
                size_mode = "CFB"
            elif algo == "chacha20_poly1305":
                size_mode = "CHACHA"
            else:
                size_mode = "GCM"
            
            for path in self.paths:
                if os.path.exists(path) and os.path.isfile(path):
                    try:
                        predicted = float(predict_encrypted_size(path, size_mode))
                        total += predicted
                        self._per_file_sizes[path] = predicted
                    except Exception:
                        # Fallback: just add file size if prediction fails
                        try:
                            fs = float(os.path.getsize(path))
                        except Exception:
                            fs = 0.0
                        total += fs
                        self._per_file_sizes[path] = fs
        else:
            # For decryption: sum actual encrypted file sizes
            for path in self.paths:
                if os.path.exists(path) and os.path.isfile(path):
                    try:
                        fs = float(os.path.getsize(path))
                        total += fs
                        self._per_file_sizes[path] = fs
                    except Exception:
                        self._per_file_sizes[path] = 0.0
        
        return max(total, 1.0)  # Ensure at least 1 to avoid division by zero

    def _make_progress_callback(self, file_index: int, total_files: int) -> Callable[[float], None]:
        """
        Create a progress callback that updates processed_bytes and emits progress signals.
        This callback is called after each chunk is processed within a file.
        """
        def callback(chunk_bytes: float):
            """Called by encryption/decryption functions after each chunk.
            
            Args:
                chunk_bytes: Number of bytes processed in this chunk
            """
            self.processed_bytes += float(chunk_bytes)
            # Clamp to total_bytes to ensure progress doesn't exceed 100%
            self.processed_bytes = min(self.processed_bytes, self.total_bytes)
            # Emit only byte-level progress (per-chunk updates)
            # File count will be updated only when a file actually completes
            self.signals.progress.emit(self.processed_bytes, self.total_bytes)
        
        return callback

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.paths)
        done = 0
        start_time = time.time()
        # initialize counts so they're available even on unexpected errors
        succeeded = 0
        failed = 0
        skipped_already_encrypted = 0
        failed_files = []

        try:
            print(f"[DEBUG] Worker started: mode={self.mode}, total_files={len(self.paths)}, total_bytes={self.total_bytes}")
            succeeded = 0
            failed = 0
            skipped_already_encrypted = 0
            failed_files = []

            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                future_to_path = {}

                for file_index, p in enumerate(self.paths):
                    if self._cancelled:
                        break                    
                    # Create progress callback for this file
                    progress_cb = self._make_progress_callback(file_index, len(self.paths))

                    # Determine job based on mode and file extension / selected algorithm
                    if self.mode == "encrypt":
                        # decide algorithm: explicit override, else load from settings
                        algo = self.enc_algo
                        if not algo:
                            try:
                                settings = load_settings()
                                algo = settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                            except Exception:
                                algo = "aes256_gcm"

                        if algo == "aes256_cfb":
                            job = partial(aes_core.encrypt_file, p, self.password,
                                          self.encrypt_name, self.chunk_size, False, progress_cb)
                        elif algo == "chacha20_poly1305":
                            job = partial(xchacha_core.encrypt_file, p, self.password,
                                          self.encrypt_name, self.chunk_size, progress_cb)
                        else:
                            # default to AES GCM AEAD
                            job = partial(aes_core.encrypt_file, p, self.password,
                                          self.encrypt_name, self.chunk_size, True, progress_cb)
                    else:
                        # decrypt: choose core by file extension
                        low = (p or "").lower()
                        if low.endswith('.gfglock'):
                            job = partial(aes_core.decrypt_file, p, self.password,
                                          self.chunk_size, progress_cb)
                        elif low.endswith('.gfglck'):
                            # CFB variant
                            job = partial(aes_core.decrypt_file, p, self.password,
                                          self.chunk_size, progress_cb)
                        elif low.endswith('.gfgcha'):
                            job = partial(xchacha_core.decrypt_file, p, self.password,
                                          self.chunk_size, progress_cb)
                        else:
                            # Unknown extension — create a job that returns a skipped message
                            def unknown_job(path, password, chunk_size=None):
                                return False, f"Skipping unknown encrypted file format: {path}"
                            job = partial(unknown_job, p, self.password, self.chunk_size)

                    fut = executor.submit(job)
                    future_to_path[fut] = p

                for fut in as_completed(future_to_path):
                    if self._cancelled:
                        break

                    p = future_to_path.get(fut, "")
                    try:
                        result = fut.result()
                        # result expected as (success, message) from core
                        if isinstance(result, tuple):
                            success, msg = result
                        else:
                            success = bool(result)
                            msg = ""

                        # forward core message to GUI logs
                        if msg:
                            self.signals.status.emit(msg)

                        # Debug: log result for the file
                        try:
                            dbg_msg = msg.replace('\n', ' | ') if isinstance(msg, str) else ''
                        except Exception:
                            dbg_msg = str(msg)
                        print(f"[DEBUG] Result for {p}: success={success}, msg={dbg_msg}")

                        if success:
                            succeeded += 1
                        else:
                                # Check if this was a skip (already encrypted/decrypted)
                                is_skipped = False
                                lowp = (p or "").lower()
                                encrypted_exts = ('.gfglock', '.gfglck', '.gfgcha')
                                if self.mode == 'encrypt':
                                    if msg and 'already encrypted' in msg.lower():
                                        is_skipped = True
                                    elif p and lowp.endswith(encrypted_exts):
                                        is_skipped = True
                                elif self.mode == 'decrypt':
                                    if msg and 'already decrypted' in msg.lower():
                                        is_skipped = True
                                    elif p and not lowp.endswith(encrypted_exts):
                                        is_skipped = True
                                if is_skipped:
                                    skipped_already_encrypted += 1
                                else:
                                    failed += 1
                                    failed_files.append(p)
                    except Exception as e:
                        failed += 1
                        failed_files.append(p)
                        self.signals.error.emit(str(e))
                        print(f"[DEBUG] Exception processing {p}: {e}")

                    done += 1
                    # File has completed successfully or failed
                    # Increment the completed files counter (this always increases)
                    self._files_completed += 1
                    # Emit both signals: byte progress and file count
                    # File count only updates when files actually complete (in correct order)
                    try:
                        self.signals.progress.emit(self.processed_bytes, self.total_bytes)
                        self.signals.files_progress.emit(self._files_completed, total)
                    except Exception:
                        pass
                    # notify current file label (path)
                    self.signals.file_changed.emit(p)

        except Exception as e:
            self.signals.error.emit(str(e))

        # Ensure progress bar reaches exactly 100% before finished signal
        # This guarantees the UI shows complete progress even if last chunk was small
        try:
            self.signals.progress.emit(self.total_bytes, self.total_bytes)
        except Exception:
            pass

        elapsed = time.time() - start_time
        self.signals.status.emit(f"Completed in {elapsed:.2f} sec")
        self.signals.finished.emit(elapsed, total, succeeded, failed, skipped_already_encrypted)
