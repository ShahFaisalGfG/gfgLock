# test_folder_scanner.py - unit tests for gfglock.services.folder_scanner and folder loading

import ctypes
import gc
import os
import stat
import threading
import time
import weakref

import pytest
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtWidgets import QApplication

from gfglock.controllers.encrypt_ctrl import EncryptController
from gfglock.core.file_ops import ENCRYPTED_EXTS, TEMP_SUFFIX
from gfglock.models.file_model import FileListModel
from gfglock.services import folder_scanner
from gfglock.services.folder_scanner import FolderScanWorker, ScanReport, iter_files, protected_locations

_ENC = frozenset((".gfglock", ".gfglck", ".gfgcha"))
_NOTHING = frozenset()


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Share one QApplication with the rest of the suite."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def unprotected(monkeypatch):
    """pytest's temp folders live in %USERPROFILE%\\AppData, which encrypting leaves alone."""
    monkeypatch.setattr(folder_scanner, "protected_locations", lambda: _NOTHING)


def _touch(path, size=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _set_attributes(path, attributes: int) -> None:
    assert ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes), "SetFileAttributesW failed"


def _wait_for_scan(controller, timeout=10.0):
    deadline = time.monotonic() + timeout
    while (controller.scanning or controller._scans) and time.monotonic() < deadline:
        controller._scan_pool.waitForDone(50)
        QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    assert not controller.scanning, "the scan did not finish in time"


def _names(controller: EncryptController) -> list[str]:
    model = controller._file_model
    return sorted(os.path.basename(str(model.data(model.index(r), FileListModel.PathRole)))
                  for r in range(model.rowCount()))


def _notices(controller) -> list[str]:
    notices: list[str] = []
    controller.notice.connect(notices.append)
    return notices


def _run_worker(worker: FolderScanWorker) -> tuple[list, ScanReport]:
    """Run a worker on this thread and return (rows, report)."""
    rows: list = []
    reports: list = []
    worker.signals.batch_found.connect(lambda _id, batch: rows.extend(batch))
    worker.signals.finished.connect(lambda _id, report: reports.append(report))
    worker.run()
    return rows, reports[0]


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

    def test_missing_root_is_counted_as_a_failed_folder(self, tmp_path):
        report = ScanReport()
        assert list(iter_files([str(tmp_path / "gone")], lambda n: True, report=report)) == []
        assert (report.failed_roots, report.folders, report.unreadable) == (1, 0, 0)

    def test_unreadable_subfolders_are_counted_once_each(self, tmp_path, monkeypatch):
        """One count at the end instead of a notice per folder (A11)."""
        _touch(tmp_path / "ok" / "a.txt")
        for name in ("locked1", "locked2"):
            (tmp_path / name).mkdir()
        denied = {os.path.normpath(str(tmp_path / n)) for n in ("locked1", "locked2")}
        original_scandir = os.scandir

        def scandir(path):
            if os.path.normpath(path) in denied:
                raise PermissionError(5, "Access is denied")
            return original_scandir(path)

        monkeypatch.setattr(folder_scanner.os, "scandir", scandir)
        report = ScanReport()
        found = [os.path.basename(p) for p, _ in iter_files([str(tmp_path)], lambda n: True, report=report)]
        assert found == ["a.txt"]
        assert (report.folders, report.failed_roots, report.unreadable) == (1, 0, 2)


