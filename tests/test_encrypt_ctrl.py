# test_encrypt_ctrl.py - unit tests for gfglock.controllers.encrypt_ctrl

import os
import threading
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtWidgets import QApplication

from gfglock.controllers import encrypt_ctrl
from gfglock.controllers.encrypt_ctrl import EncryptController
from gfglock.core.file_ops import FileResult
from gfglock.core.format_v2 import KdfParams, KeyRing
from gfglock.models.file_model import FileListModel
from gfglock.services import folder_scanner
from gfglock.services import worker as worker_mod
from gfglock.services.worker import EncryptDecryptWorker

_CHEAP_KDF = KdfParams(memory_kib=64, iterations=1, lanes=1)
_WRONG_PASSWORD = "Wrong password or the file was modified (authentication failed)"


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - EncryptController calls QApplication.clipboard(),
    so every test file shares this app type to avoid a bare QCoreApplication
    winning the session-wide singleton race depending on run order."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """No log files, no notifications, a cheap key derivation, and no protected folders (pytest's
    temp folders sit in %USERPROFILE%\\AppData, which encrypting leaves alone)."""
    monkeypatch.setattr(encrypt_ctrl, "write_log", MagicMock())
    monkeypatch.setattr(encrypt_ctrl, "write_session_separator", MagicMock())
    monkeypatch.setattr(encrypt_ctrl, "notify", MagicMock())
    monkeypatch.setattr(encrypt_ctrl, "KeyRing", lambda password: KeyRing(password, _CHEAP_KDF))
    monkeypatch.setattr(folder_scanner, "protected_locations", frozenset)


@pytest.fixture
def encryptor():
    return EncryptController("encrypt")


@pytest.fixture
def decryptor():
    return EncryptController("decrypt")


@pytest.fixture
def no_notifications(monkeypatch):
    monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}})


def _notices(controller) -> list:
    notices: list = []
    controller.notice.connect(notices.append)
    return notices


def _wait_until_idle(controller, timeout=20.0) -> None:
    """Let the worker run and deliver its queued signals until the controller is idle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if not controller.busy:
            QThreadPool.globalInstance().waitForDone(1000)
            QCoreApplication.processEvents()
            return
        time.sleep(0.01)
    pytest.fail("the run did not finish in time")


def _wait_for_scan(controller, timeout=10.0) -> None:
    deadline = time.monotonic() + timeout
    while (controller.scanning or controller._scans) and time.monotonic() < deadline:
        controller._scan_pool.waitForDone(50)
        QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    assert not controller.scanning, "the scan did not finish in time"


def _add(controller, *paths) -> None:
    """Add files or folders and wait until the background check has listed them."""
    controller.addFiles([str(path) for path in paths])
    _wait_for_scan(controller)


def _paths(model: FileListModel) -> list:
    return [model.data(model.index(r), FileListModel.PathRole) for r in range(model.rowCount())]


def _rows(model: FileListModel) -> list:
    """(status, message) for every row."""
    return [(model.data(model.index(r), FileListModel.StatusRole),
             model.data(model.index(r), FileListModel.MessageRole)) for r in range(model.rowCount())]


class TestModes:
    """Each controller accepts only the files its tab works on."""

    @pytest.mark.parametrize("name,allowed", [
        ("plain.txt", True), ("secret.gfglock", False), ("secret.GFGLCK", False), ("secret.gfgcha", False),
    ])
    def test_encrypt_tab_rejects_encrypted_files(self, encryptor, tmp_path, name, allowed):
        (tmp_path / name).write_text("x")
        _add(encryptor, tmp_path / name)
        assert encryptor.fileModel.count == int(allowed)

    @pytest.mark.parametrize("name,allowed", [("plain.txt", False), ("secret.gfglock", True)])
    def test_decrypt_tab_requires_encrypted_files(self, decryptor, tmp_path, name, allowed):
        (tmp_path / name).write_text("x")
        _add(decryptor, tmp_path / name)
        assert decryptor.fileModel.count == int(allowed)

    def test_unknown_mode_means_encrypt(self):
        assert EncryptController("preview").mode == "encrypt"


