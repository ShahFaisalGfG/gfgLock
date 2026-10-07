"""Time every read size on this PC to find the fastest one for encrypting and for decrypting.

The best read size depends on the disk and the processor's cache, so it is measured, not
guessed. A scratch file in the temp folder is encrypted and decrypted with each size through
the same path real files take (temp file, flush to disk, rename), so the timing includes the
disk. Every size is timed in two rounds, the second in reverse order, and its faster run
counts; that evens out the file cache warming up and brief background disk activity.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core import file_ops

TEST_FILE_SIZE = 256 * 1024 * 1024
ROUNDS = 2
_FILL_BLOCK = 8 * 1024 * 1024
_PASSWORD = "gfgLock read size test"
_TEST_NAME = "read size test.bin"


class ReadSizeTestError(Exception):
    """The test could not run; the message is shown to the user."""


class ReadSizeTestCancelled(Exception):
    """The user stopped the test."""


@dataclass(frozen=True)
class SizeTiming:
    """The best encrypt and decrypt time measured for one read size, in seconds."""

    read_size: int
    encrypt_s: float
    decrypt_s: float


def time_read_sizes(
    sizes: list[int],
    algorithm: str,
    folder: str | None = None,
    file_size: int = TEST_FILE_SIZE,
    is_cancelled: Callable[[], bool] = lambda: False,
    on_step: Callable[[int, int], None] = lambda done, total: None,
) -> list[SizeTiming]:
    """Encrypt and decrypt a scratch file with each read size and return the best times.

    Raises ReadSizeTestError when the test can't run (for example too little free space) and
    ReadSizeTestCancelled when is_cancelled() turns true between steps.
    """
    folder = folder or tempfile.gettempdir()
    # The source, the encrypted copy, and its temp file can all exist at once.
    needed = 3 * file_size
    if shutil.disk_usage(folder).free < needed:
        raise ReadSizeTestError(f"The test needs {needed // (1024 * 1024)} MB of free space on the system drive.")

    best: dict[int, list[float]] = {size: [float("inf"), float("inf")] for size in sizes}
    total = ROUNDS * len(sizes) * 2
    done = 0
    with tempfile.TemporaryDirectory(prefix="gfglock_speed_", dir=folder) as work:
        source = os.path.join(work, _TEST_NAME)
        _write_test_file(source, file_size)
        for round_index in range(ROUNDS):
            for size in sizes if round_index % 2 == 0 else list(reversed(sizes)):
                for step, run in enumerate((_encrypt, _decrypt)):
                    if is_cancelled():
                        raise ReadSizeTestCancelled()
                    best[size][step] = min(best[size][step], run(work, algorithm, size))
                    done += 1
                    on_step(done, total)
    return [SizeTiming(size, enc, dec) for size, (enc, dec) in best.items()]


def _write_test_file(path: str, size: int) -> None:
    """Write `size` bytes of random data, so compressed folders or disks can't skew the timing."""
    block = os.urandom(_FILL_BLOCK)
    with open(path, "wb") as fh:
        for offset in range(0, size, len(block)):
            fh.write(block[: min(len(block), size - offset)])


def _encrypt(work: str, algorithm: str, read_size: int) -> float:
    """Encrypt the test file in `work` and return the seconds it took."""
    started = time.perf_counter()
    result = file_ops.encrypt_file(os.path.join(work, _TEST_NAME), _PASSWORD, algorithm, False, read_size)
    elapsed = time.perf_counter() - started
    if result.outcome != "done":
        raise ReadSizeTestError(f"Encrypting the test file failed: {result.reason}")
    return elapsed


def _decrypt(work: str, algorithm: str, read_size: int) -> float:
    """Decrypt the encrypted test file in `work` back to the test file and return the seconds it took."""
    encrypted = os.path.join(work, _TEST_NAME + file_ops.EXTENSIONS[algorithm])
    started = time.perf_counter()
    result = file_ops.decrypt_file(encrypted, _PASSWORD, read_size)
    elapsed = time.perf_counter() - started
    if result.outcome != "done":
        raise ReadSizeTestError(f"Decrypting the test file failed: {result.reason}")
    return elapsed


class ReadSizeTestSignals(QObject):
    """Signals emitted while the read size test runs in the global thread pool."""

    progress = Signal(int, int)    # (steps done, total steps)
    finished = Signal(list, str)   # (list[SizeTiming], error message); both empty when stopped


class ReadSizeTestWorker(QRunnable):
    """Run time_read_sizes() off the GUI thread."""

    def __init__(self, sizes: list[int], algorithm: str) -> None:
        super().__init__()
        self.setAutoDelete(False)  # the controller keeps the worker so it can cancel it
        self.sizes = list(sizes)
        self.algorithm = algorithm
        self._cancel = threading.Event()
        self.signals = ReadSizeTestSignals()

    def cancel(self) -> None:
        """Stop before the next encrypt or decrypt step."""
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        """Time every size and report the result, an error message, or nothing when stopped."""
        timings: list[SizeTiming] = []
        error = ""
        try:
            timings = time_read_sizes(self.sizes, self.algorithm, is_cancelled=self._cancel.is_set,
                                      on_step=self.signals.progress.emit)
        except ReadSizeTestCancelled:
            pass
        except ReadSizeTestError as failure:
            error = str(failure)
        except OSError as failure:
            error = f"The test could not finish: {failure.strerror or failure}"
        try:
            self.signals.finished.emit(timings, error)
        except RuntimeError:
            pass  # the app is shutting down and the signal object is already gone


def pick_fastest(timings: list[SizeTiming], seconds: Callable[[SizeTiming], float],
                 default_bytes: int, margin: float = 0.05) -> int:
    """Return the fastest read size, or 0 (the default) unless it beats the default's size by `margin`.

    Differences of a few percent are within run-to-run variation, so they don't justify moving
    away from the default.
    """
    fastest = min(timings, key=seconds)
    baseline = next((t for t in timings if t.read_size == default_bytes), None)
    if baseline is None or seconds(fastest) < seconds(baseline) * (1 - margin):
        return fastest.read_size
    return 0
