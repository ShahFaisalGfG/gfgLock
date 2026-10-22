# worker.py - background encryption/decryption worker (PySide6)

import ctypes
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from ctypes import wintypes
from functools import partial

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.config.defaults import ReadSizeDefaults
from gfglock.core import file_ops
from gfglock.core.format_v2 import KeyRing
from gfglock.utils.logging import RunLog, write_log

OUTCOME_DONE = "done"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"

# Each thread holds about this many read-size buffers at once (the engines keep 4 blocks in flight,
# each with an input and an output buffer). The read size is lowered so that every thread's buffers
# together stay within 1/MEMORY_SHARE of the free physical memory.
BLOCKS_PER_THREAD = 8
MEMORY_SHARE = 4
MIN_READ_SIZE = 1024 * 1024
# The run's byte progress is sent at most this often; a run of many small files would otherwise
# queue a signal per file for a bar that redraws ten times a second.
PROGRESS_INTERVAL_S = 0.05

# Folders that running runs write temp files in (normcase path -> runs). A run starting at the same
# time in the other tab must not clear them as leftovers: they are closed between engine steps.
_claims: Counter[str] = Counter()
_claims_lock = threading.Lock()


@contextmanager
def _claim_folders(folders: list[str]) -> Iterator[list[str]]:
    """Claim the run's folders while it runs; yields those no other running run had claimed,
    which are the ones safe to clear of leftover temp files."""
    keys = [os.path.normcase(folder) for folder in folders]
    with _claims_lock:
        free = [folder for folder, key in zip(folders, keys) if not _claims[key]]
        _claims.update(keys)
    try:
        yield free
    finally:
        with _claims_lock:
            _claims.subtract(keys)
            for key in keys:
                if _claims[key] <= 0:
                    del _claims[key]


class _MemoryStatus(ctypes.Structure):
    """MEMORYSTATUSEX, as GlobalMemoryStatusEx fills it in."""

    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def available_memory() -> int | None:
    """Free physical memory in bytes, or None when Windows can't report it."""
    if sys.platform != "win32":
        return None
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys)