class TestUrlToPath:
    def test_file_url_converted_to_local_path(self, tmp_path):
        target = tmp_path / "sample.txt"
        target.write_text("x")
        url = QUrl.fromLocalFile(str(target)).toString()
        assert os.path.normpath(EncryptController._url_to_path(url)) == os.path.normpath(str(target))

    def test_non_url_string_passthrough(self):
        assert EncryptController._url_to_path("not a url") == "not a url"


class TestAddingFiles:
    def test_add_files_keeps_allowed_files_and_reports_the_rest(self, encryptor, tmp_path):
        plain = tmp_path / "plain.txt"
        plain.write_text("x")
        locked = tmp_path / "already.gfglock"
        locked.write_text("x")
        notices = _notices(encryptor)
        encryptor.addFiles([QUrl.fromLocalFile(str(plain)).toString(), str(locked), ""])
        _wait_for_scan(encryptor)
        assert _paths(encryptor.fileModel) == [os.path.normpath(str(plain))]
        assert notices == ["1 file already encrypted was left out. Use the Decrypt tab to open it."]

    def test_several_left_out_files_are_them(self, encryptor, tmp_path):
        for name in ("a.gfglock", "b.gfgcha"):
            (tmp_path / name).write_text("x")
        notices = _notices(encryptor)
        _add(encryptor, tmp_path / "a.gfglock", tmp_path / "b.gfgcha")
        assert notices == ["2 files already encrypted were left out. Use the Decrypt tab to open them."]

    def test_decrypt_tab_explains_left_out_files(self, decryptor, tmp_path):
        for name in ("a.txt", "b.txt"):
            (tmp_path / name).write_text("x")
        notices = _notices(decryptor)
        _add(decryptor, tmp_path / "a.txt", tmp_path / "b.txt")
        assert decryptor.fileModel.count == 0
        assert notices == ["2 files not encrypted by gfgLock were left out."]

    def test_files_are_checked_off_the_gui_thread(self, encryptor, tmp_path, monkeypatch):
        """addFiles only parses the paths; the scan worker stats and sizes them (A18)."""
        made = []
        original_worker = encrypt_ctrl.FolderScanWorker

        def recorded(roots, *args, **kwargs):
            made.append(list(roots))
            return original_worker(roots, *args, **kwargs)

        monkeypatch.setattr(encrypt_ctrl, "FolderScanWorker", recorded)
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "docs").mkdir()
        original_isdir = os.path.isdir
        monkeypatch.setattr(encrypt_ctrl.os.path, "isdir", lambda _p: pytest.fail("stat on the GUI thread"))
        encryptor.addFiles([str(tmp_path / "a.txt"), str(tmp_path / "docs"), str(tmp_path / "a.txt")])
        monkeypatch.setattr(encrypt_ctrl.os.path, "isdir", original_isdir)
        assert encryptor.fileModel.count == 0 and encryptor.scanning
        assert made == [[os.path.normpath(str(tmp_path / "a.txt")), os.path.normpath(str(tmp_path / "docs"))]]
        _wait_for_scan(encryptor)
        assert encryptor.fileModel.count == 1

    def test_add_folder_scans_and_filters(self, encryptor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.gfglock").write_text("x")
        (sub / "c.txt").write_text("x")
        encryptor.addFolder(QUrl.fromLocalFile(str(tmp_path)).toString())
        _wait_for_scan(encryptor)
        found = set(_paths(encryptor.fileModel))
        assert found == {os.path.normpath(str(tmp_path / "a.txt")), os.path.normpath(str(sub / "c.txt"))}
        assert not encryptor.scanning

    def test_empty_folder_is_reported(self, decryptor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        notices = _notices(decryptor)
        decryptor.addFolder(str(tmp_path))
        _wait_for_scan(decryptor)
        assert notices == ["No gfgLock-encrypted files in that folder."]

    def test_missing_folder_is_ignored(self, encryptor):
        notices = _notices(encryptor)
        encryptor.addFolder(QUrl.fromLocalFile("Z:\\does\\not\\exist").toString())
        _wait_for_scan(encryptor)
        assert encryptor.fileModel.count == 0 and notices == []

    def test_clear_files_empties_the_list(self, encryptor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        _add(encryptor, tmp_path / "a.txt")
        encryptor.clearFiles()
        assert encryptor.fileModel.count == 0

    def test_files_added_during_a_run_are_announced(self, encryptor, tmp_path):
        (tmp_path / "late.txt").write_text("x")
        notices = _notices(encryptor)
        encryptor._busy = True
        _add(encryptor, tmp_path / "late.txt")
        assert notices == ["1 file added. It will run when you press Encrypt again after this run."]

    def test_shutdown_stops_scans(self, encryptor, tmp_path):
        for i in range(200):
            (tmp_path / f"{i}.txt").write_text("x")
        encryptor.addFolder(str(tmp_path))
        encryptor.shutdown()
        assert not encryptor.scanning and encryptor._scan_pool.activeThreadCount() == 0


class TestClipboard:
    def test_copy_selected_names_sets_clipboard(self, encryptor, monkeypatch):
        encryptor._file_model = MagicMock()
        encryptor._file_model.getSelectedNamesText.return_value = "a.txt\nb.txt"
        fake_app = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "QApplication", fake_app)
        encryptor.copySelectedNames()
        fake_app.clipboard.return_value.setText.assert_called_once_with("a.txt\nb.txt")

    def test_empty_selection_leaves_clipboard_alone(self, encryptor, monkeypatch):
        encryptor._file_model = MagicMock()
        encryptor._file_model.getSelectedPathsText.return_value = ""
        fake_app = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "QApplication", fake_app)
        encryptor.copySelectedPaths()
        fake_app.clipboard.assert_not_called()


class TestStartSettings:
    """start() reads the thread count and read size from preferences for its own mode."""

    def _capture_worker(self, controller, monkeypatch, settings):
        made: dict = {}

        def fake_worker(**kwargs):
            made.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(encrypt_ctrl, "EncryptDecryptWorker", fake_worker)
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: settings)
        controller._threadpool = MagicMock()
        return made

    def test_uses_decryption_preferences(self, decryptor, monkeypatch, tmp_path):
        (tmp_path / "a.gfglock").write_text("x")
        _add(decryptor, tmp_path / "a.gfglock")
        made = self._capture_worker(decryptor, monkeypatch, {
            "decryption": {"cpu_threads": 2, "read_size": 8 * 1024 * 1024},
            "encryption": {"cpu_threads": 9, "read_size": 0},
            "advanced": {"clamp_cpu_threads": False},
        })
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 8)
        decryptor.start("pw", False, "")
        assert made["threads"] == 2 and made["read_size"] == 8 * 1024 * 1024 and made["mode"] == "decrypt"
        assert isinstance(made["keys"], KeyRing) and made["keys"].password == "pw"
        assert decryptor.busy

    def test_threads_are_clamped_to_leave_one_free(self, encryptor, monkeypatch, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        _add(encryptor, tmp_path / "a.txt")
        made = self._capture_worker(encryptor, monkeypatch, {
            "encryption": {"cpu_threads": 20}, "advanced": {"clamp_cpu_threads": True},
        })
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 4)
        encryptor.start("pw", True, "chacha20_poly1305")
        assert made["threads"] == 3 and made["algorithm"] == "chacha" and made["encrypt_name"] is True

    @pytest.mark.parametrize("choice,saved,cipher", [
        ("aes256_gcm", "", "gcm"),
        ("chacha20_poly1305", "", "chacha"),
        ("aes256_cfb", "", "gcm"),           # CFB is decrypt-only now
        ("", "chacha20_poly1305", "chacha"),  # the page passed nothing: the saved preference
        ("", "aes256_cfb", "gcm"),
        ("rot13", "", "gcm"),
    ])
    def test_algorithm_codes_map_to_engine_ciphers(self, encryptor, monkeypatch, tmp_path, choice, saved, cipher):
        (tmp_path / "a.txt").write_text("x")
        _add(encryptor, tmp_path / "a.txt")
        made = self._capture_worker(encryptor, monkeypatch, {"advanced": {"encryption_mode": saved}})
        encryptor.start("pw", False, choice)
        assert made["algorithm"] == cipher

    def test_no_password_or_no_files_does_nothing(self, encryptor, monkeypatch, tmp_path):
        made = self._capture_worker(encryptor, monkeypatch, {})
        encryptor.start("pw", False, "")
        (tmp_path / "a.txt").write_text("x")
        _add(encryptor, tmp_path / "a.txt")
        encryptor.start("", False, "")
        assert made == {} and not encryptor.busy

    def test_an_unusable_password_is_a_notice(self, encryptor, monkeypatch, tmp_path):
        monkeypatch.setattr(encrypt_ctrl, "KeyRing", KeyRing)
        (tmp_path / "a.txt").write_text("x")
        _add(encryptor, tmp_path / "a.txt")
        made = self._capture_worker(encryptor, monkeypatch, {})
        notices = _notices(encryptor)
        encryptor.start("bad \ud800 password", False, "")
        assert made == {} and not encryptor.busy
        assert notices == ["The password contains characters that can't be used."]


