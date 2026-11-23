# worker.py - runs one batch (core/batch.py) off the GUI thread and reports it with Qt signals

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core.batch import BatchRun, RunListener, RunOptions
from gfglock.core.file_ops import FileResult
from gfglock.core.format_v2 import KeyRing


class WorkerSignals(QObject):
    """What a run reports; the controller receives every signal queued, on the GUI thread."""

    # progress: (bytes read so far, total bytes of the run's files, seconds left or -1), at most every
    # PROGRESS_INTERVAL_S and once when the last file has ended
    progress = Signal(float, float, float)
    # file_started: path, when a file begins
    file_started = Signal(str)
    # file_progress: (path, fraction 0-1) while a file is under way, at most once per whole percent
    file_progress = Signal(str, float)
    # file_result: (path, outcome, category, reason, output_path), once per file
    file_result = Signal(str, str, str, str, str)
    # temps_removed: how many temp files left by an interrupted run were deleted at the start
    temps_removed = Signal(int)
    # finished: the run's RunResult, whose error says why a run stopped early
    finished = Signal(object)


class _SignalListener(RunListener):
    """Passes a run's reports on as signals."""

    def __init__(self, signals: WorkerSignals) -> None:
        self._signals = signals

    def progress(self, done: int, total: int, eta: float) -> None:
        self._signals.progress.emit(float(done), float(total), float(eta))

    def file_started(self, path: str) -> None:
        self._signals.file_started.emit(path)

    def file_progress(self, path: str, fraction: float) -> None:
        self._signals.file_progress.emit(path, fraction)

    def file_result(self, path: str, result: FileResult) -> None:
        self._signals.file_result.emit(path, result.outcome, result.category, result.reason, result.output)

    def temps_removed(self, count: int) -> None:
        self._signals.temps_removed.emit(count)


class EncryptDecryptWorker(QRunnable):
    """Encrypt, decrypt, or check a list of files on the thread pool, reporting through `signals`."""

    def __init__(self, paths: Iterable[str], keys: KeyRing, options: RunOptions) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self.batch = BatchRun(paths, keys, options, _SignalListener(self.signals))

    @Slot()
    def cancel(self) -> None:
        """Stop the run: no new files start, and the files in progress stop and stay unchanged."""
        self.batch.cancel()

    def run(self) -> None:
        """Run the batch, then report how it ended."""
        self.signals.finished.emit(self.batch.run())
