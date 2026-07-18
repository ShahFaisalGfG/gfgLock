# test_file_model.py - unit tests for gfglock.models.file_model

import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from gfglock.models.file_model import FileListModel


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


def _raise(*_args, **_kwargs):
    """Stand-in for a monkeypatched call that must fail."""
    raise OSError("simulated failure")


@pytest.fixture
def model():
    """A fresh, empty FileListModel."""
    return FileListModel()


def _populate(model: FileListModel, tmp_path, names: list) -> None:
    """Create real files under tmp_path (sized by name length) and add them."""
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"x" * len(name))
        model.addFile(str(path))


class TestAddFile:
    """addFile() must add existing files once, skip duplicates/missing paths, and emit signals."""

    def test_adds_new_existing_file(self, model, tmp_path):
        """A brand-new existing path must be appended with correct metadata."""
        f = tmp_path / "report.TXT"
        f.write_bytes(b"hello")
        count_spy = MagicMock()
        size_spy = MagicMock()
        model.countChanged.connect(count_spy)
        model.totalSizeChanged.connect(size_spy)

        model.addFile(str(f))

        assert model.rowCount() == 1
        idx = model.index(0)
        assert model.data(idx, FileListModel.NameRole) == "report.TXT"
        assert model.data(idx, FileListModel.PathRole) == os.path.normpath(str(f))
        assert model.data(idx, FileListModel.ExtRole) == "TXT"
        assert model.data(idx, FileListModel.SelectedRole) is False
        count_spy.assert_called_once_with(1)
        size_spy.assert_called_once()

    def test_duplicate_path_ignored(self, model, tmp_path):
        """Adding the same path twice must not create a second row or re-emit."""
        f = tmp_path / "a.txt"
        f.write_bytes(b"x")
        model.addFile(str(f))
        count_spy = MagicMock()
        model.countChanged.connect(count_spy)
        model.addFile(str(f))
        assert model.rowCount() == 1
        count_spy.assert_not_called()

    def test_missing_path_ignored(self, model, tmp_path):
        """A path that doesn't exist on disk must not be added."""
        model.addFile(str(tmp_path / "ghost.txt"))
        assert model.rowCount() == 0

    def test_extensionless_file_gets_file_ext(self, model, tmp_path):
        """A file without an extension must be tagged with ext 'FILE'."""
        f = tmp_path / "README"
        f.write_bytes(b"x")
        model.addFile(str(f))
        assert model.data(model.index(0), FileListModel.ExtRole) == "FILE"

    def test_getsize_failure_falls_back_to_unknown_size(self, model, tmp_path, monkeypatch):
        """A getsize() failure must still add the item with a placeholder size."""
        f = tmp_path / "locked.bin"
        f.write_bytes(b"x")
        monkeypatch.setattr(os.path, "getsize", _raise)
        model.addFile(str(f))
        assert model.rowCount() == 1
        assert model.data(model.index(0), FileListModel.SizeRole) == "?"


class TestAddFiles:
    """addFiles() must add every valid path while skipping invalid ones."""

    def test_adds_multiple_skips_missing(self, model, tmp_path):
        """A mix of existing and missing paths must only add the existing ones."""
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"1")
        b.write_bytes(b"22")
        model.addFiles([str(a), str(tmp_path / "missing.txt"), str(b)])
        assert model.rowCount() == 2
        assert model.getPaths() == [os.path.normpath(str(a)), os.path.normpath(str(b))]