class TestRuns:
    """End-to-end encrypt and decrypt runs through the worker, checked row by row."""

    def test_encrypt_then_decrypt_round_trip(self, encryptor, decryptor, tmp_path, no_notifications):
        source = tmp_path / "notes.txt"
        source.write_text("secret notes")
        _add(encryptor, source)
        encryptor.start("correct horse", False, "aes256_gcm")
        _wait_until_idle(encryptor)

        locked = tmp_path / "notes.txt.gfglock"
        assert locked.exists() and not source.exists()
        assert _rows(encryptor.fileModel) == [("done", "Saved as notes.txt.gfglock")]
        assert encryptor.summary.startswith("1 file encrypted in ")
        assert encryptor.lastFolder == str(tmp_path)
        assert encryptor.fileModel.runnableCount == 0
        assert (encryptor.progress, encryptor.filesDone, encryptor.filesTotal) == (1.0, 1, 1)

        _add(decryptor, locked)
        decryptor.start("wrong password", False, "")
        _wait_until_idle(decryptor)
        status, message = _rows(decryptor.fileModel)[0]
        assert status == "failed" and "wrong password" in message.lower()
        assert locked.exists()
        assert decryptor.summary.startswith("0 of 1 file decrypted") and "1 failed: wrong password" in decryptor.summary

        # A failed file stays in the list and runs again with the right password.
        assert decryptor.fileModel.runnableCount == 1
        decryptor.start("correct horse", False, "")
        _wait_until_idle(decryptor)
        assert _rows(decryptor.fileModel) == [("done", "Saved as notes.txt")]
        assert source.read_text() == "secret notes"

    def test_finished_rows_are_not_run_again(self, encryptor, tmp_path, monkeypatch):
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {})
        (tmp_path / "a.txt").write_text("a")
        _add(encryptor, tmp_path / "a.txt")
        encryptor.start("pw", False, "chacha20_poly1305")
        _wait_until_idle(encryptor)
        (tmp_path / "b.txt").write_text("b")
        _add(encryptor, tmp_path / "b.txt")
        assert encryptor.fileModel.runnableCount == 1
        encryptor.start("pw", False, "chacha20_poly1305")
        _wait_until_idle(encryptor)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt.gfgcha", "b.txt.gfgcha"]
        encryptor.fileModel.removeFinished()
        assert encryptor.fileModel.count == 0

    def test_leftover_temp_files_are_removed_with_one_notice(self, encryptor, tmp_path, no_notifications):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / ".0123456789abcdef.gfgpart").write_bytes(b"left by a crash")
        (tmp_path / ".fedcba9876543210.gfgpart").write_bytes(b"left by a crash")
        _add(encryptor, tmp_path / "a.txt")
        notices = _notices(encryptor)
        encryptor.start("pw", False, "aes256_gcm")
        _wait_until_idle(encryptor)
        assert notices == ["Removed 2 temporary files left by an earlier run that didn't finish."]
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt.gfglock"]

    def test_stop_ends_the_files_in_progress_unchanged(self, encryptor, tmp_path, no_notifications, monkeypatch):
        """Stop cancels the run's stop token: the file in progress stays unchanged and waits for the next run."""
        (tmp_path / "a.txt").write_text("a")
        _add(encryptor, tmp_path / "a.txt")
        original_build = EncryptDecryptWorker._build_job
        started, resume = threading.Event(), threading.Event()

        def held(worker, path, read_size):
            started.set()
            resume.wait(5)
            return original_build(worker, path, read_size)

        monkeypatch.setattr(EncryptDecryptWorker, "_build_job", held)
        encryptor.start("pw", False, "aes256_gcm")
        assert started.wait(5)
        encryptor.cancel()  # Stop pressed while the file is in progress
        resume.set()
        _wait_until_idle(encryptor)
        status, message = _rows(encryptor.fileModel)[0]
        assert status == "waiting" and message.startswith("Stopped")
        assert encryptor.fileModel.runnableCount == 1  # the next Encrypt processes it
        assert (tmp_path / "a.txt").read_text() == "a"
        assert encryptor.summary == "Stopped: 0 of 1 file encrypted. The rest were not changed."

    def test_stop_after_the_last_file_reports_a_complete_run(self, encryptor, no_notifications):
        encryptor._cancel_requested = True  # Stop arrived after every file had ended
        encryptor._on_finished(1.0, 2, 2, 0, 0)
        assert encryptor.summary == "All 2 files encrypted in 1.0 s."
        assert encryptor.progress == 1.0


