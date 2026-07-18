# test_encrypt_ctrl.py - unit tests for gfglock.controllers.encrypt_ctrl

import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication

from gfglock.controllers import encrypt_ctrl
from gfglock.controllers.encrypt_ctrl import EncryptController


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-wide QApplication - EncryptController calls QApplication.clipboard(),
    so every test file shares this app type to avoid a bare QCoreApplication
    winning the session-wide singleton race depending on run order."""
    return QApplication.instance() or QApplication([])


def _raise(*_args, **_kwargs):
    """Stand-in for a monkeypatched call that must fail."""
    raise RuntimeError("simulated failure")


@pytest.fixture
def controller():
    """A fresh EncryptController with its real FileListModel."""
    return EncryptController()


class TestModeFiltering:
    """setMode()/_isAllowed() gate which files are accepted for the current operation."""

    @pytest.mark.parametrize("path,allowed", [
        ("plain.txt", True),
        ("secret.gfglock", False),
        ("secret.gfglck", False),
        ("secret.gfgcha", False),
    ])
    def test_encrypt_mode_rejects_encrypted_exts(self, controller, path, allowed):
        """In encrypt mode, only non-encrypted extensions are allowed."""
        controller.setMode("encrypt")
        assert controller._isAllowed(path) is allowed

    @pytest.mark.parametrize("path,allowed", [
        ("plain.txt", False),
        ("secret.gfglock", True),
    ])
    def test_decrypt_mode_requires_encrypted_ext(self, controller, path, allowed):
        """In decrypt mode, only encrypted extensions are allowed."""
        controller.setMode("decrypt")
        assert controller._isAllowed(path) is allowed

    def test_unknown_mode_allows_everything(self, controller):
        """An unrecognized mode falls back to allowing any path."""
        controller.setMode("preview")
        assert controller._isAllowed("anything.xyz") is True


class TestUrlToPath:
    """_url_to_path() must resolve file:// URLs and pass through plain strings."""

    def test_file_url_converted_to_local_path(self, tmp_path):
        """A file:/// URL must be converted to its local filesystem path."""
        target = tmp_path / "sample.txt"
        target.write_text("x")
        url = QUrl.fromLocalFile(str(target)).toString()
        result = EncryptController._url_to_path(url)
        assert os.path.normpath(result) == os.path.normpath(str(target))

    def test_non_url_string_passthrough(self):
        """A plain string with no recognizable URL scheme is returned unchanged."""
        assert EncryptController._url_to_path("not a url") == "not a url"


class TestFileManagementSlots:
    """File-management slots must filter by mode and delegate to the file model."""

    def test_add_files_filters_by_mode_and_converts_urls(self, controller, tmp_path):
        """addFiles() converts URLs and drops already-encrypted files in encrypt mode."""
        controller.setMode("encrypt")
        controller._file_model = MagicMock()
        plain = tmp_path / "plain.txt"
        plain.write_text("x")
        plain_url = QUrl.fromLocalFile(str(plain)).toString()
        encrypted_url = QUrl.fromLocalFile(str(tmp_path / "already.gfglock")).toString()

        controller.addFiles([plain_url, encrypted_url, ""])

        called_paths = controller._file_model.addFiles.call_args[0][0]
        assert len(called_paths) == 1
        assert os.path.normpath(called_paths[0]) == os.path.normpath(str(plain))

    def test_add_files_empty_list_still_calls_model(self, controller):
        """addFiles([]) must still invoke the model, with an empty list."""
        controller._file_model = MagicMock()
        controller.addFiles([])
        controller._file_model.addFiles.assert_called_once_with([])

    def test_add_files_swallows_failure(self, controller):
        """A file-model failure while adding files must not propagate."""
        controller._file_model = MagicMock()
        controller._file_model.addFiles.side_effect = RuntimeError("boom")
        try:
            controller.addFiles(["file:///x.txt"])
        except Exception as exc:
            pytest.fail(f"addFiles() must not raise: {exc}")

    def test_add_folder_walks_and_filters(self, controller, tmp_path):
        """addFolder() must walk the directory and keep only mode-allowed files."""
        controller.setMode("encrypt")
        (tmp_path / "a.txt").write_text("x")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.gfglock").write_text("x")
        (sub / "c.txt").write_text("x")
        controller._file_model = MagicMock()
        folder_url = QUrl.fromLocalFile(str(tmp_path)).toString()

        controller.addFolder(folder_url)

        called = {os.path.normpath(p) for p in controller._file_model.addFiles.call_args[0][0]}
        assert os.path.normpath(str(tmp_path / "a.txt")) in called
        assert os.path.normpath(str(sub / "c.txt")) in called
        assert os.path.normpath(str(sub / "b.gfglock")) not in called

    def test_add_folder_missing_directory_noop(self, controller):
        """A nonexistent folder must be silently ignored."""
        controller._file_model = MagicMock()
        controller.addFolder(QUrl.fromLocalFile("Z:\\does\\not\\exist").toString())
        controller._file_model.addFiles.assert_not_called()

    def test_add_path_respects_mode(self, controller, tmp_path):
        """addPath() must only add the file when it passes the mode filter."""
        controller.setMode("decrypt")
        controller._file_model = MagicMock()
        controller.addPath(str(tmp_path / "plain.txt"))
        controller._file_model.addFile.assert_not_called()
        controller.addPath(str(tmp_path / "secret.gfglock"))
        controller._file_model.addFile.assert_called_once_with(str(tmp_path / "secret.gfglock"))

    def test_remove_selected_delegates(self, controller):
        """removeSelected() must delegate to the file model."""
        controller._file_model = MagicMock()
        controller.removeSelected()
        controller._file_model.removeSelected.assert_called_once()

    def test_clear_files_delegates(self, controller):
        """clearFiles() must delegate to the file model."""
        controller._file_model = MagicMock()
        controller.clearFiles()
        controller._file_model.clearAll.assert_called_once()


