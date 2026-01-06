# worker.py
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from PyQt6 import QtCore
from core import aes256_gcm_cfb as aes_core
from core import chacha20_poly1305 as xchacha_core
from utils import load_settings


class WorkerSignals(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
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

        self.signals = WorkerSignals()

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
            succeeded = 0
            failed = 0
            skipped_already_encrypted = 0
            failed_files = []

            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                future_to_path = {}

                for p in self.paths:
                    if self._cancelled:
                        break

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
                                          self.encrypt_name, self.chunk_size, False)
                        elif algo == "chacha20_poly1305":
                            job = partial(xchacha_core.encrypt_file, p, self.password,
                                          self.encrypt_name, self.chunk_size)
                        else:
                            # default to AES GCM AEAD
                            job = partial(aes_core.encrypt_file, p, self.password,
                                          self.encrypt_name, self.chunk_size, True)
                    else:
                        # decrypt: choose core by file extension
                        low = (p or "").lower()
                        if low.endswith('.gfglock'):
                            job = partial(aes_core.decrypt_file, p, self.password,
                                          self.chunk_size)
                        elif low.endswith('.gfglck'):
                            # CFB variant
                            job = partial(aes_core.decrypt_file, p, self.password,
                                          self.chunk_size)
                        elif low.endswith('.gfgcha'):
                            job = partial(xchacha_core.decrypt_file, p, self.password,
                                          self.chunk_size)
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

                    done += 1
                    self.signals.progress.emit(done, total)
                    # notify current file label (path)
                    self.signals.file_changed.emit(p)

        except Exception as e:
            self.signals.error.emit(str(e))

        elapsed = time.time() - start_time
        self.signals.status.emit(f"Completed in {elapsed:.2f} sec")
        self.signals.finished.emit(elapsed, total, succeeded, failed, skipped_already_encrypted)