class TestRunPerformance:
    """The list keeps its counts incrementally and run updates are coalesced (A5, U2, U31)."""

    def test_a_run_over_20000_rows_stays_fast(self, encryptor, monkeypatch):
        """Before 3.2.0 this run took about 355 s on the development PC; it now takes about 5 s."""
        def instant(path, keys, algorithm, encrypt_name=False, read_size=0, progress=None, stop=None):
            return FileResult(True, f"Encrypted: {path}", "done", output=f"{path}.gfglock")

        monkeypatch.setattr(worker_mod.file_ops, "encrypt_file", instant)
        monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda folders: 0)
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {
            "encryption": {"cpu_threads": 4},
            "advanced": {"clamp_cpu_threads": False, "operation_notifications": False}})
        model = encryptor.fileModel
        model.add_scanned([(f"C:\\bench\\folder{i // 1000}\\file{i:05d}.txt", 100) for i in range(20_000)])
        reads: dict = {"counts": 0, "run": 0}

        def read_counts():  # as the QML views do on every change
            reads["counts"] += 1
            reads["last counts"] = (model.runnableCount, model.finishedCount, model.failedCount)

        def read_run():
            reads["run"] += 1
            reads["last run"] = (encryptor.progress, encryptor.filesDone, encryptor.currentFile)

        model.statusCountsChanged.connect(read_counts)
        encryptor.runChanged.connect(read_run)
        loop = QEventLoop()
        encryptor.busyChanged.connect(lambda busy: None if busy else loop.quit())
        QTimer.singleShot(120_000, loop.quit)
        start = time.perf_counter()
        encryptor.start("pw", False, "aes256_gcm")
        loop.exec()
        elapsed = time.perf_counter() - start
        assert model.finishedCount == 20_000 and encryptor.filesDone == 20_000
        assert elapsed < 30, f"the run took {elapsed:.1f} s"
        assert reads["counts"] <= elapsed * 10 + 3 and reads["run"] <= elapsed * 10 + 3

    def test_run_updates_are_coalesced(self, encryptor):
        emitted = []
        encryptor.runChanged.connect(lambda: emitted.append(time.monotonic()))
        encryptor._busy = True
        start = time.monotonic()
        for i in range(2000):
            encryptor._on_progress(float(i), 4000.0)
        assert len(emitted) <= (time.monotonic() - start) * 10 + 1
        deadline = time.monotonic() + 2
        while encryptor._run_timer.isActive() and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.005)
        assert len(emitted) <= (time.monotonic() - start) * 10 + 2
        assert encryptor.progress == pytest.approx(1999 / 4000)