class TestClipboardSlots:
    """copySelectedNames()/copySelectedPaths() must copy model text to the clipboard."""

    def test_copy_selected_names_sets_clipboard(self, controller, monkeypatch):
        """Non-empty selected-names text must be written to the clipboard."""
        controller._file_model = MagicMock()
        controller._file_model.getSelectedNamesText.return_value = "a.txt\nb.txt"
        fake_app = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "QApplication", fake_app)
        controller.copySelectedNames()
        fake_app.clipboard.return_value.setText.assert_called_once_with("a.txt\nb.txt")

    def test_copy_selected_names_skips_empty_text(self, controller, monkeypatch):
        """An empty selection must not touch the clipboard."""
        controller._file_model = MagicMock()
        controller._file_model.getSelectedNamesText.return_value = ""
        fake_app = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "QApplication", fake_app)
        controller.copySelectedNames()
        fake_app.clipboard.assert_not_called()

    def test_copy_selected_paths_sets_clipboard(self, controller, monkeypatch):
        """Non-empty selected-paths text must be written to the clipboard."""
        controller._file_model = MagicMock()
        controller._file_model.getSelectedPathsText.return_value = "C:\\a.txt"
        fake_app = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "QApplication", fake_app)
        controller.copySelectedPaths()
        fake_app.clipboard.return_value.setText.assert_called_once_with("C:\\a.txt")


