# test_folder_scanner.py - unit tests for gfglock.services.folder_scanner and folder loading

import os
import time

import pytest
from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtWidgets import QApplication

from gfglock.controllers.encrypt_ctrl import EncryptController
from gfglock.models.file_model import FileListModel
from gfglock.services.folder_scanner import FolderScanWorker, iter_files

_ENC = frozenset((".gfglock", ".gfglck", ".gfgcha"))


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Share one QApplication with the rest of the suite."""
    return QApplication.instance() or QApplication([])


def _touch(path, size=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _wait_for_scan(controller, qt_app, timeout=10.0):
    deadline = time.monotonic() + timeout
    while controller.scanning and time.monotonic() < deadline:
        QThreadPool.globalInstance().waitForDone(50)
        qt_app.processEvents()
    qt_app.processEvents()


class TestIterFiles:
    def test_recursive_sorted_with_sizes(self, tmp_path):
        _touch(tmp_path / "b.txt", 2)
        _touch(tmp_path / "A.txt", 3)
        _touch(tmp_path / "sub" / "c.txt", 5)
        found = list(iter_files([str(tmp_path)], lambda name: True))
        assert [os.path.relpath(p, tmp_path) for p, _ in found] == ["A.txt", "b.txt", os.path.join("sub", "c.txt")]
        assert [size for _, size in found] == [3, 2, 5]

    def test_accept_filter_and_cancel(self, tmp_path):
        for i in range(10):
            _touch(tmp_path / f"{i}.gfglock")
        _touch(tmp_path / "plain.txt")
        assert len(list(iter_files([str(tmp_path)], lambda n: n.endswith(".txt")))) == 1
        seen = []
        for path, _ in iter_files([str(tmp_path)], lambda n: True, is_cancelled=lambda: len(seen) >= 3):
            seen.append(path)
        assert len(seen) == 3

    def test_missing_root_reports_error(self, tmp_path):
        errors = []
        assert list(iter_files([str(tmp_path / "gone")], lambda n: True, on_error=errors.append)) == []
        assert errors


class TestFolderScanWorker:
    def test_mode_filter(self, tmp_path):
        _touch(tmp_path / "a.txt")
        _touch(tmp_path / "b.GFGLOCK")
        for include_encrypted, expected in ((False, ["a.txt"]), (True, ["b.GFGLOCK"])):
            worker = FolderScanWorker([str(tmp_path)], _ENC, include_encrypted)
            batches = []
            worker.signals.batch_found.connect(batches.append)
            worker.run()
            assert [os.path.basename(p) for batch in batches for p, _ in batch] == expected

    def test_cancelled_worker_sends_nothing(self, tmp_path):
        _touch(tmp_path / "a.txt")
        worker = FolderScanWorker([str(tmp_path)], _ENC, False)
        batches, finished = [], []
        worker.signals.batch_found.connect(batches.append)
        worker.signals.finished.connect(lambda found, cancelled: finished.append(cancelled))
        worker.cancel()
        worker.run()
        assert batches == [] and finished == [True]


class TestControllerFolderLoading:
    def test_dropped_folder_is_scanned_not_added_as_a_file(self, tmp_path, qt_app):
        """Dropping a folder used to add the folder itself as a row, which then failed to encrypt."""
        _touch(tmp_path / "docs" / "one.txt")
        _touch(tmp_path / "docs" / "deep" / "two.txt")
        controller = EncryptController()
        controller.setMode("encrypt")
        controller.addFiles([QUrl.fromLocalFile(str(tmp_path / "docs")).toString()])
        _wait_for_scan(controller, qt_app)
        names = sorted(os.path.basename(p) for p in controller._file_model.getPaths())
        assert names == ["one.txt", "two.txt"]

    def test_thousands_of_files_load_quickly(self, tmp_path, qt_app):
        for i in range(3000):
            (tmp_path / f"f{i:04d}.bin").write_bytes(b"")
        controller = EncryptController()
        controller.setMode("encrypt")
        start = time.perf_counter()
        controller.addFolder(QUrl.fromLocalFile(str(tmp_path)).toString())
        assert time.perf_counter() - start < 0.5, "addFolder must return immediately"
        _wait_for_scan(controller, qt_app)
        assert controller._file_model.count == 3000
        assert time.perf_counter() - start < 10

    def test_mode_change_cancels_scan(self, tmp_path, qt_app):
        _touch(tmp_path / "a.txt")
        controller = EncryptController()
        controller.setMode("encrypt")
        controller.addFolder(QUrl.fromLocalFile(str(tmp_path)).toString())
        controller.setMode("decrypt")
        _wait_for_scan(controller, qt_app)
        assert controller.scanning is False


class TestModelBulkOperations:
    def test_add_scanned_dedupes_in_one_insert(self, tmp_path):
        model = FileListModel()
        inserts = []
        model.rowsInserted.connect(lambda *args: inserts.append(args))
        path = str(tmp_path / "a.txt")
        model.addScanned([(path, 10), (path, 10), (str(tmp_path / "b.txt"), 20)])
        assert model.count == 2 and len(inserts) == 1
        assert model.totalSize == "30.0 B"

    def test_remove_thousands_selected_is_fast(self, tmp_path):
        model = FileListModel()
        model.addScanned([(str(tmp_path / f"{i}.txt"), 1) for i in range(5000)])
        model.selectAll()
        start = time.perf_counter()
        model.removeSelected()
        assert model.count == 0
        assert time.perf_counter() - start < 1.0

    def test_add_files_skips_directories(self, tmp_path):
        model = FileListModel()
        (tmp_path / "folder").mkdir()
        model.addFiles([str(tmp_path / "folder")])
        assert model.count == 0