class TestProtectedLocations:
    """Encrypting leaves Windows, program and app folders, and System files alone (A6)."""

    @pytest.fixture
    def system(self, tmp_path, monkeypatch):
        """Environment variables pointing every protected location into tmp_path."""
        base = tmp_path / "sys"
        names = {"SystemRoot": "Windows", "ProgramFiles": "Program Files",
                 "ProgramFiles(x86)": "Program Files (x86)", "ProgramData": "ProgramData"}
        for variable, folder in names.items():
            monkeypatch.setenv(variable, str(base / folder))
        monkeypatch.setenv("USERPROFILE", str(base / "Users" / "me"))
        monkeypatch.setenv("APPDATA", str(base / "Roaming"))
        monkeypatch.setattr(folder_scanner, "data_dir", lambda: str(base / "portable data"))
        monkeypatch.setattr(folder_scanner, "app_folder", lambda: str(base / "Apps" / "gfgLock"))
        return base

    def test_every_location_is_listed(self, system):
        expected = ["Windows", "Program Files", "Program Files (x86)", "ProgramData",
                    os.path.join("Users", "me", "AppData"), os.path.join("Roaming", "gfgLock"),
                    "portable data", os.path.join("Apps", "gfgLock")]
        keys = {os.path.normcase(os.path.join(str(system), name)) for name in expected}
        assert protected_locations() == keys

    def test_unset_variables_are_ignored(self, monkeypatch):
        for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "USERPROFILE"):
            monkeypatch.delenv(variable, raising=False)
        assert all(os.path.isabs(folder) for folder in protected_locations())

    def test_protected_subfolders_are_skipped_without_walking(self, system):
        _touch(system / "Windows" / "System32" / "kernel.dll")
        _touch(system / "Users" / "me" / "AppData" / "Local" / "cache.db")
        _touch(system / "Users" / "me" / "Documents" / "plan.docx")
        _touch(system / "notes.txt")
        report = ScanReport()
        found = [os.path.relpath(p, system) for p, _ in
                 iter_files([str(system)], lambda n: True, report=report, protected=protected_locations())]
        assert found == ["notes.txt", os.path.join("Users", "me", "Documents", "plan.docx")]
        assert report.protected_folders == 2

    def test_a_protected_root_is_left_out_whole(self, system):
        _touch(system / "ProgramData" / "app" / "config.ini")
        report = ScanReport()
        root = str(system / "ProgramData" / "app")
        assert list(iter_files([root], lambda n: True, report=report, protected=protected_locations())) == []
        assert (report.protected_folders, report.folders) == (1, 0)

    def test_comparison_ignores_case(self, system):
        _touch(system / "windows" / "a.txt")
        report = ScanReport()
        root = str(system).upper()
        assert list(iter_files([root], lambda n: True, report=report, protected=protected_locations())) == []
        assert report.protected_folders == 1

    def test_system_files_and_hidden_system_folders_are_left_out(self, tmp_path):
        _touch(tmp_path / "desktop.ini")
        _touch(tmp_path / "photo.jpg")
        _touch(tmp_path / "$Recycle.Bin" / "S-1-5" / "$R1.docx")
        _set_attributes(tmp_path / "desktop.ini", stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM)
        _set_attributes(tmp_path / "$Recycle.Bin", stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM)
        report = ScanReport()
        found = [os.path.basename(p) for p, _ in
                 iter_files([str(tmp_path)], lambda n: True, report=report, protected=_NOTHING)]
        assert found == ["photo.jpg"]
        assert (report.protected_files, report.protected_folders) == (1, 1)

    def test_decrypt_mode_is_not_filtered(self, tmp_path):
        _touch(tmp_path / "desktop.ini.gfglock")
        _set_attributes(tmp_path / "desktop.ini.gfglock", stat.FILE_ATTRIBUTE_SYSTEM)
        rows, report = _run_worker(FolderScanWorker([str(tmp_path)], _ENC, include_encrypted=True))
        assert [os.path.basename(p) for p, _ in rows] == ["desktop.ini.gfglock"]
        assert report.protected_files == 0

    def test_files_added_directly_from_a_protected_folder_are_left_out(self, system, monkeypatch):
        monkeypatch.setattr(folder_scanner, "protected_locations", protected_locations)
        inside = system / "Users" / "me" / "AppData" / "Roaming" / "app.json"
        outside = system / "Users" / "me" / "Desktop" / "todo.txt"
        _touch(inside)
        _touch(outside)
        rows, report = _run_worker(FolderScanWorker([str(inside), str(outside)], _ENC, include_encrypted=False))
        assert [os.path.basename(p) for p, _ in rows] == ["todo.txt"]
        assert report.protected_files == 1

    def test_controller_reports_one_notice_with_the_counts(self, system, monkeypatch):
        monkeypatch.setattr(folder_scanner, "protected_locations", protected_locations)
        _touch(system / "Windows" / "a.dll")
        _touch(system / "Program Files" / "b.exe")
        _touch(system / "keep.txt")
        _touch(system / "pagefile.sys")
        _set_attributes(system / "pagefile.sys", stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM)
        controller = EncryptController("encrypt")
        notices = _notices(controller)
        controller.addFolder(str(system))
        _wait_for_scan(controller)
        assert _names(controller) == ["keep.txt"]
        assert notices == ["2 system or app folders and 1 system or app file were left out."]