class TestRemoveAt:
    """removeAt() must remove a single row, keep totals accurate, and re-index selection."""

    def test_removes_row_and_updates_totals(self, model, tmp_path):
        """Removing a row must shrink the count and total size accordingly."""
        _populate(model, tmp_path, ["a.txt", "bb.txt", "ccc.txt"])
        count_spy = MagicMock()
        size_spy = MagicMock()
        model.countChanged.connect(count_spy)
        model.totalSizeChanged.connect(size_spy)

        model.removeAt(1)

        assert model.rowCount() == 2
        assert model.getPaths() == [
            os.path.normpath(str(tmp_path / "a.txt")),
            os.path.normpath(str(tmp_path / "ccc.txt")),
        ]
        count_spy.assert_called_once_with(2)
        size_spy.assert_called_once()

    def test_reindexes_selection_after_removal(self, model, tmp_path):
        """Selected rows after the removed index must shift down by one."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.toggleSelection(2)
        model.removeAt(0)
        assert model.data(model.index(1), FileListModel.SelectedRole) is True

    def test_out_of_range_row_is_noop(self, model, tmp_path):
        """An out-of-bounds row index must be ignored."""
        _populate(model, tmp_path, ["a.txt"])
        model.removeAt(5)
        model.removeAt(-1)
        assert model.rowCount() == 1


class TestRemoveSelected:
    """removeSelected() must remove every selected row and clear the selection."""

    def test_removes_selected_rows_only(self, model, tmp_path):
        """Only rows marked selected must be removed; others survive untouched."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.toggleSelection(0)
        model.toggleSelection(2)

        model.removeSelected()

        assert model.rowCount() == 1
        assert model.getPaths() == [os.path.normpath(str(tmp_path / "b.txt"))]
        assert model.selectedCount == 0


class TestClearAll:
    """clearAll() must reset the model to empty and clear selection/total size."""

    def test_clears_everything(self, model, tmp_path):
        """After clearAll(), count/totalSize/selection must all reset."""
        f = tmp_path / "a.txt"
        f.write_bytes(b"x")
        model.addFile(str(f))
        model.toggleSelection(0)
        count_spy = MagicMock()
        model.countChanged.connect(count_spy)

        model.clearAll()

        assert model.rowCount() == 0
        assert model.selectedCount == 0
        assert model.totalSize == "0.0 B"
        count_spy.assert_called_once_with(0)


class TestSelectionSlots:
    """toggleSelection()/selectAll()/clearSelection()/setSingle()/selectRange() track selection."""

    def test_toggle_selection_flips_state_and_emits(self, model, tmp_path):
        """Toggling a row must flip its selected flag and emit selectionChanged."""
        _populate(model, tmp_path, ["a.txt", "b.txt"])
        spy = MagicMock()
        model.selectionChanged.connect(spy)

        model.toggleSelection(0)
        assert model.data(model.index(0), FileListModel.SelectedRole) is True
        model.toggleSelection(0)
        assert model.data(model.index(0), FileListModel.SelectedRole) is False
        assert spy.call_count == 2

    def test_select_all_selects_every_row(self, model, tmp_path):
        """selectAll() must mark every row selected."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.selectAll()
        assert model.selectedCount == 3

    def test_select_all_on_empty_model_still_emits(self, model):
        """selectAll() on an empty model must still emit selectionChanged."""
        spy = MagicMock()
        model.selectionChanged.connect(spy)
        model.selectAll()
        spy.assert_called_once()

    def test_clear_selection_deselects_all(self, model, tmp_path):
        """clearSelection() must deselect every previously selected row."""
        _populate(model, tmp_path, ["a.txt", "b.txt"])
        model.selectAll()
        model.clearSelection()
        assert model.selectedCount == 0

    def test_clear_selection_noop_still_emits(self, model, tmp_path):
        """clearSelection() with nothing selected must still emit selectionChanged."""
        _populate(model, tmp_path, ["a.txt"])
        spy = MagicMock()
        model.selectionChanged.connect(spy)
        model.clearSelection()
        spy.assert_called_once()

    def test_set_single_selects_only_one_row(self, model, tmp_path):
        """setSingle() must replace the whole selection with a single row."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.selectAll()
        model.setSingle(1)
        assert model.selectedCount == 1
        assert model.data(model.index(1), FileListModel.SelectedRole) is True

    def test_set_single_out_of_range_is_noop(self, model, tmp_path):
        """An out-of-range row must leave selection state and signals untouched."""
        _populate(model, tmp_path, ["a.txt"])
        spy = MagicMock()
        model.selectionChanged.connect(spy)
        model.setSingle(9)
        spy.assert_not_called()

    def test_select_range_selects_inclusive_span(self, model, tmp_path):
        """selectRange() must select every row between anchor and target inclusively."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt", "d.txt", "e.txt"])
        model.selectRange(1, 3)
        assert model.selectedCount == 3
        for row in (1, 2, 3):
            assert model.data(model.index(row), FileListModel.SelectedRole) is True

    def test_select_range_handles_reversed_bounds(self, model, tmp_path):
        """selectRange() must work the same whether anchor or target is larger."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt", "d.txt", "e.txt"])
        model.selectRange(3, 1)
        assert model.selectedCount == 3

    def test_select_range_clamps_to_bounds(self, model, tmp_path):
        """selectRange() must clamp an out-of-bounds target to the last row."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.selectRange(0, 99)
        assert model.selectedCount == 3


class TestSelectedTextExport:
    """getSelectedNamesText()/getSelectedPathsText() must join selected entries in row order."""

    def test_names_text_sorted_by_row(self, model, tmp_path):
        """Selecting out of order must still produce names sorted by row index."""
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.toggleSelection(2)
        model.toggleSelection(0)
        assert model.getSelectedNamesText() == "a.txt\nc.txt"

    def test_paths_text_matches_selection(self, model, tmp_path):
        """getSelectedPathsText() must return full paths for selected rows only."""
        _populate(model, tmp_path, ["a.txt", "b.txt"])
        model.toggleSelection(1)
        assert model.getSelectedPathsText() == os.path.normpath(str(tmp_path / "b.txt"))

    def test_empty_selection_returns_empty_string(self, model, tmp_path):
        """No selection must produce an empty string, not an error."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.getSelectedNamesText() == ""
        assert model.getSelectedPathsText() == ""


