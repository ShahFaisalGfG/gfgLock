import glob
import os
from functools import partial
from typing import Callable, cast

import pytest
from PySide6.QtCore import QCoreApplication, Qt

from gfglock.core import aes256_gcm_cfb as aes_core
from gfglock.core import chacha20_poly1305 as xchacha_core
from gfglock.core import native_bridge
from gfglock.services import worker as worker_mod
from gfglock.services.worker import EncryptDecryptWorker, WorkerSignals
from gfglock.utils import predict_encrypted_size


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QCoreApplication exists so Qt signal delivery works in-process."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


class _Recorder:
    """Collects every argument tuple emitted by a connected Qt signal."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def _find_encrypted(directory: str, ext: str) -> str:
    """Locate the first encrypted file matching *{ext} in directory."""
    matches = glob.glob(os.path.join(directory, f"*{ext}"))
    assert matches, f"No *{ext} file found in {directory}"
    return matches[0]


def _as_partial(job: Callable) -> partial:
    """Narrow a _build_job() result to functools.partial for white-box inspection."""
    return cast(partial, job)


class TestWorkerSignals:
    """WorkerSignals must expose a working Signal for each stage of a job."""

    def test_all_signals_deliver_exact_arguments(self, qapp):
        """Every declared signal must deliver its emitted arguments unchanged to a slot."""
        signals = WorkerSignals()
        names = ("progress", "files_progress", "file_changed", "status", "error", "file_result", "finished")
        recorders = {name: _Recorder() for name in names}
        for name in names:
            getattr(signals, name).connect(recorders[name], Qt.ConnectionType.DirectConnection)

        signals.progress.emit(1.0, 2.0)
        signals.files_progress.emit(1, 2)
        signals.file_changed.emit("f.txt")
        signals.status.emit("running")
        signals.error.emit("oops")
        signals.file_result.emit(True, "ok")
        signals.finished.emit(1.5, 2, 1, 1, 0)

        assert recorders["progress"].calls == [(1.0, 2.0)]
        assert recorders["files_progress"].calls == [(1, 2)]
        assert recorders["file_changed"].calls == [("f.txt",)]
        assert recorders["status"].calls == [("running",)]
        assert recorders["error"].calls == [("oops",)]
        assert recorders["file_result"].calls == [(True, "ok")]
        assert recorders["finished"].calls == [(1.5, 2, 1, 1, 0)]


class TestCalcTotalSize:
    """_calc_total_size must predict encrypt output size or use raw size for decrypt."""

    def test_encrypt_uses_predicted_gcm_size(self, make_file, password):
        """Default GCM encrypt total_bytes must equal the predicted encrypted size."""
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        assert worker.total_bytes == pytest.approx(predict_encrypted_size(src, "GCM"))

    def test_encrypt_respects_cfb_algo(self, make_file, password):
        """An explicit CFB algo must switch the size prediction to CFB overhead."""
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_cfb")
        assert worker.total_bytes == pytest.approx(predict_encrypted_size(src, "CFB"))

    def test_encrypt_falls_back_to_settings_when_algo_missing(self, make_file, password, monkeypatch):
        """Without an explicit enc_algo, the encryption_mode setting must be consulted."""
        src = make_file()
        monkeypatch.setattr(
            worker_mod, "load_settings",
            lambda: {"advanced": {"encryption_mode": "chacha20_poly1305"}},
        )
        worker = EncryptDecryptWorker([src], password, mode="encrypt")
        assert worker.total_bytes == pytest.approx(predict_encrypted_size(src, "CHACHA"))

    def test_decrypt_uses_raw_file_size(self, make_file, password):
        """Decrypt-mode total_bytes must equal the actual on-disk file size."""
        src = make_file()
        size = os.path.getsize(src)
        worker = EncryptDecryptWorker([src], password, mode="decrypt")
        assert worker.total_bytes == pytest.approx(float(size))

    def test_nonexistent_path_floors_to_one(self, password):
        """An all-missing path list must still floor total_bytes at 1.0."""
        worker = EncryptDecryptWorker(["/no/such/file.bin"], password, mode="encrypt", enc_algo="aes256_gcm")
        assert worker.total_bytes == 1.0


class TestBuildJob:
    """_build_job must route each file to the correct encrypt/decrypt callable."""

    def test_encrypt_default_uses_gcm(self, make_file, password):
        """Default encrypt mode must build an AES job with AEAD=True."""
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        job = _as_partial(worker._build_job(src, lambda _b: None))
        assert job.func is aes_core.encrypt_file
        assert job.args[4] is True

    def test_encrypt_cfb_sets_aead_false(self, make_file, password):
        """aes256_cfb must build an AES job with AEAD=False."""
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_cfb")
        job = _as_partial(worker._build_job(src, lambda _b: None))
        assert job.func is aes_core.encrypt_file
        assert job.args[4] is False

    def test_encrypt_chacha_uses_chacha_core(self, make_file, password):
        """chacha20_poly1305 must route to the ChaCha20 encrypt function."""
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="chacha20_poly1305")
        job = _as_partial(worker._build_job(src, lambda _b: None))
        assert job.func is xchacha_core.encrypt_file

    def test_decrypt_gfglock_routes_to_aes(self, password):
        """A .gfglock path must route to the AES decrypt function."""
        worker = EncryptDecryptWorker(["file.gfglock"], password, mode="decrypt")
        job = _as_partial(worker._build_job("file.gfglock", lambda _b: None))
        assert job.func is aes_core.decrypt_file

    def test_decrypt_gfglck_routes_to_aes(self, password):
        """A .gfglck path must also route to the AES decrypt function."""
        worker = EncryptDecryptWorker(["file.gfglck"], password, mode="decrypt")
        job = _as_partial(worker._build_job("file.gfglck", lambda _b: None))
        assert job.func is aes_core.decrypt_file

    def test_decrypt_gfgcha_routes_to_chacha(self, password):
        """A .gfgcha path must route to the ChaCha20 decrypt function."""
        worker = EncryptDecryptWorker(["file.gfgcha"], password, mode="decrypt")
        job = _as_partial(worker._build_job("file.gfgcha", lambda _b: None))
        assert job.func is xchacha_core.decrypt_file

    def test_decrypt_unknown_extension_returns_skip_job(self, password):
        """An unrecognized extension must build a job that fails with a clear message."""
        worker = EncryptDecryptWorker(["plain.txt"], password, mode="decrypt")
        job = worker._build_job("plain.txt", lambda _b: None)
        ok, msg = job()
        assert ok is False
        assert "unknown encrypted file format" in msg.lower()


class TestIsSkip:
    """_is_skip must distinguish real failures from expected 'already done' outcomes."""

    def test_encrypt_message_already_encrypted_is_skip(self, password):
        """A message stating the file is already encrypted must count as a skip."""
        worker = EncryptDecryptWorker(["a.txt"], password, mode="encrypt")
        assert worker._is_skip("a.txt", "a.txt is already encrypted") is True

    def test_encrypt_extension_already_encrypted_is_skip(self, password):
        """An already-encrypted extension must count as a skip even without a message."""
        worker = EncryptDecryptWorker(["a.gfglock"], password, mode="encrypt")
        assert worker._is_skip("a.gfglock", "") is True

    def test_encrypt_real_failure_is_not_skip(self, password):
        """An unrelated failure message on a plain file must not count as a skip."""
        worker = EncryptDecryptWorker(["a.txt"], password, mode="encrypt")
        assert worker._is_skip("a.txt", "disk full") is False

    def test_decrypt_message_already_decrypted_is_skip(self, password):
        """A message stating the file is already decrypted must count as a skip."""
        worker = EncryptDecryptWorker(["a.gfglock"], password, mode="decrypt")
        assert worker._is_skip("a.gfglock", "a.gfglock is already decrypted") is True

    def test_decrypt_non_encrypted_extension_is_skip(self, password):
        """Trying to decrypt a non-encrypted extension must count as a skip."""
        worker = EncryptDecryptWorker(["a.txt"], password, mode="decrypt")
        assert worker._is_skip("a.txt", "") is True

    def test_decrypt_real_auth_failure_is_not_skip(self, password):
        """An authentication failure on a genuinely encrypted file must not count as a skip."""
        worker = EncryptDecryptWorker(["a.gfglock"], password, mode="decrypt")
        assert worker._is_skip("a.gfglock", "authentication failed") is False


class TestCancel:
    """cancel() must set the internal flag checked by run()'s processing loop."""

    def test_cancel_sets_flag(self, password):
        """cancel() must flip _cancelled from False to True."""
        worker = EncryptDecryptWorker(["a.txt"], password, mode="encrypt")
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True


