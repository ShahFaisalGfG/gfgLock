# test_encrypt_ctrl.py - unit tests for gfglock.controllers.encrypt_ctrl

import os
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtWidgets import QApplication

from gfglock.controllers import encrypt_ctrl
from gfglock.controllers.encrypt_ctrl import EncryptController
from gfglock.models.file_model import FileListModel


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - EncryptController calls QApplication.clipboard(),
    so every test file shares this app type to avoid a bare QCoreApplication
    winning the session-wide singleton race depending on run order."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def quiet(monkeypatch):
    """Keep tests from writing log files or showing Windows notifications."""
    monkeypatch.setattr(encrypt_ctrl, "write_log", MagicMock())
    monkeypatch.setattr(encrypt_ctrl, "write_session_separator", MagicMock())
    monkeypatch.setattr(encrypt_ctrl, "send_notification", MagicMock())


@pytest.fixture
def encryptor(quiet):
    return EncryptController("encrypt")


@pytest.fixture
def decryptor(quiet):
    return EncryptController("decrypt")


def _notices(controller) -> list:
    notices: list = []
    controller.notice.connect(notices.append)
    return notices


def _wait_until_idle(controller, qt_app, timeout=20.0) -> None:
    """Let the worker run and deliver its queued signals until the controller is idle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        qt_app.processEvents()
        if not controller.busy:
            QThreadPool.globalInstance().waitForDone(1000)
            qt_app.processEvents()
            return
        time.sleep(0.01)
    pytest.fail("the run did not finish in time")


def _rows(model: FileListModel) -> list[tuple[str, str]]:
    """(status, message) for every row."""
    return [(model.data(model.index(r), FileListModel.StatusRole), model.data(model.index(r), FileListModel.MessageRole))
            for r in range(model.count)]


class TestModes:
    """Each controller accepts only the files its tab works on."""

    @pytest.mark.parametrize("path,allowed", [
        ("plain.txt", True), ("secret.gfglock", False), ("secret.GFGLCK", False), ("secret.gfgcha", False),
    ])
    def test_encrypt_tab_rejects_encrypted_files(self, encryptor, path, allowed):
        assert encryptor._isAllowed(path) is allowed

    @pytest.mark.parametrize("path,allowed", [("plain.txt", False), ("secret.gfglock", True)])
    def test_decrypt_tab_requires_encrypted_files(self, decryptor, path, allowed):
        assert decryptor._isAllowed(path) is allowed

    def test_unknown_mode_means_encrypt(self, quiet):
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
        assert [os.path.normpath(p) for p in encryptor.fileModel.getPaths()] == [os.path.normpath(str(plain))]
        assert notices == ["1 file already encrypted was left out. Use the Decrypt tab to open them."]

    def test_decrypt_tab_explains_left_out_files(self, decryptor, tmp_path):
        for name in ("a.txt", "b.txt"):
            (tmp_path / name).write_text("x")
        notices = _notices(decryptor)
        decryptor.addFiles([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])
        assert decryptor.fileModel.count == 0
        assert notices == ["2 files not encrypted by gfgLock were left out."]

    def test_add_folder_scans_and_filters(self, encryptor, tmp_path, qt_app):
        (tmp_path / "a.txt").write_text("x")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.gfglock").write_text("x")
        (sub / "c.txt").write_text("x")
        encryptor.addFolder(QUrl.fromLocalFile(str(tmp_path)).toString())
        assert QThreadPool.globalInstance().waitForDone(5000)
        qt_app.processEvents()
        found = {os.path.normpath(p) for p in encryptor.fileModel.getPaths()}
        assert found == {os.path.normpath(str(tmp_path / "a.txt")), os.path.normpath(str(sub / "c.txt"))}
        assert not encryptor.scanning

    def test_empty_folder_is_reported(self, decryptor, tmp_path, qt_app):
        (tmp_path / "a.txt").write_text("x")
        notices = _notices(decryptor)
        decryptor.addFolder(str(tmp_path))
        assert QThreadPool.globalInstance().waitForDone(5000)
        qt_app.processEvents()
        assert notices == ["No gfgLock-encrypted files in that folder."]

    def test_missing_folder_is_ignored(self, encryptor):
        encryptor.addFolder(QUrl.fromLocalFile("Z:\\does\\not\\exist").toString())
        assert not encryptor.scanning and encryptor.fileModel.count == 0

    def test_clear_files_empties_the_list(self, encryptor, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        encryptor.addFiles([str(tmp_path / "a.txt")])
        encryptor.clearFiles()
        assert encryptor.fileModel.count == 0


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
            worker = MagicMock()
            return worker

        monkeypatch.setattr(encrypt_ctrl, "EncryptDecryptWorker", fake_worker)
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: settings)
        controller._threadpool = MagicMock()
        return made

    def test_uses_decryption_preferences(self, decryptor, monkeypatch, tmp_path):
        (tmp_path / "a.gfglock").write_text("x")
        decryptor.addFiles([str(tmp_path / "a.gfglock")])
        made = self._capture_worker(decryptor, monkeypatch, {
            "decryption": {"cpu_threads": 2, "read_size": 8 * 1024 * 1024},
            "encryption": {"cpu_threads": 9, "read_size": 0},
            "advanced": {"clamp_cpu_threads": False},
        })
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 8)
        decryptor.start("pw", False, "")
        assert made["threads"] == 2 and made["read_size"] == 8 * 1024 * 1024 and made["mode"] == "decrypt"
        assert decryptor.busy

    def test_threads_are_clamped_to_leave_one_free(self, encryptor, monkeypatch, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        encryptor.addFiles([str(tmp_path / "a.txt")])
        made = self._capture_worker(encryptor, monkeypatch, {
            "encryption": {"cpu_threads": 20}, "advanced": {"clamp_cpu_threads": True},
        })
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 4)
        encryptor.start("pw", True, "aes256_cfb")
        assert made["threads"] == 3 and made["enc_algo"] == "aes256_cfb" and made["encrypt_name"] is True

    def test_no_password_or_no_files_does_nothing(self, encryptor, monkeypatch, tmp_path):
        made = self._capture_worker(encryptor, monkeypatch, {})
        encryptor.start("pw", False, "")
        (tmp_path / "a.txt").write_text("x")
        encryptor.addFiles([str(tmp_path / "a.txt")])
        encryptor.start("", False, "")
        assert made == {} and not encryptor.busy


class TestRuns:
    """End-to-end encrypt and decrypt runs through the worker, checked row by row."""

    def test_encrypt_then_decrypt_round_trip(self, encryptor, decryptor, tmp_path, qt_app, monkeypatch):
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}})
        source = tmp_path / "notes.txt"
        source.write_text("secret notes")
        encryptor.addFiles([str(source)])
        encryptor.start("correct horse", False, "aes256_gcm")
        _wait_until_idle(encryptor, qt_app)

        locked = tmp_path / "notes.txt.gfglock"
        assert locked.exists() and not source.exists()
        assert _rows(encryptor.fileModel) == [("done", "Saved as notes.txt.gfglock")]
        assert encryptor.summary.startswith("All 1 file encrypted in ")
        assert encryptor.lastFolder == str(tmp_path)
        assert encryptor.fileModel.runnableCount == 0

        decryptor.addFiles([str(locked)])
        decryptor.start("wrong password", False, "")
        _wait_until_idle(decryptor, qt_app)
        status, message = _rows(decryptor.fileModel)[0]
        assert status == "failed" and "wrong password" in message.lower()
        assert locked.exists()
        assert decryptor.summary.startswith("0 of 1 file decrypted") and "1 failed" in decryptor.summary

        # A failed file stays in the list and runs again with the right password.
        assert decryptor.fileModel.runnableCount == 1
        decryptor.start("correct horse", False, "")
        _wait_until_idle(decryptor, qt_app)
        assert _rows(decryptor.fileModel) == [("done", "Saved as notes.txt")]
        assert source.read_text() == "secret notes"

    def test_finished_rows_are_not_run_again(self, encryptor, tmp_path, qt_app, monkeypatch):
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {})
        (tmp_path / "a.txt").write_text("a")
        encryptor.addFiles([str(tmp_path / "a.txt")])
        encryptor.start("pw", False, "chacha20_poly1305")
        _wait_until_idle(encryptor, qt_app)
        (tmp_path / "b.txt").write_text("b")
        encryptor.addFiles([str(tmp_path / "b.txt")])
        assert encryptor.fileModel.runnableCount == 1
        encryptor.start("pw", False, "chacha20_poly1305")
        _wait_until_idle(encryptor, qt_app)
        assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt.gfgcha", "b.txt.gfgcha"]
        encryptor.fileModel.removeFinished()
        assert encryptor.fileModel.count == 0


class TestSummary:
    @pytest.mark.parametrize("args,expected", [
        ((2.04, 3, 3, 0, 0, False), "All 3 files encrypted in 2.0 s."),
        ((1.0, 4, 2, 1, 1, False), "2 of 4 files encrypted in 1.0 s, 1 failed, 1 skipped."),
        ((1.0, 5, 2, 0, 0, True), "Stopped after 2 files: 2 encrypted. The rest were not changed."),
    ])
    def test_summary_lines(self, encryptor, args, expected):
        assert encryptor._build_summary(*args) == expected

    def test_summary_clears_when_the_list_changes(self, encryptor, tmp_path):
        encryptor._summary = "All 1 file encrypted in 0.1 s."
        cleared = []
        encryptor.summaryChanged.connect(lambda: cleared.append(encryptor.summary))
        (tmp_path / "new.txt").write_text("x")
        encryptor.addFiles([str(tmp_path / "new.txt")])
        assert encryptor.summary == "" and cleared == [""]

    def test_notification_respects_preference(self, encryptor, monkeypatch):
        send = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "send_notification", send)
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}})
        encryptor._notify_complete(1, 0)
        send.assert_not_called()
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": True}})
        encryptor._notify_complete(1, 1)
        assert send.call_args[0][0] == "gfgLock - Encryption finished with errors"


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

    def test_cancel_without_worker_is_harmless(self, encryptor):
        encryptor.cancel()
        assert not encryptor.cancelling
