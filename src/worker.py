# worker.py
import time
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5 import QtCore
import gfglock_fast_aes256_cryptography as core


class WorkerSignals(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    file_changed = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(float, int, int, int, int)   # elapsed_time, total_files, succeeded, failed, skipped_already_encrypted


class EncryptDecryptWorker(QtCore.QRunnable):
    def __init__(self, paths, password, mode="encrypt",
                 encrypt_name=False, threads=1, chunk_size=8*1024*1024,
                 show_password=False):
        super().__init__()
        self.paths = list(paths)
        self.password = password
        self.mode = mode
        self.encrypt_name = encrypt_name
        self.threads = int(threads)
        self.chunk_size = int(chunk_size)
        self._cancelled = False

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

                    if self.mode == "encrypt":
                        job = partial(core.encrypt_file, p, self.password,
                                      self.encrypt_name, self.chunk_size)
                    else:
                        job = partial(core.decrypt_file, p, self.password,
                                      self.chunk_size)

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
                            # Check if this was an expected 'already encrypted' skip
                            is_already_encrypted = False
                            if self.mode == 'encrypt':
                                if msg and 'already encrypted' in msg.lower():
                                    is_already_encrypted = True
                                elif p and p.lower().endswith('.gfglock'):
                                    is_already_encrypted = True

                            if is_already_encrypted:
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
