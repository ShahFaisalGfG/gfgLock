"""Scan folders and prepare file rows away from the GUI thread."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.models.file_model import FileListModel


class FolderScanSignals(QObject):
    """Signals emitted while a folder scan runs in the global thread pool."""

    items_found = Signal(list)
    error = Signal(str)
    finished = Signal(int)


class FolderScanWorker(QRunnable):
    """Walk one folder and emit ready-to-insert file metadata in small batches."""

    BATCH_SIZE = 256

    def __init__(
        self,
        folder: str,
        scan_id: int,
        encrypted_extensions: frozenset[str],
        include_encrypted: bool,
    ) -> None:
        super().__init__()
        self.folder = folder
        self.scan_id = scan_id
        self.encrypted_extensions = encrypted_extensions
        self.include_encrypted = include_encrypted
        self.signals = FolderScanSignals()

    @Slot()
    def run(self) -> None:
        """Scan the folder and emit metadata batches, reporting traversal errors."""
        batch: list[dict] = []
        try:
            for root, _, filenames in os.walk(self.folder, onerror=self._report_error):
                for filename in filenames:
                    path = os.path.join(root, filename)
                    is_encrypted = os.path.splitext(filename)[1].lower() in self.encrypted_extensions
                    if is_encrypted != self.include_encrypted or not os.path.isfile(path):
                        continue

                    batch.append(FileListModel._make_item(path))
                    if len(batch) >= self.BATCH_SIZE:
                        self.signals.items_found.emit(batch)
                        batch = []
        except Exception as error:
            self.signals.error.emit(f"Could not finish scanning {self.folder}: {error}")
        finally:
            if batch:
                self.signals.items_found.emit(batch)
            self.signals.finished.emit(self.scan_id)

    def _report_error(self, error: OSError) -> None:
        """Forward directory traversal errors to the controller."""
        self.signals.error.emit(str(error))
