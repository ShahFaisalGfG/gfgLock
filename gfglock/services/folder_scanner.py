"""Check and size the files and folders added to a list without blocking the GUI thread.

What a scan takes is decided in core/scan.py, shared with the command line. This worker runs it
off the GUI thread and hands rows to the model in batches sized by time (not by count), so a
folder with tens of thousands of files fills the list smoothly while the window keeps repainting.
Files and folders added while a scan runs join it. A scan can be cancelled at any time: Stop,
clearing the list, or app shutdown.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Iterable, Iterator

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core.scan import ScanReport, accepts, iter_files, protected_locations, scan_paths
from gfglock.utils.logging import write_log

__all__ = ["FolderScanSignals", "FolderScanWorker", "ScanReport", "iter_files", "protected_locations"]

# Rows are flushed to the GUI at most this often, or sooner once this many are waiting.
FLUSH_INTERVAL_S = 0.1
MAX_BATCH = 2000
_scan_ids = itertools.count(1)


class FolderScanSignals(QObject):
    """Signals of one scan; each carries the scan's id so the receiver can tell scans apart."""

    batch_found = Signal(int, list)  # (scan id, list of (path, size))
    finished = Signal(int, object)   # (scan id, ScanReport)


class FolderScanWorker(QRunnable):
    """Check the files and walk the folders added to one list, reporting the rows in batches."""

    def __init__(
        self,
        roots: Iterable[str],
        encrypted_extensions: frozenset[str],
        include_encrypted: bool,
    ) -> None:
        super().__init__()
        # Left to auto-delete: with that off, PySide's pool keeps a reference to every scan it ran.
        self.scan_id = next(_scan_ids)
        self.encrypted_extensions = encrypted_extensions
        self.include_encrypted = include_encrypted
        self._roots = list(roots)
        self._lock = threading.Lock()
        self._closed = False
        self._cancel = threading.Event()
        self.signals = FolderScanSignals()

    def add_roots(self, roots: Iterable[str]) -> bool:
        """Queue more files and folders for this scan; False once it has ended or was cancelled."""
        with self._lock:
            if self._closed or self._cancel.is_set():
                return False
            self._roots.extend(roots)
            return True

    def cancel(self) -> None:
        """Stop at the next directory entry and send no more batches."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        """True once cancel() has been called."""
        return self._cancel.is_set()

    def _accept(self, name: str) -> bool:
        """Keep encrypted files in decrypt mode and everything else in encrypt mode."""
        return accepts(name, self.include_encrypted, self.encrypted_extensions)

    @Slot()
    def run(self) -> None:
        """Scan the queued roots, including ones added meanwhile, then report once."""
        report = ScanReport()
        batch: list[tuple[str, int]] = []
        last_flush = time.monotonic()
        try:
            protected = None if self.include_encrypted else protected_locations()
            while not self._cancel.is_set():
                roots = self._take_roots()
                if not roots:
                    break
                for item in self._scan(roots, report, protected):
                    batch.append(item)
                    now = time.monotonic()
                    if len(batch) >= MAX_BATCH or now - last_flush >= FLUSH_INTERVAL_S:
                        self._flush(batch)
                        batch, last_flush = [], now
        except Exception as error:  # the scan must still end, or the list would stay "scanning"
            report.error = str(error)
            write_log(f"Folder scan stopped: {error}", "critical")
        finally:
            with self._lock:
                self._closed = True
            try:
                if batch:
                    self._flush(batch)
                self.signals.finished.emit(self.scan_id, report)
            except RuntimeError:
                pass  # the app is shutting down and the signal object is already gone

    def _take_roots(self) -> list[str]:
        """The roots queued so far. When none are left the scan closes, so later ones start a new scan."""
        with self._lock:
            roots, self._roots = self._roots, []
            self._closed = not roots
            return roots

    def _scan(self, roots: list[str], report: ScanReport,
              protected: frozenset[str] | None) -> Iterator[tuple[str, int]]:
        """Yield the rows for these files and folders, in the order they were added."""
        return scan_paths(roots, self.include_encrypted, report, protected, self._cancel.is_set,
                          self.encrypted_extensions)

    def _flush(self, batch: list[tuple[str, int]]) -> None:
        """Send one batch, unless the scan was cancelled."""
        if not self._cancel.is_set():
            self.signals.batch_found.emit(self.scan_id, batch)
