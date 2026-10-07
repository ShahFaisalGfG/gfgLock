# file_model.py - QAbstractListModel backing the QML file list

import os
from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    Property,
    Qt,
    Signal,
    Slot,
)

from gfglock.utils.helpers import format_bytes

# What happened to a file so far. A run processes the waiting and failed rows.
STATUS_WAITING = "waiting"
STATUS_WORKING = "working"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
_FINISHED = (STATUS_DONE, STATUS_SKIPPED)
_RUNNABLE = (STATUS_WAITING, STATUS_FAILED)


class FileListModel(QAbstractListModel):
    """List model that exposes file metadata and each file's result to QML via named roles."""

    NameRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    SizeRole = Qt.ItemDataRole.UserRole + 3
    ExtRole = Qt.ItemDataRole.UserRole + 4
    SelectedRole = Qt.ItemDataRole.UserRole + 5
    FolderRole = Qt.ItemDataRole.UserRole + 6
    StatusRole = Qt.ItemDataRole.UserRole + 7
    ProgressRole = Qt.ItemDataRole.UserRole + 8
    MessageRole = Qt.ItemDataRole.UserRole + 9
    OutputRole = Qt.ItemDataRole.UserRole + 10

    _ROLE_KEYS = {
        NameRole: "name", PathRole: "path", SizeRole: "size", ExtRole: "ext",
        FolderRole: "folder", StatusRole: "status", ProgressRole: "progress",
        MessageRole: "message", OutputRole: "output",
    }

    countChanged = Signal(int)
    totalSizeChanged = Signal()
    selectionChanged = Signal()
    statusCountsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[dict] = []
        self._rows: dict[str, int] = {}     # normcase(path) -> row
        self._selected: set[int] = set()
        self._total_bytes: int = 0

    # ── QAbstractListModel interface ─────────────────────────────────────────

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._files)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if not index.isValid() or index.row() >= len(self._files):
            return None
        item = self._files[index.row()]
        if role == self.SelectedRole:
            return index.row() in self._selected
        if role == Qt.ItemDataRole.DisplayRole:
            return item["name"]
        key = self._ROLE_KEYS.get(role)
        return item[key] if key else None

    def roleNames(self) -> dict:
        names = {role: key.encode() for role, key in self._ROLE_KEYS.items()}
        names[self.SelectedRole] = b"selected"
        return names

    # ── Adding and removing ──────────────────────────────────────────────────

    @Slot(str)
    def addFile(self, path: str) -> None:
        """Add a file by path if not already in the list."""
        self.addFiles([path])

    @Slot(list)
    def addFiles(self, paths: list) -> int:
        """Add existing files in one model update, skipping duplicates; return how many were added."""
        additions = []
        pending: set[str] = set()
        for raw_path in paths:
            path = os.path.normpath(str(raw_path))
            key = os.path.normcase(path)
            if key in self._rows or key in pending or not os.path.isfile(path):
                continue
            additions.append(self._make_item(path))
            pending.add(key)
        self._insert_items(additions)
        return len(additions)

    @Slot(list)
    def addScanned(self, entries: list) -> None:
        """Insert (path, size) pairs from a folder scan without touching the filesystem."""
        additions = []
        pending: set[str] = set()
        for entry in entries:
            try:
                raw_path, size = entry
                path = os.path.normpath(str(raw_path))
                size = int(size)
            except (TypeError, ValueError):
                continue
            key = os.path.normcase(path)
            if key in self._rows or key in pending:
                continue
            additions.append(self._make_item(path, size))
            pending.add(key)
        self._insert_items(additions)

    def _insert_items(self, items: list[dict]) -> None:
        """Append prepared file rows and emit one contiguous model update."""
        if not items:
            return
        first = len(self._files)
        self.beginInsertRows(QModelIndex(), first, first + len(items) - 1)
        self._files.extend(items)
        for row, item in enumerate(items, start=first):
            self._rows[os.path.normcase(item["path"])] = row
        self._total_bytes += sum(item["bytes"] for item in items)
        self.endInsertRows()
        self._emit_counts()

    @Slot(int)
    def removeAt(self, row: int) -> None:
        """Remove the item at the given row index."""
        if not 0 <= row < len(self._files):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._files.pop(row)
        self._total_bytes -= removed["bytes"]
        self._selected = {i if i < row else i - 1 for i in self._selected if i != row}
        self._reindex()
        self.endRemoveRows()
        self._emit_counts()
        self.selectionChanged.emit()

    @Slot()
    def removeSelected(self) -> None:
        """Remove all currently selected items in one pass and one model reset.

        Removing row by row is quadratic (each pop shifts the list and each removal
        relayouts the view), which froze the window when removing thousands of rows.
        """
        if self._selected:
            self._keep(lambda row, _item: row not in self._selected)

    @Slot()
    def removeFinished(self) -> None:
        """Remove the rows that were encrypted, decrypted, or skipped, keeping the rest."""
        self._keep(lambda _row, item: item["status"] not in _FINISHED)

    @Slot()
    def clearAll(self) -> None:
        """Remove all items from the model."""
        self._keep(lambda _row, _item: False)

    def _keep(self, predicate) -> None:
        """Keep only the rows predicate(row, item) accepts, in one model reset."""
        kept = [item for row, item in enumerate(self._files) if predicate(row, item)]
        if len(kept) == len(self._files):
            return
        self.beginResetModel()
        self._files = kept
        self._total_bytes = sum(item["bytes"] for item in kept)
        self._selected.clear()
        self._reindex()
        self.endResetModel()
        self._emit_counts()
        self.selectionChanged.emit()

    # ── Results ──────────────────────────────────────────────────────────────

    def set_status(
        self,
        path: str,
        status: str,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        output: Optional[str] = None,
    ) -> None:
        """Record what is happening to one file; None leaves a field as it is."""
        row = self._rows.get(os.path.normcase(os.path.normpath(path)))
        if row is None:
            return
        item = self._files[row]
        changes: dict[str, Any] = {"status": status}
        if progress is not None:
            changes["progress"] = progress
        if message is not None:
            changes["message"] = message
        if output is not None:
            changes["output"] = output
        roles = [role for role, key in self._ROLE_KEYS.items() if key in changes and item[key] != changes[key]]
        if not roles:
            return
        status_changed = item["status"] != status
        item.update(changes)
        index = self.index(row)
        self.dataChanged.emit(index, index, roles)
        if status_changed:
            self.statusCountsChanged.emit()

    def set_progress(self, path: str, progress: float) -> None:
        """Update one working file's progress (0-1)."""
        row = self._rows.get(os.path.normcase(os.path.normpath(path)))
        if row is not None and self._files[row]["progress"] != progress:
            self._files[row]["progress"] = progress
            index = self.index(row)
            self.dataChanged.emit(index, index, [self.ProgressRole])

    def runnable_paths(self) -> list[str]:
        """Files the next run processes: those not finished yet, including ones that failed."""
        return [item["path"] for item in self._files if item["status"] in _RUNNABLE]

    def reset_for_run(self, paths: list[str]) -> None:
        """Mark the given files as waiting, clearing an earlier failure reason."""
        for path in paths:
            self.set_status(path, STATUS_WAITING, progress=0.0, message="")

    @Property(int, notify=statusCountsChanged)
    def runnableCount(self) -> int:
        """How many files the next run would process."""
        return sum(item["status"] in _RUNNABLE for item in self._files)

    @Property(int, notify=statusCountsChanged)
    def finishedCount(self) -> int:
        """How many files were encrypted, decrypted, or skipped."""
        return sum(item["status"] in _FINISHED for item in self._files)

    @Property(int, notify=statusCountsChanged)
    def failedCount(self) -> int:
        """How many files failed in the last run."""
        return sum(item["status"] == STATUS_FAILED for item in self._files)

    # ── Selection ────────────────────────────────────────────────────────────

    @Slot(int)
    def toggleSelection(self, row: int) -> None:
        """Toggle the selected state of a single item."""
        if 0 <= row < len(self._files):
            self._selected.symmetric_difference_update({row})
            index = self.index(row)
            self.dataChanged.emit(index, index, [self.SelectedRole])
            self.selectionChanged.emit()

    @Slot()
    def selectAll(self) -> None:
        """Select all items."""
        self._replace_selection(set(range(len(self._files))))

    @Slot()
    def clearSelection(self) -> None:
        """Deselect all items."""
        self._replace_selection(set())

    @Slot(int)
    def setSingle(self, row: int) -> None:
        """Deselect all items, then select only the given row."""
        if 0 <= row < len(self._files):
            self._replace_selection({row})

    @Slot(int, int)
    def selectRange(self, anchor: int, target: int) -> None:
        """Replace selection with all rows between anchor and target (inclusive)."""
        lo = max(0, min(anchor, target))
        hi = min(len(self._files) - 1, max(anchor, target))
        self._replace_selection(set(range(lo, hi + 1)))

    def _replace_selection(self, rows: set[int]) -> None:
        """Select exactly `rows`, repainting only the span that changed."""
        changed = self._selected.symmetric_difference(rows)
        self._selected = rows
        if changed:
            self.dataChanged.emit(self.index(min(changed)), self.index(max(changed)), [self.SelectedRole])
        self.selectionChanged.emit()

    @Slot(result=str)
    def getSelectedNamesText(self) -> str:
        """Return newline-separated file names for all selected items."""
        return "\n".join(self._files[i]["name"] for i in sorted(self._selected) if i < len(self._files))

    @Slot(result=str)
    def getSelectedPathsText(self) -> str:
        """Return newline-separated full paths for all selected items."""
        return "\n".join(self._files[i]["path"] for i in sorted(self._selected) if i < len(self._files))

    @Slot(int, result=str)
    def locationAt(self, row: int) -> str:
        """Where the row's file is now: the written file once done, else the original."""
        if not 0 <= row < len(self._files):
            return ""
        item = self._files[row]
        return item["output"] or item["path"]

    # ── Query API ────────────────────────────────────────────────────────────

    @Property(int, notify=countChanged)
    def count(self) -> int:
        """Total number of files - bindable QML property."""
        return len(self._files)

    @Property(str, notify=totalSizeChanged)
    def totalSize(self) -> str:
        """Formatted combined size of all files, cached at add time."""
        return format_bytes(float(self._total_bytes))

    @Property(int, notify=selectionChanged)
    def selectedCount(self) -> int:
        """Number of currently selected items - bindable QML property."""
        return len(self._selected)

    @Slot(result=list)
    def getPaths(self) -> list:
        """Return a list of all file paths in the model."""
        return [f["path"] for f in self._files]

    @Slot(result=int)
    def fileCount(self) -> int:
        """Return the total number of files."""
        return len(self._files)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _reindex(self) -> None:
        """Rebuild the path -> row index after rows were removed."""
        self._rows = {os.path.normcase(item["path"]): row for row, item in enumerate(self._files)}

    def _emit_counts(self) -> None:
        self.countChanged.emit(len(self._files))
        self.totalSizeChanged.emit()
        self.statusCountsChanged.emit()

    @staticmethod
    def _make_item(path: str, size_bytes: int | None = None) -> dict:
        """Build a file metadata dict for a path, using a known size when the caller has one."""
        if size_bytes is None:
            try:
                size_bytes = os.path.getsize(path)
            except OSError:
                size_bytes = -1
        size_str = format_bytes(float(size_bytes)) if size_bytes >= 0 else "?"
        name = os.path.basename(path)
        return {
            "name": name,
            "path": path,
            "folder": os.path.dirname(path),
            "size": size_str,
            "bytes": max(size_bytes, 0),
            "ext": os.path.splitext(name)[1].lstrip(".").upper() or "FILE",
            "status": STATUS_WAITING,
            "progress": 0.0,
            "message": "",
            "output": "",
        }
