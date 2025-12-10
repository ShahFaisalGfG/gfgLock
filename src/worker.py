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
    finished = QtCore.pyqtSignal(float, int)   # elapsed_time, total_files


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

        try:
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = []

                for p in self.paths:
                    if self._cancelled:
                        break

                    if self.mode == "encrypt":
                        job = partial(core.encrypt_file, p, self.password,
                                      self.encrypt_name, self.chunk_size)
                    else:
                        job = partial(core.decrypt_file, p, self.password,
                                      self.chunk_size)

                    futures.append(executor.submit(job))

                for fut in as_completed(futures):
                    if self._cancelled:
                        break

                    try:
                        fut.result()
                    except Exception as e:
                        self.signals.error.emit(str(e))

                    done += 1
                    self.signals.progress.emit(done, total)
                    self.signals.file_changed.emit(f"{done}/{total}")

        except Exception as e:
            self.signals.error.emit(str(e))

        elapsed = time.time() - start_time
        self.signals.status.emit(f"Completed in {elapsed:.2f} sec")
        self.signals.finished.emit(elapsed, total)