class TestStartOperation:
    """startOperation() must validate state, resolve settings, and launch the worker."""

    _SETTINGS = {
        "encryption": {"cpu_threads": 3, "chunk_size": 4096},
        "advanced": {"clamp_cpu_threads": False, "encryption_mode": "aes256_gcm"},
    }

    def _ready_controller(self, controller, monkeypatch, settings=None):
        """Wire a controller with one queued path and stubbed settings/logging."""
        controller._file_model = MagicMock()
        controller._file_model.getPaths.return_value = ["a.txt"]
        controller._file_model.totalSize = "1.0 MB"
        monkeypatch.setattr(encrypt_ctrl, "load_settings", lambda: dict(settings or self._SETTINGS))
        log_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "write_log", log_mock)
        controller._threadpool = MagicMock()
        return controller, log_mock

    def test_noop_when_already_busy(self, controller):
        """A second call while busy must be ignored."""
        controller._busy = True
        controller._threadpool = MagicMock()
        controller._file_model = MagicMock()
        controller.startOperation("pw", "encrypt", False, 1, None, "aes256_gcm")
        controller._threadpool.start.assert_not_called()

    def test_noop_when_no_files(self, controller):
        """No files in the model must skip launching a worker entirely."""
        controller._file_model = MagicMock()
        controller._file_model.getPaths.return_value = []
        controller._threadpool = MagicMock()
        controller.startOperation("pw", "encrypt", False, 1, None, "aes256_gcm")
        controller._threadpool.start.assert_not_called()

    def test_launches_worker_with_resolved_settings(self, controller, monkeypatch):
        """Falsy threads/chunk_size/enc_algo must fall back to settings values."""
        controller, log_mock = self._ready_controller(controller, monkeypatch)
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 8)
        worker_cls = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "EncryptDecryptWorker", worker_cls)
        started_spy = MagicMock()
        busy_spy = MagicMock()
        controller.operationStarted.connect(started_spy)
        controller.busyChanged.connect(busy_spy)

        controller.startOperation("pw", "encrypt", True, 0, None, "")

        _, kwargs = worker_cls.call_args
        assert kwargs["paths"] == ["a.txt"]
        assert kwargs["password"] == "pw"
        assert kwargs["threads"] == 3
        assert kwargs["chunk_size"] == 4096
        assert kwargs["enc_algo"] == "aes256_gcm"
        assert controller.isBusy is True
        started_spy.assert_called_once()
        busy_spy.assert_called_once_with(True)
        controller._threadpool.start.assert_called_once_with(worker_cls.return_value)
        assert log_mock.call_count == 2

    def test_threads_clamped_when_enabled(self, controller, monkeypatch):
        """clamp_cpu_threads=True must reserve one CPU thread."""
        settings = {
            "encryption": {"cpu_threads": 1, "chunk_size": None},
            "advanced": {"clamp_cpu_threads": True, "encryption_mode": "aes256_gcm"},
        }
        controller, _ = self._ready_controller(controller, monkeypatch, settings)
        monkeypatch.setattr(encrypt_ctrl.os, "cpu_count", lambda: 8)
        worker_cls = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "EncryptDecryptWorker", worker_cls)

        controller.startOperation("pw", "encrypt", False, 20, None, "aes256_cfb")

        _, kwargs = worker_cls.call_args
        assert kwargs["threads"] == 7

    def test_error_path_emits_error_signal(self, controller, monkeypatch):
        """A worker-construction failure must emit errorOccurred and leave state unbusy."""
        controller, _ = self._ready_controller(controller, monkeypatch)
        monkeypatch.setattr(
            encrypt_ctrl, "EncryptDecryptWorker", MagicMock(side_effect=RuntimeError("boom"))
        )
        error_spy = MagicMock()
        controller.errorOccurred.connect(error_spy)

        controller.startOperation("pw", "encrypt", False, 1, None, "aes256_gcm")

        error_spy.assert_called_once_with("boom")
        assert controller.isBusy is False
        controller._threadpool.start.assert_not_called()


class TestCancelOperation:
    """cancelOperation() must forward the cancel request to an active worker."""

    def test_cancels_active_worker(self, controller):
        """An active worker's cancel() must be invoked."""
        controller._worker = MagicMock()
        controller.cancelOperation()
        controller._worker.cancel.assert_called_once()

    def test_noop_without_active_worker(self, controller):
        """No worker present must not raise."""
        controller._worker = None
        try:
            controller.cancelOperation()
        except Exception as exc:
            pytest.fail(f"cancelOperation() must not raise: {exc}")


class TestConnectWorker:
    """_connect_worker() must wire every worker signal to the matching controller signal."""

    def test_wires_all_signals_with_queued_connection(self, controller):
        """Each worker signal must be forwarded via a queued connection."""
        worker = MagicMock()
        controller._worker = worker
        controller._connect_worker()
        conn = Qt.ConnectionType.QueuedConnection
        worker.signals.progress.connect.assert_called_once_with(controller.progressChanged, conn)
        worker.signals.files_progress.connect.assert_called_once_with(controller.filesProgressChanged, conn)
        worker.signals.file_changed.connect.assert_called_once_with(controller.currentFileChanged, conn)
        worker.signals.status.connect.assert_called_once_with(controller.statusChanged, conn)
        worker.signals.error.connect.assert_called_once_with(controller.errorOccurred, conn)
        worker.signals.file_result.connect.assert_called_once_with(controller._log_file_result, conn)
        worker.signals.finished.connect.assert_called_once_with(controller._on_finished, conn)

    def test_noop_without_worker(self, controller):
        """No worker present must not raise."""
        controller._worker = None
        try:
            controller._connect_worker()
        except Exception as exc:
            pytest.fail(f"_connect_worker() must not raise: {exc}")


class TestLogFileResult:
    """_log_file_result() must always log generally, and additionally on failure."""

    def test_success_logs_general_only(self, controller, monkeypatch):
        """A successful result must only write to the general log."""
        log_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "write_log", log_mock)
        controller._log_file_result(True, "done")
        log_mock.assert_called_once_with("done", "general")

    def test_failure_logs_general_and_critical(self, controller, monkeypatch):
        """A failed result must additionally write to the critical log."""
        log_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "write_log", log_mock)
        controller._log_file_result(False, "oops")
        assert log_mock.call_args_list == [
            (("oops", "general"),),
            (("oops", "critical"),),
        ]