class TestFolderScanWorker:
    def test_mode_filter(self, tmp_path):
        _touch(tmp_path / "a.txt")
        _touch(tmp_path / "b.GFGLOCK")
        for include_encrypted, expected in ((False, ["a.txt"]), (True, ["b.GFGLOCK"])):
            rows, _report = _run_worker(FolderScanWorker([str(tmp_path)], _ENC, include_encrypted))
            assert [os.path.basename(p) for p, _ in rows] == expected

    def test_cancelled_worker_sends_nothing(self, tmp_path):
        _touch(tmp_path / "a.txt")
        worker = FolderScanWorker([str(tmp_path)], _ENC, False)
        worker.cancel()
        rows, _report = _run_worker(worker)
        assert rows == [] and worker.cancelled

    def test_files_added_directly_are_sized_in_the_worker(self, tmp_path):
        """addFiles hands plain files to the worker, so the GUI thread never stats them (A18)."""
        _touch(tmp_path / "one.txt", 7)
        _touch(tmp_path / "locked.gfglock")
        _touch(tmp_path / ("." + "0" * 16 + TEMP_SUFFIX))
        worker = FolderScanWorker([str(tmp_path / "one.txt"), str(tmp_path / "locked.gfglock"),
                                   str(tmp_path / ("." + "0" * 16 + TEMP_SUFFIX)), str(tmp_path / "gone.txt")],
                                  _ENC, include_encrypted=False)
        rows, report = _run_worker(worker)
        assert rows == [(os.path.normpath(str(tmp_path / "one.txt")), 7)]
        assert report.other_type == 1

    def test_roots_queued_before_the_scan_ends_join_it(self, tmp_path):
        _touch(tmp_path / "first" / "a.txt")
        _touch(tmp_path / "second" / "b.txt")
        worker = FolderScanWorker([str(tmp_path / "first")], _ENC, False)
        assert worker.add_roots([str(tmp_path / "second")])
        rows, report = _run_worker(worker)
        assert [os.path.basename(p) for p, _ in rows] == ["a.txt", "b.txt"]
        assert report.folders == 2
        assert worker.add_roots([str(tmp_path / "first")]) is False

    def test_a_cancelled_scan_takes_no_more_roots(self, tmp_path):
        worker = FolderScanWorker([str(tmp_path)], _ENC, False)
        worker.cancel()
        assert worker.add_roots([str(tmp_path)]) is False

    def test_report_add_sums_counts(self):
        report = ScanReport(folders=1, unreadable=2)
        report.add(ScanReport(folders=2, failed_roots=1, protected_files=3, other_type=4, error="boom"))
        assert report == ScanReport(folders=3, failed_roots=1, unreadable=2, protected_files=3,
                                    other_type=4, error="boom")


