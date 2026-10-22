"""Measure the fastest read size and files at a time on this PC, for encrypting and for decrypting.

The best values depend on the disk and the processor, so they are measured, not guessed. Scratch
files in the temp folder go through the same file_ops path as the user's files. Before every timed
pass the files it reads are dropped from the Windows file cache, so the reads come from the disk as
they would for files that weren't just written, and the key is derived once before any timing.
Every value is timed in two rounds, the second in reverse order, and its faster run counts; that
evens out brief background disk activity.

1. Read size: one large file is encrypted and decrypted with each read size. The time runs until
   the engine has read the whole file, so the flush to disk afterwards, the same for every size,
   stays out of it.
2. Files at a time: a batch of smaller files is encrypted and decrypted 1, 2, 4, ... at a time with
   the read size just picked. The whole run counts here, flushes included, since they overlap.

A value replaces the default only when it is at least MARGIN faster.
"""

from __future__ import annotations

import ctypes
import math
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from dataclasses import dataclass
from typing import NamedTuple

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.config.defaults import ReadSizeDefaults
from gfglock.core import file_ops
from gfglock.core.format_v2 import KeyRing
from gfglock.core.py_cipher import StopToken
from gfglock.utils.logging import write_log

# The whole test takes about a minute on a 4-core desktop with a SATA SSD (63 s measured).
TEST_FILE_SIZE = 256 * 1024 * 1024
BATCH_FILE_SIZE = 8 * 1024 * 1024
ROUNDS = 2
MARGIN = 0.05
_FILL_BLOCK = 8 * 1024 * 1024
_PASSWORD = "gfgLock speed test"
_TEST_NAME = "speed test.bin"
_FOLDER_PREFIX = "gfglock_speed_"

_GENERIC_READ = 0x80000000
_SHARE_ALL = 0x7  # read, write, and delete
_OPEN_EXISTING = 3
_FILE_FLAG_NO_BUFFERING = 0x20000000
_INVALID_HANDLE = wintypes.HANDLE(-1).value
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateFileW = _kernel32.CreateFileW
_CreateFileW.restype = wintypes.HANDLE
_CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.restype = wintypes.BOOL
_CloseHandle.argtypes = [wintypes.HANDLE]


class ReadSizeTestError(Exception):
    """The test could not run; the message is shown to the user."""


class ReadSizeTestCancelled(Exception):
    """The user stopped the test."""


@dataclass(frozen=True)
class Choice:
    """The fastest settings found for one direction and the speed they reached."""

    read_size: int  # 0 is the default read size
    threads: int
    bytes_per_s: float


@dataclass(frozen=True)
class SpeedResult:
    """What the speed test picked for encrypting and for decrypting."""

    encrypt: Choice
    decrypt: Choice


class _Timing(NamedTuple):
    """One timed pass: seconds until its files were read, seconds until it finished, the files it wrote."""

    read_s: float
    total_s: float
    outputs: list[str]


def run_speed_test(
    algorithm: str,
    thread_limit: int,
    default_threads: int,
    *,
    keys: KeyRing | None = None,
    stop: StopToken | None = None,
    folder: str | None = None,
    on_step: Callable[[int, int], None] = lambda done, total: None,
    sizes: Sequence[int] = ReadSizeDefaults.TEST_SIZES,
    file_size: int = TEST_FILE_SIZE,
    batch_size: int = BATCH_FILE_SIZE,
) -> SpeedResult:
    """Time each read size, then each number of files at a time, and return the fastest of each.

    Raises ReadSizeTestError when the test can't run (too little free space, a failed pass) and
    ReadSizeTestCancelled when `stop` is cancelled.
    """
    folder = folder or tempfile.gettempdir()
    remove_stale(folder)
    counts = thread_counts(thread_limit, default_threads)
    batch_names = [f"speed test {index + 1}.bin" for index in range(2 * counts[-1])]
    batch_bytes = len(batch_names) * batch_size
    # A file and its encrypted copy exist together, with room to spare.
    needed = 3 * max(file_size, batch_bytes)
    if shutil.disk_usage(folder).free < needed:
        raise ReadSizeTestError(f"The test needs {needed // (1024 * 1024)} MB of free space on the system drive.")
    keys = keys or KeyRing(_PASSWORD)
    keys.new_header(algorithm)  # derives the key now, so no timed pass includes it
    passes = _Passes(algorithm, keys, stop, on_step, total=2 * ROUNDS * (len(sizes) + len(counts)))
    with tempfile.TemporaryDirectory(prefix=_FOLDER_PREFIX, dir=folder, ignore_cleanup_errors=True) as work:
        source = os.path.join(work, _TEST_NAME)
        _write_test_file(source, file_size, stop)
        encrypt_size, decrypt_size = _time_sizes(passes, source, sizes)
        batch = [os.path.join(work, name) for name in batch_names]
        for path in batch:
            _write_test_file(path, batch_size, stop)
        encrypt_times, decrypt_times = _time_counts(passes, batch, counts, encrypt_size, decrypt_size)
        encrypt_threads = pick_fastest(encrypt_times, default_threads)
        decrypt_threads = pick_fastest(decrypt_times, default_threads)
        return SpeedResult(
            Choice(_size_code(encrypt_size), encrypt_threads, batch_bytes / encrypt_times[encrypt_threads]),
            Choice(_size_code(decrypt_size), decrypt_threads, batch_bytes / decrypt_times[decrypt_threads]),
        )