class TestOnFinished:
    """_on_finished() must reset busy state, log a summary, and emit operationFinished."""

    def test_success_summary_no_critical_log(self, controller, monkeypatch):
        """A run with zero failures must not touch the critical log."""
        controller._busy = True
        controller._worker = MagicMock()
        log_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "write_log", log_mock)
        monkeypatch.setattr(encrypt_ctrl, "write_session_separator", MagicMock())
        monkeypatch.setattr(
            encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}}
        )
        finished_spy = MagicMock()
        controller.operationFinished.connect(finished_spy)

        controller._on_finished(1.5, 2, 2, 0, 0)

        assert controller.isBusy is False
        assert controller._worker is None
        log_mock.assert_called_once()
        assert log_mock.call_args[0][1] == "general"
        finished_spy.assert_called_once_with(1.5, 2, 2, 0, 0)

    def test_failure_summary_also_writes_critical_log(self, controller, monkeypatch):
        """A run with failures must additionally write the critical log."""
        log_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "write_log", log_mock)
        monkeypatch.setattr(encrypt_ctrl, "write_session_separator", MagicMock())
        monkeypatch.setattr(
            encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}}
        )

        controller._on_finished(1.0, 3, 1, 2, 0)

        assert log_mock.call_count == 2
        assert log_mock.call_args_list[1][0][1] == "critical"

    def test_swallows_internal_failure(self, controller, monkeypatch):
        """A logging failure mid-summary must not propagate, and busy is still cleared."""
        controller._busy = True
        monkeypatch.setattr(encrypt_ctrl, "write_log", _raise)
        finished_spy = MagicMock()
        controller.operationFinished.connect(finished_spy)
        try:
            controller._on_finished(1.0, 1, 1, 0, 0)
        except Exception as exc:
            pytest.fail(f"_on_finished() must not raise: {exc}")
        assert controller.isBusy is False
        finished_spy.assert_not_called()


class TestNotifyComplete:
    """_notify_complete() must respect the notification setting and word the message correctly."""

    def test_disabled_setting_skips_notification(self, controller, monkeypatch):
        """operation_notifications == False must skip sending any notification."""
        monkeypatch.setattr(
            encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": False}}
        )
        notify_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "send_notification", notify_mock)
        controller._notify_complete(1.0, 1, 0, 0)
        notify_mock.assert_not_called()

    def test_all_succeeded_message(self, controller, monkeypatch):
        """A fully successful encrypt run must report a simple success message."""
        monkeypatch.setattr(
            encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": True}}
        )
        notify_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "send_notification", notify_mock)
        controller._operation_mode = "encrypt"
        controller._notify_complete(2.0, 3, 0, 0)
        title, body = notify_mock.call_args[0]
        assert "Encryption Complete" in title
        assert "3 file(s) encrypted" in body

    def test_partial_failure_message(self, controller, monkeypatch):
        """A run with failures must report the ok/failed/skipped breakdown."""
        monkeypatch.setattr(
            encrypt_ctrl, "load_settings", lambda: {"advanced": {"operation_notifications": True}}
        )
        notify_mock = MagicMock()
        monkeypatch.setattr(encrypt_ctrl, "send_notification", notify_mock)
        controller._operation_mode = "decrypt"
        controller._notify_complete(2.0, 1, 1, 1)
        title, body = notify_mock.call_args[0]
        assert "Decryption Complete" in title
        assert "1 ok" in body and "1 failed" in body and "1 skipped" in body

    def test_swallows_settings_failure(self, controller, monkeypatch):
        """A load_settings() failure must not propagate."""
        monkeypatch.setattr(encrypt_ctrl, "load_settings", _raise)
        try:
            controller._notify_complete(1.0, 1, 0, 0)
        except Exception as exc:
            pytest.fail(f"_notify_complete() must not raise: {exc}")


class TestSetBusy:
    """_set_busy() must emit busyChanged only on an actual state transition."""

    def test_emits_on_change(self, controller):
        """Toggling busy from False to True must emit once."""
        spy = MagicMock()
        controller.busyChanged.connect(spy)
        controller._set_busy(True)
        spy.assert_called_once_with(True)
        assert controller.isBusy is True

    def test_no_emit_when_unchanged(self, controller):
        """Setting busy to its current value must not emit."""
        spy = MagicMock()
        controller.busyChanged.connect(spy)
        controller._set_busy(False)
        spy.assert_not_called()


class TestProperties:
    """Property getters must expose internal state as-is."""

    def test_file_model_property_identity(self, controller):
        """fileModel must return the same FileListModel instance created in __init__."""
        assert controller.fileModel is controller._file_model

    def test_is_busy_reflects_internal_flag(self, controller):
        """isBusy must mirror the private _busy flag."""
        assert controller.isBusy is False
        controller._busy = True
        assert controller.isBusy is True