class TestControllerFolderLoading:
    def test_dropped_folder_is_scanned_not_added_as_a_file(self, tmp_path):
        """Dropping a folder used to add the folder itself as a row, which then failed to encrypt."""
        _touch(tmp_path / "docs" / "one.txt")
        _touch(tmp_path / "docs" / "deep" / "two.txt")
        controller = EncryptController("encrypt")
        controller.addFiles([QUrl.fromLocalFile(str(tmp_path / "docs")).toString()])
        _wait_for_scan(controller)
        assert _names(controller) == ["one.txt", "two.txt"]

    def test_thousands_of_files_load_quickly(self, tmp_path):
        for i in range(3000):
            (tmp_path / f"f{i:04d}.bin").write_bytes(b"")
        controller = EncryptController("encrypt")
        start = time.perf_counter()
        controller.addFolder(QUrl.fromLocalFile(str(tmp_path)).toString())
        assert time.perf_counter() - start < 0.5, "addFolder must return immediately"
        _wait_for_scan(controller)
        assert controller._file_model.rowCount() == 3000
        assert time.perf_counter() - start < 10

    def test_a_second_folder_joins_the_running_scan(self, tmp_path, monkeypatch):
        """Dropping a folder while another one scans used to stop the first scan silently (A1)."""
        for i in range(500):
            _touch(tmp_path / "big" / f"f{i:03d}.txt", 1)
        _touch(tmp_path / "small" / "only.txt")
        release = threading.Event()
        monkeypatch.setattr(folder_scanner, "protected_locations", lambda: (release.wait(5), _NOTHING)[1])
        controller = EncryptController("encrypt")
        notices = _notices(controller)
        scanning = []
        controller.scanChanged.connect(lambda: scanning.append(controller.scanning))
        controller.addFolder(str(tmp_path / "big"))
        controller.addFolder(str(tmp_path / "small"))
        assert len(controller._scans) == 1, "the second folder must join, not replace, the scan"
        release.set()
        _wait_for_scan(controller)
        assert controller._file_model.rowCount() == 501
        assert scanning[-1] is False and scanning.count(False) == 1
        assert controller.scanFound == 501 and notices == []

    def test_folders_added_after_a_scan_closed_still_all_arrive(self, tmp_path):
        _touch(tmp_path / "a" / "1.txt")
        _touch(tmp_path / "b" / "2.txt")
        controller = EncryptController("encrypt")
        controller.addFolder(str(tmp_path / "a"))
        controller._scan_pool.waitForDone(5000)   # the first scan closed; its events are still queued
        controller.addFolder(str(tmp_path / "b"))
        _wait_for_scan(controller)
        assert _names(controller) == ["1.txt", "2.txt"]

    def test_clearing_the_list_during_a_scan_keeps_it_empty(self, tmp_path):
        """Batches already on their way used to arrive after Clear and refill the list (A7)."""
        for i in range(300):
            _touch(tmp_path / f"f{i:03d}.txt", 1)
        controller = EncryptController("encrypt")
        controller.addFolder(str(tmp_path))
        controller._scan_pool.waitForDone(5000)   # every batch is sent and waiting in the event queue
        controller.clearFiles()
        assert controller.scanning is False
        _wait_for_scan(controller)
        assert controller._file_model.rowCount() == 0 and controller._scans == {}

    def test_stop_keeps_the_rows_found_so_far(self, tmp_path):
        _touch(tmp_path / "a.txt")
        controller = EncryptController("encrypt")
        controller.addFolder(str(tmp_path))
        _wait_for_scan(controller)
        controller.cancelScan()
        assert controller._file_model.rowCount() == 1

    def test_finished_scans_are_released(self, tmp_path):
        """A lambda that captured each worker kept every finished scan alive (A20)."""
        _touch(tmp_path / "a.txt")
        controller = EncryptController("encrypt")
        refs = []
        for _ in range(3):
            controller.addFolder(str(tmp_path))
            refs.append(weakref.ref(controller._scans[next(iter(controller._scans))]))
            _wait_for_scan(controller)
        gc.collect()
        assert [ref() for ref in refs] == [None, None, None]

    def test_scans_do_not_wait_for_the_shared_pool(self, tmp_path):
        """A run on a 2-thread PC used to hold scans back until it ended (A19)."""
        controller = EncryptController("encrypt")
        assert controller._scan_pool is not controller._threadpool

    def test_empty_folder_is_reported(self, tmp_path):
        _touch(tmp_path / "a.txt")
        controller = EncryptController("decrypt")
        notices = _notices(controller)
        controller.addFolder(str(tmp_path))
        _wait_for_scan(controller)
        assert notices == ["No gfgLock-encrypted files in that folder."]

    def test_a_folder_that_cannot_be_opened_says_so(self, tmp_path, monkeypatch):
        """It used to say "No files to encrypt in that folder." (A11)."""
        (tmp_path / "locked").mkdir()
        original_scandir = os.scandir

        def scandir(path):
            if os.path.normpath(path) == os.path.normpath(str(tmp_path / "locked")):
                raise PermissionError(5, "Access is denied")
            return original_scandir(path)

        monkeypatch.setattr(folder_scanner.os, "scandir", scandir)
        controller = EncryptController("encrypt")
        notices = _notices(controller)
        controller.addFolder(str(tmp_path / "locked"))
        _wait_for_scan(controller)
        assert notices == ["Couldn't open that folder."]

    def test_unreadable_subfolders_give_one_notice(self, tmp_path, monkeypatch):
        _touch(tmp_path / "a.txt")
        for i in range(5):
            (tmp_path / f"locked{i}").mkdir()
        original_scandir = os.scandir

        def scandir(path):
            if os.path.basename(path).startswith("locked"):
                raise PermissionError(5, "Access is denied")
            return original_scandir(path)

        monkeypatch.setattr(folder_scanner.os, "scandir", scandir)
        controller = EncryptController("encrypt")
        notices = _notices(controller)
        controller.addFolder(str(tmp_path))
        _wait_for_scan(controller)
        assert notices == ["5 folders inside couldn't be opened and were skipped."]
        assert _names(controller) == ["a.txt"]


class TestLinksAndTempFiles:
    def test_junction_loop_is_not_followed(self, tmp_path):
        _winapi = pytest.importorskip("_winapi")
        root = tmp_path / "root"
        _touch(root / "a.txt")
        _winapi.CreateJunction(str(root), str(root / "loop"))
        found = [os.path.relpath(p, root) for p, _ in iter_files([str(root)], lambda n: True)]
        assert found == ["a.txt"]

    def test_temp_files_of_unfinished_jobs_are_left_out(self, tmp_path):
        _touch(tmp_path / "doc.txt")
        _touch(tmp_path / (".0123456789abcdef" + TEMP_SUFFIX))
        worker = FolderScanWorker([str(tmp_path)], ENCRYPTED_EXTS, include_encrypted=False)
        found = [os.path.basename(p) for p, _ in iter_files([str(tmp_path)], worker._accept)]
        assert found == ["doc.txt"]