class TestQueryProperties:
    """count/totalSize/selectedCount/getPaths()/fileCount() must reflect model state."""

    def test_count_and_file_count_match_rows(self, model, tmp_path):
        """count property and fileCount() slot must agree with rowCount()."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.count == 1
        assert model.fileCount() == 1

    def test_total_size_formats_bytes(self, model, tmp_path):
        """totalSize must be the human-readable sum of all added files."""
        f = tmp_path / "a.bin"
        f.write_bytes(b"x" * 2048)
        model.addFile(str(f))
        assert model.totalSize == "2.0 KB"

    def test_total_size_empty_model(self, model):
        """An empty model must report a zero-byte total."""
        assert model.totalSize == "0.0 B"

    def test_selected_count_matches_selection(self, model, tmp_path):
        """selectedCount must track the number of currently selected rows."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.selectedCount == 0
        model.toggleSelection(0)
        assert model.selectedCount == 1

    def test_get_paths_returns_insertion_order(self, model, tmp_path):
        """getPaths() must return paths in the order files were added."""
        names = ["b.txt", "a.txt", "c.txt"]
        _populate(model, tmp_path, names)
        assert model.getPaths() == [os.path.normpath(str(tmp_path / n)) for n in names]


class TestModelInterface:
    """data()/roleNames() must satisfy QAbstractListModel's contract."""

    def test_invalid_index_returns_none(self, model, tmp_path):
        """An invalid QModelIndex must yield None for any role."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.data(QModelIndex(), FileListModel.NameRole) is None

    def test_out_of_range_row_returns_none(self, model):
        """A row beyond the current size must yield None."""
        assert model.data(model.index(0), FileListModel.NameRole) is None

    def test_display_role_returns_name(self, model, tmp_path):
        """Qt.DisplayRole must fall back to the file name, like NameRole."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.data(model.index(0), Qt.ItemDataRole.DisplayRole) == "a.txt"

    def test_role_names_mapping(self, model):
        """roleNames() must expose exactly the five documented byte-string roles."""
        assert model.roleNames() == {
            FileListModel.NameRole: b"name",
            FileListModel.PathRole: b"path",
            FileListModel.SizeRole: b"size",
            FileListModel.ExtRole: b"ext",
            FileListModel.SelectedRole: b"selected",
        }


class TestMakeItem:
    """_make_item() must build a well-formed metadata dict for a given path."""

    def test_builds_expected_fields(self, tmp_path):
        """A normal file must produce name/path/size/ext/bytes fields."""
        f = tmp_path / "doc.PDF"
        f.write_bytes(b"x" * 10)
        item = FileListModel._make_item(str(f))
        assert item["name"] == "doc.PDF"
        assert item["path"] == str(f)
        assert item["ext"] == "PDF"
        assert item["bytes"] == 10
        assert item["size"] == "10.0 B"
