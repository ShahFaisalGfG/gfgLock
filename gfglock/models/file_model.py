# file_model.py - QAbstractListModel backing the QML file list

import os

from gfglock.utils.helpers import format_bytes
from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    Property,
    Qt,
    Signal,
    Slot,
)


class FileListModel(QAbstractListModel):
    """List model that exposes file metadata to QML via named roles."""

    NameRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    SizeRole = Qt.UserRole + 3
    ExtRole = Qt.UserRole + 4
    SelectedRole = Qt.UserRole + 5

    countChanged = Signal(int)
    totalSizeChanged = Signal()
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[dict] = []
        self._selected: set[int] = set()
        self._total_bytes: int = 0

    # ── QAbstractListModel interface ─────────────────────────────────────────

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._files)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._files):
            return None
        item = self._files[index.row()]
        if role == self.NameRole:
            return item["name"]
        if role == self.PathRole:
            return item["path"]
        if role == self.SizeRole:
            return item["size"]
        if role == self.ExtRole:
            return item["ext"]
        if role == self.SelectedRole:
            return index.row() in self._selected
        if role == Qt.DisplayRole:
            return item["name"]
        return None

    def roleNames(self) -> dict:
        return {
            self.NameRole: b"name",
            self.PathRole: b"path",
            self.SizeRole: b"size",
            self.ExtRole: b"ext",
            self.SelectedRole: b"selected",
        }

    # ── Mutation API ─────────────────────────────────────────────────────────

    @Slot(str)
    def addFile(self, path: str) -> None:
        """Add a file by path if not already in the list."""
        try:
            path = os.path.normpath(path)
            if any(f["path"] == path for f in self._files):
                return
            if not os.path.exists(path):
                return
            item = self._make_item(path)
            self.beginInsertRows(QModelIndex(), len(self._files), len(self._files))
            self._files.append(item)
            self._total_bytes += item["bytes"]
            self.endInsertRows()
            self.countChanged.emit(len(self._files))
            self.totalSizeChanged.emit()
        except Exception:
            pass

    @Slot(list)
    def addFiles(self, paths: list) -> None:
        """Add multiple files, skipping duplicates."""
        for path in paths:
            try:
                self.addFile(str(path))
            except Exception:
                pass

    @Slot(int)
    def removeAt(self, row: int) -> None:
        """Remove the item at the given row index."""
        try:
            if 0 <= row < len(self._files):
                self.beginRemoveRows(QModelIndex(), row, row)
                removed = self._files.pop(row)
                self._total_bytes -= removed["bytes"]
                self._selected.discard(row)
                self._selected = {i if i < row else i - 1 for i in self._selected if i != row}
                self.endRemoveRows()
                self.countChanged.emit(len(self._files))
                self.totalSizeChanged.emit()
                self.selectionChanged.emit()
        except Exception:
            pass

    @Slot()
    def removeSelected(self) -> None:
        """Remove all currently selected items."""
        try:
            rows = sorted(self._selected, reverse=True)
            for row in rows:
                if 0 <= row < len(self._files):
                    self.beginRemoveRows(QModelIndex(), row, row)
                    removed = self._files.pop(row)
                    self._total_bytes -= removed["bytes"]
                    self.endRemoveRows()
            self._selected.clear()
            self.countChanged.emit(len(self._files))
            self.totalSizeChanged.emit()
            self.selectionChanged.emit()
        except Exception:
            pass

    @Slot()
    def clearAll(self) -> None:
        """Remove all items from the model."""
        try:
            self.beginResetModel()
            self._files.clear()
            self._selected.clear()
            self._total_bytes = 0
            self.endResetModel()
            self.countChanged.emit(0)
            self.totalSizeChanged.emit()
            self.selectionChanged.emit()
        except Exception:
            pass

    @Slot(int)
    def toggleSelection(self, row: int) -> None:
        """Toggle the selected state of a single item."""
        try:
            if 0 <= row < len(self._files):
                if row in self._selected:
                    self._selected.discard(row)
                else:
                    self._selected.add(row)
                idx = self.index(row)
                self.dataChanged.emit(idx, idx, [self.SelectedRole])
                self.selectionChanged.emit()
        except Exception:
            pass

    @Slot()
    def selectAll(self) -> None:
        """Select all items."""
        try:
            self._selected = set(range(len(self._files)))
            if self._files:
                self.dataChanged.emit(
                    self.index(0), self.index(len(self._files) - 1), [self.SelectedRole]
                )
            self.selectionChanged.emit()
        except Exception:
            pass

    @Slot()
    def clearSelection(self) -> None:
        """Deselect all items."""
        try:
            if self._selected:
                self._selected.clear()
                if self._files:
                    self.dataChanged.emit(
                        self.index(0), self.index(len(self._files) - 1), [self.SelectedRole]
                    )
            self.selectionChanged.emit()
        except Exception:
            pass

    @Slot(int)
    def setSingle(self, row: int) -> None:
        """Deselect all items, then select only the given row."""
        try:
            if 0 <= row < len(self._files):
                old = self._selected.copy()
                self._selected = {row}
                changed = old.symmetric_difference(self._selected)
                if changed:
                    indices = sorted(changed)
                    self.dataChanged.emit(
                        self.index(indices[0]), self.index(indices[-1]), [self.SelectedRole]
                    )
                self.selectionChanged.emit()
        except Exception:
            pass

    @Slot(int, int)
    def selectRange(self, anchor: int, target: int) -> None:
        """Replace selection with all rows between anchor and target (inclusive)."""
        try:
            lo = max(0, min(anchor, target))
            hi = min(len(self._files) - 1, max(anchor, target))
            old = self._selected.copy()
            self._selected = set(range(lo, hi + 1))
            changed = old.symmetric_difference(self._selected)
            if changed:
                indices = sorted(changed)
                self.dataChanged.emit(
                    self.index(indices[0]), self.index(indices[-1]), [self.SelectedRole]
                )
            self.selectionChanged.emit()
        except Exception:
            pass

    @Slot(result=str)
    def getSelectedNamesText(self) -> str:
        """Return newline-separated file names for all selected items."""
        try:
            return "\n".join(
                self._files[i]["name"]
                for i in sorted(self._selected)
                if i < len(self._files)
            )
        except Exception:
            return ""

    @Slot(result=str)
    def getSelectedPathsText(self) -> str:
        """Return newline-separated full paths for all selected items."""
        try:
            return "\n".join(
                self._files[i]["path"]
                for i in sorted(self._selected)
                if i < len(self._files)
            )
        except Exception:
            return ""

    # ── Query API ────────────────────────────────────────────────────────────

    @Property(int, notify=countChanged)
    def count(self) -> int:
        """Total number of files - bindable QML property."""
        return len(self._files)

    @Property(str, notify=totalSizeChanged)
    def totalSize(self) -> str:
        """Formatted combined size of all files, cached at add time."""
        try:
            return format_bytes(float(self._total_bytes))
        except Exception:
            return "0 B"

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

    @staticmethod
    def _make_item(path: str) -> dict:
        """Build a file metadata dict for a given path."""
        try:
            size_bytes = os.path.getsize(path)
            size_str = format_bytes(float(size_bytes))
        except Exception:
            size_bytes = 0
            size_str = "?"
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lstrip(".").upper() or "FILE"
        return {"name": name, "path": path, "size": size_str, "bytes": size_bytes, "ext": ext}