class TestProgress:
    def test_progress_holds_below_100_until_the_run_ends(self, encryptor, no_notifications):
        """The last files are still being flushed when every byte has been read (U6)."""
        encryptor._busy = True
        encryptor._worker = MagicMock()
        encryptor._on_progress(100.0, 100.0)
        assert encryptor.progress == 0.99
        encryptor._on_finished(1.0, 1, 1, 0, 0)
        assert encryptor.progress == 1.0

    def test_a_stopped_run_keeps_its_progress(self, encryptor, no_notifications):
        encryptor._busy = True
        encryptor._worker = MagicMock()
        encryptor._on_progress(30.0, 100.0)
        encryptor.cancel()
        encryptor._on_finished(1.0, 3, 1, 0, 0)
        assert encryptor.progress == pytest.approx(0.3)

    def test_the_end_of_a_run_is_sent_at_once(self, encryptor, no_notifications):
        emitted, counted = [], []
        encryptor.runChanged.connect(lambda: emitted.append(True))
        encryptor.fileModel.statusCountsChanged.connect(lambda: counted.append(True))
        encryptor.fileModel.add_scanned([("C:\\x\\a.txt", 1)])
        counted.clear()
        encryptor._busy = True
        encryptor._worker = MagicMock()
        encryptor._on_file_result("C:\\x\\a.txt", "done", "", "C:\\x\\a.txt.gfglock")
        emitted.clear()
        encryptor._on_finished(1.0, 1, 1, 0, 0)
        assert emitted == [True] and counted


