# worker.py - background encryption/decryption worker (PySide6)

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from functools import partial
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core import aes256_gcm_cfb as aes_core
from gfglock.core import chacha20_poly1305 as xchacha_core
from gfglock.core.file_ops import FileResult
from gfglock.utils import load_settings, predict_encrypted_size
from gfglock.utils.logging import write_log

OUTCOME_DONE = "done"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


class WorkerSignals(QObject):
    # progress: (processed_bytes, total_bytes) across every file
    progress = Signal(float, float)
    # files_progress: (completed_files, total_files)
    files_progress = Signal(int, int)
    # file_started: path, when a file begins
    file_started = Signal(str)
    # file_progress: (path, fraction 0-1), at most once per whole percent
    file_progress = Signal(str, float)
    # file_result: (path, outcome, reason, output_path, log_message), once per file
    file_result = Signal(str, str, str, str, str)
    error = Signal(str)
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
        read_size: int = 0,
        enc_algo: str | None = None,
    ):
        super().__init__()
        self.paths = list(paths)
        self.password = password
        self.mode = mode
        self.encrypt_name = encrypt_name
        self.threads = max(1, int(threads))
        self.read_size = max(0, int(read_size or 0))  # bytes per read; 0 lets the engine choose
        self._cancelled = False
        self.enc_algo = enc_algo or self._default_algorithm()
        self._per_file_sizes: dict[str, float] = {}
        # Measured in run(), off the GUI thread: sizing thousands of files (or files on a network
        # share) takes long enough to freeze the window.
        self.total_bytes = 1.0
        self.processed_bytes = 0.0
        self._progress_lock = threading.Lock()
        self.signals = WorkerSignals()

    @staticmethod
    def _default_algorithm() -> str:
        """The algorithm chosen in preferences, used when the caller passes none."""
        try:
            return load_settings().get("advanced", {}).get("encryption_mode", "aes256_gcm")
        except Exception as error:  # a damaged settings file must not stop encryption
            write_log(f"Could not read the default algorithm: {error}", "critical")
            return "aes256_gcm"

    def _calc_total_size(self) -> float:
        """Total bytes the operation will process, for the overall progress bar."""
        size_mode = {"aes256_cfb": "CFB", "chacha20_poly1305": "CHACHA"}.get(self.enc_algo, "GCM")
        total = 0.0
        for path in self.paths:
            if not os.path.isfile(path):
                continue
            try:
                size = float(predict_encrypted_size(path, size_mode) if self.mode == "encrypt"
                             else os.path.getsize(path))
            except OSError:
                size = 0.0
            self._per_file_sizes[path] = size
            total += size
        return max(total, 1.0)

    def _make_progress_callback(self, path: str) -> Callable[[float], None]:
        """Create a per-file chunk progress callback that also reports the file's own percent."""
        file_total = max(self._per_file_sizes.get(path, 0.0), 1.0)
        state = {"done": 0.0, "percent": -1}

        def callback(chunk_bytes: float) -> None:
            # Native workers report from several threads at once; without the lock two
            # read-modify-writes can interleave and drop progress.
            with self._progress_lock:
                self.processed_bytes = min(self.processed_bytes + float(chunk_bytes), self.total_bytes)
                done = self.processed_bytes
                state["done"] += float(chunk_bytes)
                percent = min(100, int(state["done"] * 100 / file_total))
                changed = percent != state["percent"]
                state["percent"] = percent
            self.signals.progress.emit(done, self.total_bytes)
            if changed:
                self.signals.file_progress.emit(path, percent / 100.0)
        return callback

    @Slot()
    def cancel(self) -> None:
        """Stop starting new files; the files already being processed finish normally."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the encrypt/decrypt operation on the thread pool."""
        total = len(self.paths)
        completed = succeeded = failed = skipped = 0
        start_time = time.time()
        try:
            self.total_bytes = self._calc_total_size()
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                pending: dict[Future, str] = {}
                queue = iter(self.paths)

                def submit_next() -> None:
                    if self._cancelled:
                        return
                    path = next(queue, None)
                    if path is None:
                        return
                    self.signals.file_started.emit(path)
                    pending[executor.submit(self._build_job(path, self._make_progress_callback(path)))] = path

                for _ in range(min(self.threads, total)):
                    submit_next()

                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        path = pending.pop(future)
                        outcome = self._report(path, future)
                        succeeded += outcome == OUTCOME_DONE
                        failed += outcome == OUTCOME_FAILED
                        skipped += outcome == OUTCOME_SKIPPED
                        completed += 1
                        self.signals.files_progress.emit(completed, total)
                        submit_next()
        except Exception as error:  # the executor itself failing must still end the run
            write_log(f"Operation stopped unexpectedly: {error}", "critical")
            self.signals.error.emit(str(error))

        if not self._cancelled:
            self.signals.progress.emit(self.total_bytes, self.total_bytes)
        self.signals.finished.emit(time.time() - start_time, total, succeeded, failed, skipped)

    def _report(self, path: str, future: Future) -> str:
        """Emit one file's result and return its outcome."""
        try:
            result = future.result()
        except Exception as error:  # a crash in one file must not stop the others
            message = f"Critical error while processing {path}: {error}"
            self.signals.file_result.emit(path, OUTCOME_FAILED, f"Unexpected error: {error}", "", message)
            return OUTCOME_FAILED
        self.signals.file_result.emit(path, result.outcome, result.reason, result.output, result[1])
        return result.outcome

    def _build_job(self, path: str, progress_cb: Callable) -> Callable:
        """Return the encrypt/decrypt callable for one file."""
        if self.mode == "encrypt":
            if self.enc_algo == "chacha20_poly1305":
                return partial(xchacha_core.encrypt_file, path, self.password, self.encrypt_name,
                               read_size=self.read_size, progress_callback=progress_cb)
            return partial(aes_core.encrypt_file, path, self.password, self.encrypt_name,
                           read_size=self.read_size, AEAD=self.enc_algo != "aes256_cfb",
                           progress_callback=progress_cb)
        low = path.lower()
        if low.endswith((".gfglock", ".gfglck")):
            return partial(aes_core.decrypt_file, path, self.password, self.read_size, progress_cb)
        if low.endswith(".gfgcha"):
            return partial(xchacha_core.decrypt_file, path, self.password, self.read_size, progress_cb)
        return partial(FileResult, False, f"{path} is not an encrypted gfgLock file",
                       OUTCOME_SKIPPED, "Not an encrypted gfgLock file")
