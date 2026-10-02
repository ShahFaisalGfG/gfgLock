"""Scan folders for files to encrypt or decrypt without blocking the GUI thread.

The walk uses os.scandir, whose directory entries already carry file type and size on Windows,
so no extra stat call is made per file. Rows are handed to the model in batches sized by time
(not by count), so a folder with tens of thousands of files fills the list smoothly while the
window keeps repainting. A scan can be cancelled at any time: new scan, mode change, clearing
the list, or app shutdown.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable, Iterator

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

# Rows are flushed to the GUI at most this often, or sooner once this many are waiting.
FLUSH_INTERVAL_S = 0.1
MAX_BATCH = 2000


def iter_files(
    roots: Iterable[str],
    accept: Callable[[str], bool],
    is_cancelled: Callable[[], bool] = lambda: False,
    on_error: Callable[[str], None] | None = None,
) -> Iterator[tuple[str, int]]:
    """Yield (path, size_bytes) for every file under `roots` whose name passes `accept`.

    Directories are walked depth-first in case-insensitive name order, so files arrive in the
    order Explorer lists them. Symlinked directories are not followed (avoids loops), and
    unreadable directories are reported through `on_error` and skipped.
    """
    stack = list(reversed([os.path.normpath(r) for r in roots]))
    while stack:
        if is_cancelled():
            return
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                listing = sorted(entries, key=lambda e: e.name.casefold())
        except OSError as error:
            if on_error:
                on_error(f"Skipped {folder}: {error.strerror or error}")
            continue
        subfolders: list[str] = []
        for entry in listing:
            if is_cancelled():
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    subfolders.append(entry.path)
                elif accept(entry.name) and entry.is_file():
                    yield entry.path, entry.stat().st_size
            except OSError:
                continue
        stack.extend(reversed(subfolders))


class FolderScanSignals(QObject):
    """Signals emitted while a folder scan runs in the global thread pool."""

    batch_found = Signal(list)       # list[tuple[str, int]] of (path, size)
    progress = Signal(int)           # files found so far
    error = Signal(str)
    finished = Signal(int, bool)     # (files found, cancelled)


class FolderScanWorker(QRunnable):
    """Walk one or more folders and report files allowed for the current mode, in batches."""

    def __init__(
        self,
        roots: list[str],
        encrypted_extensions: frozenset[str],
        include_encrypted: bool,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)  # the controller keeps the worker so it can cancel it
        self.roots = list(roots)
        self.encrypted_extensions = encrypted_extensions
        self.include_encrypted = include_encrypted
        self._cancel = threading.Event()
        self.signals = FolderScanSignals()

    def cancel(self) -> None:
        """Stop at the next directory entry; batches already sent stay delivered."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        """True once cancel() has been called."""
        return self._cancel.is_set()

    def _accept(self, name: str) -> bool:
        """Keep encrypted files in decrypt mode and everything else in encrypt mode."""
        is_encrypted = os.path.splitext(name)[1].lower() in self.encrypted_extensions
        return is_encrypted == self.include_encrypted

    @Slot()
    def run(self) -> None:
        """Scan the roots, flushing batches on a time budget, then report completion."""
        found = 0
        batch: list[tuple[str, int]] = []
        last_flush = time.monotonic()
        try:
            for item in iter_files(self.roots, self._accept, self._cancel.is_set, self.signals.error.emit):
                batch.append(item)
                found += 1
                now = time.monotonic()
                if len(batch) >= MAX_BATCH or now - last_flush >= FLUSH_INTERVAL_S:
                    self._flush(batch, found)
                    batch, last_flush = [], now
        except Exception as error:
            self.signals.error.emit(f"Could not finish scanning: {error}")
        finally:
            try:
                if batch:
                    self._flush(batch, found)
                self.signals.finished.emit(found, self._cancel.is_set())
            except RuntimeError:
                pass  # the app is shutting down and the signal object is already gone

    def _flush(self, batch: list[tuple[str, int]], found: int) -> None:
        """Send one batch and the running total, unless the scan was cancelled."""
        if self._cancel.is_set():
            return
        self.signals.batch_found.emit(batch)
        self.signals.progress.emit(found)