class TestSummary:
    @pytest.mark.parametrize("args,expected", [
        ((2.04, 3, 3, 0, 0, False), "All 3 files encrypted in 2.0 s."),
        ((0.4, 1, 1, 0, 0, False), "1 file encrypted in 0.4 s."),
        ((0.03, 2, 2, 0, 0, False), "All 2 files encrypted in under 0.1 s."),
        ((75.2, 3, 3, 0, 0, False), "All 3 files encrypted in 1 min 15 s."),
        ((3725.0, 3, 3, 0, 0, False), "All 3 files encrypted in 1 h 2 min."),
        ((1.0, 4, 2, 1, 1, False), "2 of 4 files encrypted in 1.0 s, 1 skipped, 1 failed."),
        ((1.0, 5, 2, 0, 0, True), "Stopped: 2 of 5 files encrypted. The rest were not changed."),
        ((4.2, 10, 1, 2, 0, True), "Stopped: 1 of 10 files encrypted, 2 failed. The rest were not changed."),
        ((2.0, 2, 2, 0, 0, True), "Stopped: 2 of 2 files encrypted."),
    ])
    def test_summary_lines(self, encryptor, args, expected):
        """A stopped run names its failures, and fast runs say "under 0.1 s" (A14)."""
        encryptor._failure_reasons = {"Disk full", "Access is denied"}
        assert encryptor._build_summary(*args) == expected

    def test_one_shared_failure_reason_is_stated_once(self, decryptor):
        """When every failure has the same reason, the summary says it (U7)."""
        for name in ("a", "b", "c"):
            decryptor._on_file_result(f"C:\\x\\{name}.gfglock", "failed", _WRONG_PASSWORD, "")
        assert decryptor._build_summary(1.2, 3, 0, 3, 0, False) == (
            "0 of 3 files decrypted in 1.2 s, 3 failed: wrong password or the file was modified "
            "(authentication failed).")

    def test_a_done_row_with_a_reason_shows_both(self, decryptor):
        decryptor.fileModel.add_scanned([("C:\\x\\old.gfglck", 10)])
        decryptor._on_file_result("C:\\x\\old.gfglck", "done", "The encrypted file was kept", "C:\\x\\old.txt")
        assert _rows(decryptor.fileModel) == [("done", "Saved as old.txt. The encrypted file was kept")]

    def test_summary_clears_when_the_list_changes(self, encryptor, tmp_path):
        encryptor._summary = "All 1 file encrypted in 0.1 s."
        cleared = []
        encryptor.summaryChanged.connect(lambda: cleared.append(encryptor.summary))
        (tmp_path / "new.txt").write_text("x")
        _add(encryptor, tmp_path / "new.txt")
        assert encryptor.summary == "" and cleared == [""]


class TestNotifications:
    """A notification goes out only when the preference is on and the user may have looked away (A15)."""

    @pytest.fixture
    def sent(self, monkeypatch):
        send = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "notify", send)
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": True}})
        return send

    def _state(self, monkeypatch, active: bool) -> None:
        state = Qt.ApplicationState.ApplicationActive if active else Qt.ApplicationState.ApplicationInactive
        fake = MagicMock()
        fake.applicationState.return_value = state
        monkeypatch.setattr(encrypt_ctrl, "QGuiApplication", fake)

    def test_preference_off_sends_nothing(self, encryptor, sent, monkeypatch):
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}})
        self._state(monkeypatch, active=False)
        encryptor._notify_complete(60.0, 0, False)
        sent.assert_not_called()

    def test_a_short_run_in_front_of_the_user_sends_nothing(self, encryptor, sent, monkeypatch):
        self._state(monkeypatch, active=True)
        encryptor._notify_complete(9.9, 0, False)
        sent.assert_not_called()

    def test_a_long_run_notifies_even_in_front(self, encryptor, sent, monkeypatch):
        self._state(monkeypatch, active=True)
        encryptor._summary = "All 3 files encrypted in 12.0 s."
        encryptor._notify_complete(12.0, 0, False)
        sent.assert_called_once_with("Encryption complete", "All 3 files encrypted in 12.0 s.")

    def test_a_run_behind_other_windows_notifies(self, encryptor, sent, monkeypatch):
        self._state(monkeypatch, active=False)
        encryptor._notify_complete(0.5, 0, False)
        sent.assert_called_once()

    @pytest.mark.parametrize("mode,failed,stopped,title", [
        ("encrypt", 0, False, "Encryption complete"),
        ("encrypt", 1, False, "Encryption finished with errors"),
        ("decrypt", 0, True, "Decryption stopped"),
        ("decrypt", 2, True, "Decryption stopped"),
    ])
    def test_titles(self, sent, monkeypatch, mode, failed, stopped, title):
        self._state(monkeypatch, active=False)
        EncryptController(mode)._notify_complete(1.0, failed, stopped)
        assert sent.call_args[0][0] == title