def capped_read_size(read_size: int, threads: int, available: int | None) -> int:
    """The read size to run with: the chosen one (0 = the default), lowered when the threads'
    blocks would take more than their share of the free memory, but never below 1 MiB."""
    if available is None:
        return read_size
    limit = available // MEMORY_SHARE // (max(1, threads) * BLOCKS_PER_THREAD)
    limit = max(MIN_READ_SIZE, limit // MIN_READ_SIZE * MIN_READ_SIZE)
    return read_size if (read_size or ReadSizeDefaults.DEFAULT_BYTES) <= limit else limit


class WorkerSignals(QObject):
    """What a run reports; the controller receives every signal queued, on the GUI thread."""

    # progress: (bytes read so far, total bytes of the run's files), every PROGRESS_INTERVAL_S at most
    # and once when the last file has ended
    progress = Signal(float, float)
    # file_started: path, when a file begins
    file_started = Signal(str)
    # file_progress: (path, fraction 0-1) while a file is under way, at most once per whole percent
    file_progress = Signal(str, float)
    # file_result: (path, outcome, reason, output_path), once per file
    file_result = Signal(str, str, str, str)
    # temps_removed: how many temp files left by an interrupted run were deleted at the start
    temps_removed = Signal(int)
    error = Signal(str)
    # finished: (elapsed_time, total_files, succeeded, failed, skipped)
    finished = Signal(float, int, int, int, int)


class EncryptDecryptWorker(QRunnable):
    """Encrypt or decrypt a list of files on `threads` threads, reporting progress and each result."""

    def __init__(
        self,
        paths,
        keys: KeyRing,
        mode: str = "encrypt",
        encrypt_name: bool = False,
        threads: int = 1,
        read_size: int = 0,
        algorithm: str = "gcm",
    ):
        super().__init__()
        self.paths = list(paths)
        self.keys = keys
        self.mode = mode
        self.encrypt_name = encrypt_name
        self.threads = max(1, int(threads))
        self.read_size = max(0, int(read_size or 0))  # bytes per read; 0 lets the engine choose
        self.algorithm = algorithm  # a file_ops code, used when encrypting
        self._cancelled = False
        self._stop = file_ops.new_stop_token()
        # Measured in run(), off the GUI thread: sizing thousands of files (or files on a network
        # share) takes long enough to freeze the window.
        self._sizes: dict[str, int] = {}
        self._read: dict[str, int] = {}
        self.total_bytes = 1
        self._done_bytes = 0
        self._progress_sent = 0.0
        self._progress_lock = threading.Lock()
        self._outcomes: Counter[str] = Counter()
        self.signals = WorkerSignals()

    @Slot()
    def cancel(self) -> None:
        """Stop the run: no new files start, and the files in progress stop and stay unchanged."""
        self._cancelled = True
        self._stop.cancel()

    def run(self) -> None:
        """Execute the encrypt/decrypt operation on the thread pool."""
        start_time = time.monotonic()
        folders = sorted({os.path.dirname(os.path.abspath(path)) for path in self.paths})
        try:
            with RunLog() as log, _claim_folders(folders) as free_folders:
                read_size = self._prepare(log, free_folders)
                self._process(read_size, log)
        except Exception as error:  # a failure outside the files' own jobs must still end the run
            write_log(f"Operation stopped unexpectedly: {error}", "critical")
            self.signals.error.emit(f"The run stopped unexpectedly: {error}")
        self.signals.finished.emit(time.monotonic() - start_time, len(self.paths), self._outcomes[OUTCOME_DONE],
                                   self._outcomes[OUTCOME_FAILED], self._outcomes[OUTCOME_SKIPPED])

    def _prepare(self, log: RunLog, folders: list[str]) -> int:
        """Size the files, pick the read size, and clear the given folders of temp files that an
        interrupted run left behind. Returns the read size."""
        for path in self.paths:
            if self._cancelled:  # sizing thousands of files on a network share takes a while
                break
            try:
                self._sizes[path] = os.path.getsize(path)
            except OSError:
                self._sizes[path] = 0  # missing or unreadable: the file's own result says why
        self.total_bytes = max(sum(self._sizes.values()), 1)
        read_size = capped_read_size(self.read_size, self.threads, available_memory())
        if read_size != self.read_size:
            log.write(f"Read size lowered to {read_size // MIN_READ_SIZE} MB to fit in the free memory")
        removed = file_ops.remove_stale_temps(folders)
        if removed:
            log.write(f"Removed {removed} temporary {'file' if removed == 1 else 'files'} left by an earlier run")
            self.signals.temps_removed.emit(removed)
        return read_size

    def _process(self, read_size: int, log: RunLog) -> None:
        """Run the files on `threads` threads. Each thread takes the next file as soon as it is free,
        so a run of many small files never waits on a hand-off between threads."""
        queue = iter(self.paths)
        queue_lock = threading.Lock()

        def next_path() -> str | None:
            with queue_lock:
                return None if self._cancelled else next(queue, None)

        def work() -> None:
            while (path := next_path()) is not None:
                self.signals.file_started.emit(path)
                self._process_file(path, read_size, log)

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            runners = [executor.submit(work) for _ in range(min(self.threads, len(self.paths)))]
        for runner in runners:
            runner.result()  # re-raises an error outside the files' own jobs, which ends the run
        with self._progress_lock:
            done_bytes = self._done_bytes
        self.signals.progress.emit(float(done_bytes), float(self.total_bytes))

    def _process_file(self, path: str, read_size: int, log: RunLog) -> None:
        """Encrypt or decrypt one file, then log and emit its result."""
        try:
            result = self._build_job(path, read_size)()
        except Exception as error:  # a crash in one file must not stop the others
            outcome, reason, output = OUTCOME_FAILED, f"Unexpected error: {error}", ""
            message = f"Critical error while processing {path}: {error}"
        else:
            outcome, reason, output = result.outcome, result.reason, result.output
            message = self._log_message(result)
        with self._progress_lock:
            self._outcomes[outcome] += 1
        log.write(message, critical=outcome == OUTCOME_FAILED)
        self._add_progress(path, self._sizes.get(path, 0))
        self.signals.file_result.emit(path, outcome, reason, output)

    def _log_message(self, result: file_ops.FileResult) -> str:
        """The result's log line. With hidden names, an encrypted file is logged by its new name only,
        so the log never pairs the hidden name with the original one."""
        if self.encrypt_name and self.mode == "encrypt" and result.outcome == OUTCOME_DONE:
            return f"Encrypted: {result.output}"
        return result[1]

    def _add_progress(self, path: str, read: int) -> None:
        """Record that `read` bytes of path have been read in all, and report the run's progress
        unless it was reported less than PROGRESS_INTERVAL_S ago."""
        with self._progress_lock:
            read = min(read, self._sizes.get(path, 0))
            previous = self._read.get(path, 0)
            if read <= previous:
                return
            self._read[path] = read
            self._done_bytes += read - previous
            now = time.monotonic()
            if now - self._progress_sent < PROGRESS_INTERVAL_S:
                return
            self._progress_sent = now
            done = self._done_bytes
        self.signals.progress.emit(float(done), float(self.total_bytes))

    def _make_progress_callback(self, path: str) -> Callable[[float], None]:
        """A callback for the engine's progress (bytes read since its last call) that also reports
        the file's own percent, at most once per whole percent. 0% is shown when the file starts and
        100% when its result arrives, so neither is sent from here."""
        size = self._sizes.get(path, 0)
        state = {"read": 0, "percent": 0}

        def callback(amount: float) -> None:
            state["read"] += int(amount)
            self._add_progress(path, state["read"])
            percent = min(100, state["read"] * 100 // size) if size else 100
            if percent != state["percent"] and percent < 100:
                state["percent"] = percent
                self.signals.file_progress.emit(path, percent / 100.0)
        return callback

    def _build_job(self, path: str, read_size: int) -> Callable[[], file_ops.FileResult]:
        """Return the encrypt/decrypt callable for one file."""
        progress = self._make_progress_callback(path)
        if self.mode == "encrypt":
            return partial(file_ops.encrypt_file, path, self.keys, self.algorithm, encrypt_name=self.encrypt_name,
                           read_size=read_size, progress=progress, stop=self._stop)
        return partial(file_ops.decrypt_file, path, self.keys, read_size=read_size, progress=progress, stop=self._stop)
