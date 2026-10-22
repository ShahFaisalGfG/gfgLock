# test_file_model.py - unit tests for gfglock.models.file_model

import os
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from gfglock.models.file_model import COUNTS_INTERVAL_MS, FileListModel


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - shared app type across test files since
    encrypt_ctrl needs QtWidgets for clipboard access, so whichever file
    runs first must not leave a bare QCoreApplication singleton behind."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def model():
    """A fresh, empty FileListModel."""
    return FileListModel()


def _path(tmp_path, name: str) -> str:
    return os.path.normpath(str(tmp_path / name))


def _populate(model: FileListModel, tmp_path, names: list) -> None:
    """Add one row per name (sized by name length), as a folder scan would."""
    model.add_scanned([(_path(tmp_path, name), len(name)) for name in names])


def _paths(model: FileListModel) -> list:
    return [model.data(model.index(row), FileListModel.PathRole) for row in range(model.rowCount())]


def _counts(model: FileListModel) -> tuple:
    """(runnable, finished, failed) as QML reads them."""
    return model.runnableCount, model.finishedCount, model.failedCount


def _brute_counts(model: FileListModel) -> tuple[int, int, int]:
    """The same counts recomputed from the rows."""
    statuses = [model.data(model.index(row), FileListModel.StatusRole) for row in range(model.rowCount())]
    return (sum(s in ("waiting", "failed") for s in statuses), sum(s in ("done", "skipped") for s in statuses),
            statuses.count("failed"))


def _settle(model: FileListModel) -> None:
    """Run the event loop until the coalesced statusCountsChanged has gone out."""
    deadline = time.monotonic() + COUNTS_INTERVAL_MS * 20 / 1000
    while model._counts_timer.isActive() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.005)
    QCoreApplication.processEvents()
    assert not model._counts_timer.isActive(), "statusCountsChanged never went out"