class TestCancel:
    def test_cancel_marks_cancelling_until_finished(self, encryptor):
        worker = MagicMock()
        encryptor._worker = worker
        encryptor._busy = True
        encryptor.cancel()
        worker.cancel.assert_called_once()
        assert encryptor.cancelling
        encryptor.cancel()
        worker.cancel.assert_called_once()

    def test_cancel_stops_the_files_in_progress(self, encryptor):
        """Cancel reaches the worker's stop token, which the engines check once per block."""
        worker = EncryptDecryptWorker(["a.txt"], KeyRing("pw", _CHEAP_KDF))
        encryptor._worker = worker
        encryptor._busy = True
        encryptor.cancel()
        assert worker._stop.cancelled

    def test_cancel_without_worker_is_harmless(self, encryptor):
        encryptor.cancel()
        assert not encryptor.cancelling


class TestShowInFolder:
    """Show in folder asks the shell to select the file; no program is started by name (A3)."""

    @pytest.fixture
    def shell(self, monkeypatch):
        fake = MagicMock()
        fake.ILCreateFromPathW.return_value = 1234
        monkeypatch.setattr(encrypt_ctrl, "_shell32", fake)
        return fake

    def _row(self, controller, path) -> int:
        controller.fileModel.add_scanned([(str(path), 1)])
        return 0

    def test_selects_the_file_in_explorer(self, encryptor, shell, tmp_path):
        target = tmp_path / "report, final.txt"  # a comma used to break explorer /select,
        target.write_text("x")
        encryptor.showInFolder(self._row(encryptor, target))
        shell.ILCreateFromPathW.assert_called_once_with(os.path.normpath(str(target)))
        shell.SHOpenFolderAndSelectItems.assert_called_once_with(1234, 0, None, 0)
        shell.ILFree.assert_called_once_with(1234)

    def test_a_missing_file_opens_its_folder(self, encryptor, shell, tmp_path, monkeypatch):
        opened = []
        monkeypatch.setattr(encrypt_ctrl.os, "startfile", opened.append, raising=False)
        encryptor.showInFolder(self._row(encryptor, tmp_path / "gone.txt"))
        shell.ILCreateFromPathW.assert_not_called()
        assert opened == [str(tmp_path)]

    def test_a_shell_failure_is_a_notice(self, encryptor, shell, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        shell.SHOpenFolderAndSelectItems.side_effect = OSError("[WinError -2147024894] not found")
        notices = _notices(encryptor)
        encryptor.showInFolder(self._row(encryptor, target))
        shell.ILFree.assert_called_once_with(1234)
        assert notices == ["Couldn't open File Explorer for that file."]

    def test_no_shell_item_is_a_notice(self, encryptor, shell, tmp_path):
        target = tmp_path / "a.txt"
        target.write_text("x")
        shell.ILCreateFromPathW.return_value = None
        notices = _notices(encryptor)
        encryptor.showInFolder(self._row(encryptor, target))
        shell.SHOpenFolderAndSelectItems.assert_not_called()
        assert notices == ["Couldn't open File Explorer for that file."]

    def test_the_shell_functions_are_declared(self):
        assert encrypt_ctrl._shell32.SHOpenFolderAndSelectItems.restype is encrypt_ctrl.ctypes.HRESULT
        assert encrypt_ctrl._shell32.ILCreateFromPathW.restype is encrypt_ctrl.ctypes.c_void_p