def thread_counts(limit: int, default: int) -> list[int]:
    """The files-at-a-time values to time: 1, 2, 4, ... below limit, then limit, plus the default."""
    counts = {limit, max(1, min(default, limit))}
    count = 1
    while count < limit:
        counts.add(count)
        count *= 2
    return sorted(counts)


def pick_fastest(seconds: dict[int, float], default: int, margin: float = MARGIN) -> int:
    """The value with the shortest time, or `default` unless that value beats the default's time by margin.

    Differences of a few percent are within run-to-run variation, so they don't justify moving
    away from the default.
    """
    fastest = min(seconds, key=seconds.__getitem__)
    baseline = seconds.get(default)
    if baseline is None or seconds[fastest] < baseline * (1 - margin):
        return fastest
    return default


def evict_cache(path: str) -> None:
    """Drop a file's pages from the Windows file cache, so its next read comes from the disk.

    Opening a file without buffering makes Windows flush and purge the pages it has cached for it.
    """
    handle = _CreateFileW(path, _GENERIC_READ, _SHARE_ALL, None, _OPEN_EXISTING, _FILE_FLAG_NO_BUFFERING, None)
    if handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    _CloseHandle(handle)


def remove_stale(folder: str) -> None:
    """Delete the scratch folders of speed tests that a crash or a kill ended before cleanup."""
    try:
        entries = list(os.scandir(folder))
    except OSError as error:
        write_log(f"Could not look for old speed test files in {folder}: {error}", "critical")
        return
    for entry in entries:
        if entry.name.startswith(_FOLDER_PREFIX) and entry.is_dir(follow_symlinks=False) and not entry.is_junction():
            shutil.rmtree(entry.path, onexc=_log_removal)


def _log_removal(_function: Callable, path: str, error: BaseException) -> None:
    """rmtree's error handler: a file still held open (by an antivirus scan, say) stays for next time."""
    write_log(f"Could not remove {path}: {error}", "critical")


class _Passes:
    """Runs timed encrypt and decrypt passes and reports each one as a progress step."""

    def __init__(self, algorithm: str, keys: KeyRing, stop: StopToken | None,
                 on_step: Callable[[int, int], None], total: int) -> None:
        self._algorithm = algorithm
        self._keys = keys
        self._stop = stop
        self._on_step = on_step
        self._total = total
        self._done = 0

    def encrypt(self, paths: list[str], read_size: int, threads: int = 1) -> _Timing:
        """Encrypt every file in paths, `threads` at a time."""
        return self._run("Encrypting", paths, threads, lambda path, progress: file_ops.encrypt_file(
            path, self._keys, self._algorithm, read_size=read_size, progress=progress, stop=self._stop))

    def decrypt(self, paths: list[str], read_size: int, threads: int = 1) -> _Timing:
        """Decrypt every file in paths, `threads` at a time."""
        return self._run("Decrypting", paths, threads, lambda path, progress: file_ops.decrypt_file(
            path, self._keys, read_size=read_size, progress=progress, stop=self._stop))

    def _run(self, verb: str, paths: list[str], threads: int,
             job: Callable[[str, Callable[[float], None]], file_ops.FileResult]) -> _Timing:
        """Drop the inputs from the file cache, run job on each, and time it."""
        self._check_stop()
        for path in paths:
            evict_cache(path)
        reads: list[float] = []  # when the engine reported bytes read; its last report ends the reading

        def progress(_bytes: float) -> None:
            reads.append(time.perf_counter())

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=threads) as pool:
            results = list(pool.map(lambda path: job(path, progress), paths))
        finished = time.perf_counter()
        self._check_stop()
        failed = next((result for result in results if result.outcome != "done"), None)
        if failed is not None:
            raise ReadSizeTestError(f"{verb} the test file failed: {failed.reason}")
        self._done += 1
        self._on_step(self._done, self._total)
        return _Timing(max(reads, default=finished) - started, finished - started, [r.output for r in results])

    def _check_stop(self) -> None:
        if self._stop is not None and self._stop.cancelled:
            raise ReadSizeTestCancelled()