class TestAddScanned:
    """add_scanned() adds rows once, with the sizes the scan measured, and emits one update."""

    def test_adds_rows_with_metadata(self, model, tmp_path):
        count_spy = MagicMock()
        size_spy = MagicMock()
        model.countChanged.connect(count_spy)
        model.totalSizeChanged.connect(size_spy)

        assert model.add_scanned([(str(tmp_path / "report.TXT"), 5)]) == 1

        assert model.rowCount() == 1
        idx = model.index(0)
        assert model.data(idx, FileListModel.NameRole) == "report.TXT"
        assert model.data(idx, FileListModel.PathRole) == _path(tmp_path, "report.TXT")
        assert model.data(idx, FileListModel.ExtRole) == "TXT"
        assert model.data(idx, FileListModel.SelectedRole) is False
        count_spy.assert_called_once_with(1)
        size_spy.assert_called_once()

    def test_dedupes_in_one_insert(self, model, tmp_path):
        inserts = []
        model.rowsInserted.connect(lambda *args: inserts.append(args))
        path = str(tmp_path / "a.txt")
        assert model.add_scanned([(path, 10), (path.upper(), 10), (str(tmp_path / "b.txt"), 20)]) == 2
        assert model.count == 2 and len(inserts) == 1
        assert model.totalSize == "30 B"

    def test_already_listed_paths_are_skipped_without_signals(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        count_spy = MagicMock()
        model.countChanged.connect(count_spy)
        assert model.add_scanned([(str(tmp_path / "a.txt"), 5)]) == 0
        assert model.rowCount() == 1
        count_spy.assert_not_called()

    def test_malformed_entries_are_ignored(self, model, tmp_path):
        assert model.add_scanned([("only-a-path",), (str(tmp_path / "ok.txt"), "not a size"),
                                  (str(tmp_path / "b.txt"), 3)]) == 1

    def test_extensionless_file_gets_file_ext(self, model, tmp_path):
        """A file without an extension must be tagged with ext 'FILE'."""
        _populate(model, tmp_path, ["README"])
        assert model.data(model.index(0), FileListModel.ExtRole) == "FILE"


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
        assert _paths(model) == [_path(tmp_path, "a.txt"), _path(tmp_path, "ccc.txt")]
        assert model.totalSize == "12 B"
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

        assert _paths(model) == [_path(tmp_path, "b.txt")]
        assert model.selectedCount == 0

    def test_remove_thousands_selected_is_fast(self, model, tmp_path):
        model.add_scanned([(str(tmp_path / f"{i}.txt"), 1) for i in range(5000)])
        model.selectAll()
        start = time.perf_counter()
        model.removeSelected()
        assert model.count == 0
        assert time.perf_counter() - start < 1.0


class TestClearAll:
    """clearAll() must reset the model to empty and clear selection/total size."""

    def test_clears_everything(self, model, tmp_path):
        """After clearAll(), count/totalSize/selection must all reset."""
        _populate(model, tmp_path, ["a.txt"])
        model.toggleSelection(0)
        count_spy = MagicMock()
        model.countChanged.connect(count_spy)

        model.clearAll()

        assert model.rowCount() == 0
        assert model.selectedCount == 0
        assert model.totalSize == "0 B"
        assert _counts(model) == (0, 0, 0)
        count_spy.assert_called_once_with(0)


class TestSelectionSlots:
    """toggleSelection()/selectAll()/setSingle()/selectRange() track selection."""

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
        assert model.getSelectedPathsText() == _path(tmp_path, "b.txt")

    def test_empty_selection_returns_empty_string(self, model, tmp_path):
        """No selection must produce an empty string, not an error."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.getSelectedNamesText() == ""
        assert model.getSelectedPathsText() == ""


class TestQueryProperties:
    """count/totalSize/selectedCount must reflect model state."""

    def test_count_matches_rows(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        assert model.count == model.rowCount() == 1

    @pytest.mark.parametrize("size,text", [(400, "400 B"), (2048, "2 KB"), (1536, "1.5 KB"), (0, "0 B")])
    def test_sizes_have_no_trailing_zero(self, model, tmp_path, size, text):
        """Sizes read '400 B' and '2 KB', not '400.0 B' (U24)."""
        model.add_scanned([(str(tmp_path / "a.bin"), size)])
        assert model.data(model.index(0), FileListModel.SizeRole) == text
        assert model.totalSize == text

    def test_total_size_empty_model(self, model):
        """An empty model must report a zero-byte total."""
        assert model.totalSize == "0 B"

    def test_selected_count_matches_selection(self, model, tmp_path):
        """selectedCount must track the number of currently selected rows."""
        _populate(model, tmp_path, ["a.txt"])
        assert model.selectedCount == 0
        model.toggleSelection(0)
        assert model.selectedCount == 1

    def test_rows_keep_insertion_order(self, model, tmp_path):
        names = ["b.txt", "a.txt", "c.txt"]
        _populate(model, tmp_path, names)
        assert _paths(model) == [_path(tmp_path, n) for n in names]


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
        """roleNames() must expose every documented byte-string role."""
        assert model.roleNames() == {
            FileListModel.NameRole: b"name",
            FileListModel.PathRole: b"path",
            FileListModel.SizeRole: b"size",
            FileListModel.ExtRole: b"ext",
            FileListModel.SelectedRole: b"selected",
            FileListModel.FolderRole: b"folder",
            FileListModel.StatusRole: b"status",
            FileListModel.ProgressRole: b"progress",
            FileListModel.MessageRole: b"message",
            FileListModel.OutputRole: b"output",
        }


class TestMakeItem:
    """_make_item() must build a well-formed metadata dict for a given path."""

    def test_builds_expected_fields(self, tmp_path):
        """A normal file must produce name/path/size/ext/bytes fields."""
        path = str(tmp_path / "doc.PDF")
        item = FileListModel._make_item(path, 10)
        assert item["name"] == "doc.PDF"
        assert item["path"] == path
        assert item["folder"] == str(tmp_path)
        assert item["ext"] == "PDF"
        assert item["bytes"] == 10
        assert item["size"] == "10 B"
        assert (item["status"], item["progress"], item["message"], item["output"]) == ("waiting", 0.0, "", "")


class TestResults:
    """Each row carries its result, and a run only picks up the rows that aren't finished."""

    def _status(self, model, row):
        return model.data(model.index(row), FileListModel.StatusRole)

    def test_new_rows_wait_and_are_runnable(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt", "b.txt"])
        assert [self._status(model, r) for r in range(2)] == ["waiting", "waiting"]
        assert model.runnableCount == 2 and model.finishedCount == 0

    def test_set_status_updates_roles_and_counts(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        changes = []
        model.statusCountsChanged.connect(lambda: changes.append(True))
        model.set_status(str(tmp_path / "a.txt"), "done", progress=1.0, message="Saved as a.txt.gfglock",
                         output=str(tmp_path / "a.txt.gfglock"))
        model.set_status(str(tmp_path / "b.txt"), "failed", message="Wrong password")
        model.set_status(str(tmp_path / "c.txt"), "skipped", message="Already encrypted")
        assert model.data(model.index(0), FileListModel.MessageRole) == "Saved as a.txt.gfglock"
        assert _counts(model) == (1, 2, 1)
        assert model.runnable_paths() == [_path(tmp_path, "b.txt")]
        _settle(model)
        assert changes == [True]

    def test_unknown_path_is_ignored(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        model.set_status(str(tmp_path / "other.txt"), "done")
        assert self._status(model, 0) == "waiting"
        assert _counts(model) == (1, 0, 0)

    def test_reset_for_run_clears_an_earlier_failure(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        path = str(tmp_path / "a.txt")
        model.set_status(path, "failed", message="Wrong password")
        model.reset_for_run([path])
        assert self._status(model, 0) == "waiting"
        assert model.data(model.index(0), FileListModel.MessageRole) == ""
        assert _counts(model) == (1, 0, 0)

    def test_progress_updates_only_the_progress_role(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        roles = []
        model.dataChanged.connect(lambda _a, _b, r: roles.append(list(r)))
        model.set_progress(str(tmp_path / "a.txt"), 0.5)
        assert model.data(model.index(0), FileListModel.ProgressRole) == 0.5
        assert roles == [[FileListModel.ProgressRole]]

    def test_remove_finished_keeps_waiting_and_failed(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt", "b.txt", "c.txt"])
        model.set_status(str(tmp_path / "a.txt"), "done")
        model.set_status(str(tmp_path / "b.txt"), "failed")
        model.removeFinished()
        assert [os.path.basename(p) for p in _paths(model)] == ["b.txt", "c.txt"]
        # Status updates still find the right rows after removal.
        model.set_status(str(tmp_path / "c.txt"), "done")
        assert self._status(model, 1) == "done"

    def test_location_is_the_written_file_once_done(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        assert model.locationAt(0) == _path(tmp_path, "a.txt")
        model.set_status(str(tmp_path / "a.txt"), "done", output=str(tmp_path / "a.txt.gfglock"))
        assert model.locationAt(0) == str(tmp_path / "a.txt.gfglock")
        assert model.locationAt(5) == ""


class TestIncrementalCounts:
    """The status counts are kept as rows change, never recounted on read (A5)."""

    def test_counts_follow_every_kind_of_change(self, model, tmp_path):
        names = [f"f{i}.txt" for i in range(10)]
        _populate(model, tmp_path, names)
        for i, status in enumerate(["working", "done", "failed", "skipped", "done", "failed"]):
            model.set_status(str(tmp_path / names[i]), status)
        assert _counts(model) == _brute_counts(model) == (6, 3, 2)
        model.removeAt(1)                       # a done row
        assert _counts(model) == _brute_counts(model) == (6, 2, 2)
        model.toggleSelection(1)                # f2.txt, failed
        model.removeSelected()
        assert _counts(model) == _brute_counts(model) == (5, 2, 1)
        model.removeFinished()
        assert _counts(model) == _brute_counts(model) == (5, 0, 1)
        model.reset_for_run(model.runnable_paths())
        assert _counts(model) == _brute_counts(model) == (5, 0, 0)
        _populate(model, tmp_path, ["new.txt"])
        assert _counts(model) == _brute_counts(model) == (6, 0, 0)
        model.clearAll()
        assert _counts(model) == (0, 0, 0)

    def test_reading_counts_does_not_walk_the_rows(self, model, tmp_path):
        model.add_scanned([(str(tmp_path / f"{i}.txt"), 1) for i in range(20_000)])
        start = time.perf_counter()
        for _ in range(10_000):
            _counts(model)
        assert time.perf_counter() - start < 0.5

    def test_status_changes_of_20000_rows_send_few_signals(self, model, tmp_path):
        model.add_scanned([(str(tmp_path / f"{i}.txt"), 1) for i in range(20_000)])
        emitted = []
        model.statusCountsChanged.connect(lambda: emitted.append(time.monotonic()))
        start = time.monotonic()
        for i in range(20_000):
            path = str(tmp_path / f"{i}.txt")
            model.set_status(path, "working")
            model.set_status(path, "done")
        _settle(model)
        assert len(emitted) <= (time.monotonic() - start) * 1000 / COUNTS_INTERVAL_MS + 2
        gaps = [later - earlier for earlier, later in zip(emitted, emitted[1:])]
        assert all(gap >= COUNTS_INTERVAL_MS / 1000 * 0.9 for gap in gaps[:-1])
        assert _counts(model) == (0, 20_000, 0)

    def test_flush_counts_sends_the_pending_signal_at_once(self, model, tmp_path):
        _populate(model, tmp_path, ["a.txt"])
        emitted = []
        model.statusCountsChanged.connect(lambda: emitted.append(True))
        model.flush_counts()
        assert emitted == []
        model.set_status(str(tmp_path / "a.txt"), "done")
        model.flush_counts()
        assert emitted == [True]
        _settle(model)
        assert emitted == [True]

    def test_reset_for_run_is_one_update(self, model, tmp_path):
        paths = [str(tmp_path / f"{i}.txt") for i in range(10_000)]
        model.add_scanned([(path, 1) for path in paths])
        for path in paths:
            model.set_status(path, "failed", message="Wrong password")
        _settle(model)
        changed, counted = [], []
        model.dataChanged.connect(lambda first, last, _roles: changed.append((first.row(), last.row())))
        model.statusCountsChanged.connect(lambda: counted.append(True))
        start = time.perf_counter()
        model.reset_for_run(model.runnable_paths())
        assert time.perf_counter() - start < 1.0
        assert changed == [(0, 9_999)] and counted == [True]
        assert _counts(model) == (10_000, 0, 0)