class TestRun:
    """run() must drive the thread pool and emit accurate progress/result signals."""

    _SIGNAL_NAMES = ("progress", "files_progress", "file_changed", "status", "error", "file_result", "finished")

    def _connect(self, worker: EncryptDecryptWorker) -> dict:
        """Attach a direct-connection recorder to every signal on the worker."""
        recorders = {}
        for name in self._SIGNAL_NAMES:
            rec = _Recorder()
            getattr(worker.signals, name).connect(rec, Qt.ConnectionType.DirectConnection)
            recorders[name] = rec
        return recorders

    def test_encrypt_success_emits_finished_and_result(self, qapp, make_file, password, monkeypatch):
        """A clean encrypt run must report one success and the file must be renamed."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 1, 0, 0)
        assert elapsed >= 0
        assert recorders["file_result"].calls[0][0] is True
        assert recorders["file_changed"].calls == [(src,)]
        assert recorders["files_progress"].calls[-1] == (1, 1)
        assert recorders["progress"].calls[-1] == (worker.total_bytes, worker.total_bytes)
        assert not os.path.exists(src)

    def test_decrypt_success_emits_finished_and_result(self, qapp, make_file, password, monkeypatch):
        """A clean decrypt run of a previously encrypted file must report one success."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        ok, msg = aes_core.encrypt_file(src, password, AEAD=True)
        assert ok, msg
        enc_path = _find_encrypted(os.path.dirname(src), ".gfglock")
        worker = EncryptDecryptWorker([enc_path], password, mode="decrypt")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 1, 0, 0)
        assert recorders["file_result"].calls[0][0] is True

    def test_wrong_password_reports_failure(self, qapp, make_file, password, monkeypatch):
        """A wrong password on decrypt must count as a failure, not a skip."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        aes_core.encrypt_file(src, password, AEAD=True)
        enc_path = _find_encrypted(os.path.dirname(src), ".gfglock")
        worker = EncryptDecryptWorker([enc_path], "wrong-password", mode="decrypt")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 0, 1, 0)
        assert recorders["file_result"].calls[0][0] is False

    def test_already_encrypted_file_is_skipped(self, qapp, password, tmp_path, monkeypatch):
        """Re-encrypting an already-encrypted file must be counted as skipped, not failed."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / "already.gfglock"
        src.write_bytes(b"pretend-encrypted")
        worker = EncryptDecryptWorker([str(src)], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 0, 0, 1)

    def test_unknown_extension_decrypt_is_skipped(self, qapp, password, tmp_path):
        """Attempting to decrypt a plain file must be counted as skipped, not failed."""
        src = tmp_path / "plain.txt"
        src.write_bytes(b"just text")
        worker = EncryptDecryptWorker([str(src)], password, mode="decrypt")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 0, 0, 1)

    def test_cancelled_before_run_processes_nothing(self, qapp, make_file, password, monkeypatch):
        """Cancelling before run() starts must still emit finished, with zero completions."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        worker.cancel()
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 0, 0, 0)
        assert recorders["file_result"].calls == []
        assert os.path.exists(src)

    def test_job_exception_emits_error_and_counts_as_failed(self, qapp, make_file, password, monkeypatch):
        """An unexpected exception raised inside a job must emit error and count as failed."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)

        def raiser(*_args, **_kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(aes_core, "encrypt_file", raiser)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 0, 1, 0)
        assert recorders["error"].calls
        assert "disk exploded" in recorders["error"].calls[0][0]

    def test_multiple_files_report_final_counts(self, qapp, password, tmp_path, monkeypatch):
        """Multiple files must all be processed with files_progress reaching (n, n)."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        paths = []
        for i in range(3):
            p = tmp_path / f"file{i}.bin"
            p.write_bytes(os.urandom(256))
            paths.append(str(p))
        worker = EncryptDecryptWorker(paths, password, mode="encrypt", enc_algo="aes256_gcm", threads=2)
        recorders = self._connect(worker)
        worker.run()
        elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (3, 3, 0, 0)
        assert recorders["files_progress"].calls[-1] == (3, 3)
        assert len(recorders["file_changed"].calls) == 3