def _time_sizes(passes: _Passes, source: str, sizes: Sequence[int]) -> tuple[int, int]:
    """Encrypt and decrypt source with each read size; return the fastest sizes, then delete it."""
    best = {size: [math.inf, math.inf] for size in sizes}
    current = source
    for size in _rounds(sizes):
        encrypted = passes.encrypt([current], size)
        restored = passes.decrypt(encrypted.outputs, size)
        (current,) = restored.outputs
        best[size] = [min(best[size][0], encrypted.read_s), min(best[size][1], restored.read_s)]
    os.remove(current)
    default = ReadSizeDefaults.DEFAULT_BYTES
    return (pick_fastest({size: times[0] for size, times in best.items()}, default),
            pick_fastest({size: times[1] for size, times in best.items()}, default))


def _time_counts(passes: _Passes, batch: list[str], counts: Sequence[int], encrypt_size: int,
                 decrypt_size: int) -> tuple[dict[int, float], dict[int, float]]:
    """Encrypt and decrypt the batch with each number of files at a time; return the best times."""
    encrypt_times = dict.fromkeys(counts, math.inf)
    decrypt_times = dict.fromkeys(counts, math.inf)
    current = batch
    for count in _rounds(counts):
        encrypted = passes.encrypt(current, encrypt_size, count)
        restored = passes.decrypt(encrypted.outputs, decrypt_size, count)
        current = restored.outputs
        encrypt_times[count] = min(encrypt_times[count], encrypted.total_s)
        decrypt_times[count] = min(decrypt_times[count], restored.total_s)
    return encrypt_times, decrypt_times


def _rounds(values: Sequence[int]) -> Iterator[int]:
    """Every value once per round, every other round in reverse order."""
    for round_index in range(ROUNDS):
        yield from (values if round_index % 2 == 0 else list(reversed(values)))


def _size_code(size: int) -> int:
    """The settings value for a read size: 0 stands for the default size."""
    return ReadSizeDefaults.DEFAULT if size == ReadSizeDefaults.DEFAULT_BYTES else size


def _write_test_file(path: str, size: int, stop: StopToken | None = None) -> None:
    """Write `size` bytes of random data, so compressed folders or disks can't skew the timing."""
    block = os.urandom(_FILL_BLOCK)
    with open(path, "wb") as fh:
        for offset in range(0, size, len(block)):
            if stop is not None and stop.cancelled:
                raise ReadSizeTestCancelled()
            fh.write(block[: min(len(block), size - offset)])


class ReadSizeTestSignals(QObject):
    """Signals emitted while the speed test runs in the global thread pool."""

    progress = Signal(int, int)      # (passes done, total passes)
    finished = Signal(object, str)   # (SpeedResult or None, error message); both empty when stopped


class ReadSizeTestWorker(QRunnable):
    """Run run_speed_test() off the GUI thread."""

    def __init__(self, algorithm: str, thread_limit: int, default_threads: int) -> None:
        super().__init__()
        self.setAutoDelete(False)  # the controller keeps the worker so it can cancel it
        self.algorithm = algorithm
        self.thread_limit = thread_limit
        self.default_threads = default_threads
        self._stop = file_ops.new_stop_token()
        self.signals = ReadSizeTestSignals()

    def cancel(self) -> None:
        """Stop the test; the file being worked on stops within a block and is left unchanged."""
        self._stop.cancel()

    @Slot()
    def run(self) -> None:
        """Run the test and report the result, an error message, or nothing when stopped."""
        result: SpeedResult | None = None
        error = ""
        try:
            result = run_speed_test(self.algorithm, self.thread_limit, self.default_threads, stop=self._stop,
                                    on_step=self.signals.progress.emit)
        except ReadSizeTestCancelled:
            pass
        except ReadSizeTestError as failure:
            error = str(failure)
        except OSError as failure:
            error = f"The test couldn't finish: {failure.strerror or failure}."
        except Exception as failure:  # the thread boundary: any error must still end the test
            write_log(f"The speed test failed: {failure!r}", "critical")
            error = f"The test couldn't finish: {failure}."
        try:
            self.signals.finished.emit(result, error)
        except RuntimeError:
            pass  # the app is shutting down and the signal object is already gone
