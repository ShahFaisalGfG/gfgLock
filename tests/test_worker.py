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


_SIGNAL_NAMES = ("progress", "files_progress", "file_started", "file_progress", "file_result", "error", "finished")


class TestWorkerSignals:
    def test_all_signals_deliver_exact_arguments(self, qapp):
        signals = WorkerSignals()
        recorders = {name: _Recorder() for name in _SIGNAL_NAMES}
        for name in _SIGNAL_NAMES:
            getattr(signals, name).connect(recorders[name], Qt.ConnectionType.DirectConnection)

        signals.progress.emit(1.0, 2.0)
        signals.files_progress.emit(1, 2)
        signals.file_started.emit("f.txt")
        signals.file_progress.emit("f.txt", 0.5)
        signals.file_result.emit("f.txt", "done", "", "f.txt.gfglock", "Encrypted")
        signals.error.emit("oops")
        signals.finished.emit(1.5, 2, 1, 1, 0)

        assert recorders["progress"].calls == [(1.0, 2.0)]
        assert recorders["files_progress"].calls == [(1, 2)]
        assert recorders["file_started"].calls == [("f.txt",)]
        assert recorders["file_progress"].calls == [("f.txt", 0.5)]
        assert recorders["file_result"].calls == [("f.txt", "done", "", "f.txt.gfglock", "Encrypted")]
        assert recorders["error"].calls == [("oops",)]
        assert recorders["finished"].calls == [(1.5, 2, 1, 1, 0)]


class TestCalcTotalSize:
    """_calc_total_size must predict encrypt output size or use raw size for decrypt."""

    def test_constructor_does_not_touch_the_files(self, password, monkeypatch):
        """Sizing happens in run(), off the GUI thread."""
        monkeypatch.setattr(worker_mod.os.path, "isfile", lambda _p: pytest.fail("sized on construction"))
        EncryptDecryptWorker(["a.txt"] * 3, password, mode="encrypt", enc_algo="aes256_gcm")

    def test_encrypt_uses_predicted_gcm_size(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        assert worker._calc_total_size() == pytest.approx(predict_encrypted_size(src, "GCM"))

    def test_encrypt_respects_cfb_algo(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_cfb")
        assert worker._calc_total_size() == pytest.approx(predict_encrypted_size(src, "CFB"))

    def test_encrypt_falls_back_to_settings_when_algo_missing(self, make_file, password, monkeypatch):
        src = make_file()
        monkeypatch.setattr(worker_mod, "load_settings", lambda: {"advanced": {"encryption_mode": "chacha20_poly1305"}})
        worker = EncryptDecryptWorker([src], password, mode="encrypt")
        assert worker.enc_algo == "chacha20_poly1305"
        assert worker._calc_total_size() == pytest.approx(predict_encrypted_size(src, "CHACHA"))

    def test_decrypt_uses_raw_file_size(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="decrypt")
        assert worker._calc_total_size() == pytest.approx(float(os.path.getsize(src)))

    def test_nonexistent_path_floors_to_one(self, password):
        worker = EncryptDecryptWorker(["/no/such/file.bin"], password, mode="encrypt", enc_algo="aes256_gcm")
        assert worker._calc_total_size() == 1.0


class TestBuildJob:
    """_build_job must route each file to the correct encrypt/decrypt callable."""

    def test_encrypt_default_uses_gcm(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        job = _as_partial(worker._build_job(src, lambda _b: None))
        assert job.func is aes_core.encrypt_file
        assert job.keywords["AEAD"] is True

    def test_encrypt_cfb_sets_aead_false(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_cfb")
        job = _as_partial(worker._build_job(src, lambda _b: None))
        assert job.func is aes_core.encrypt_file
        assert job.keywords["AEAD"] is False

    def test_encrypt_chacha_uses_chacha_core(self, make_file, password):
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="chacha20_poly1305")
        assert _as_partial(worker._build_job(src, lambda _b: None)).func is xchacha_core.encrypt_file

    @pytest.mark.parametrize("name,func", [
        ("file.gfglock", aes_core.decrypt_file),
        ("file.GFGLCK", aes_core.decrypt_file),
        ("file.gfgcha", xchacha_core.decrypt_file),
    ])
    def test_decrypt_routes_by_extension(self, password, name, func):
        worker = EncryptDecryptWorker([name], password, mode="decrypt")
        assert _as_partial(worker._build_job(name, lambda _b: None)).func is func

    def test_decrypt_unknown_extension_is_skipped(self, password):
        worker = EncryptDecryptWorker(["plain.txt"], password, mode="decrypt")
        result = worker._build_job("plain.txt", lambda _b: None)()
        ok, _msg = result
        assert ok is False
        assert (result.outcome, result.reason) == ("skipped", "Not an encrypted gfgLock file")


class TestProgress:
    def test_per_file_progress_reports_whole_percents_once(self, tmp_path, password, qapp):
        src = str(tmp_path / "thousand.gfglock")
        with open(src, "wb") as fh:
            fh.write(bytes(1000))
        worker = EncryptDecryptWorker([src], password, mode="decrypt")
        worker.total_bytes = worker._calc_total_size()  # as run() does before any file starts
        recorder = _Recorder()
        worker.signals.file_progress.connect(recorder, Qt.ConnectionType.DirectConnection)
        callback = worker._make_progress_callback(src)
        for _ in range(4):
            callback(1.0)       # 0.1% each: still 0%
        callback(496.0)         # 50%
        callback(500.0)         # 100%
        assert recorder.calls == [(src, 0.0), (src, 0.5), (src, 1.0)]


class TestCancel:
    def test_cancel_sets_flag(self, password):
        worker = EncryptDecryptWorker(["a.txt"], password, mode="encrypt")
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True


class TestRun:
    """run() must drive the thread pool and emit accurate progress/result signals."""

    def _connect(self, worker: EncryptDecryptWorker) -> dict:
        recorders = {}
        for name in _SIGNAL_NAMES:
            rec = _Recorder()
            getattr(worker.signals, name).connect(rec, Qt.ConnectionType.DirectConnection)
            recorders[name] = rec
        return recorders

    def test_encrypt_success_emits_finished_and_result(self, qapp, make_file, password, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        _elapsed, total, succeeded, failed, skipped = recorders["finished"].calls[0]
        assert (total, succeeded, failed, skipped) == (1, 1, 0, 0)
        path, outcome, reason, output, message = recorders["file_result"].calls[0]
        assert (path, outcome, reason) == (src, "done", "")
        assert output == src + ".gfglock" and os.path.exists(output)
        assert message.startswith("Encrypted: ")
        assert recorders["file_started"].calls == [(src,)]
        assert recorders["files_progress"].calls[-1] == (1, 1)
        assert recorders["progress"].calls[-1] == (worker.total_bytes, worker.total_bytes)
        assert not os.path.exists(src)

    def test_decrypt_success_emits_finished_and_result(self, qapp, make_file, password, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        ok, msg = aes_core.encrypt_file(src, password, AEAD=True)
        assert ok, msg
        enc_path = _find_encrypted(os.path.dirname(src), ".gfglock")
        worker = EncryptDecryptWorker([enc_path], password, mode="decrypt")
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 1, 0, 0)
        assert recorders["file_result"].calls[0][1] == "done"
        assert recorders["file_result"].calls[0][3] == src

    def test_wrong_password_reports_failure_with_reason(self, qapp, make_file, password, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        aes_core.encrypt_file(src, password, AEAD=True)
        enc_path = _find_encrypted(os.path.dirname(src), ".gfglock")
        worker = EncryptDecryptWorker([enc_path], "wrong-password", mode="decrypt")
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 1, 0)
        _path, outcome, reason, output, _message = recorders["file_result"].calls[0]
        assert outcome == "failed" and output == ""
        assert reason.startswith("Wrong password")

    def test_already_encrypted_file_is_skipped(self, qapp, password, tmp_path, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / "already.gfglock"
        src.write_bytes(b"pretend-encrypted")
        worker = EncryptDecryptWorker([str(src)], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 0, 1)
        assert recorders["file_result"].calls[0][1:3] == ("skipped", "Already encrypted")

    def test_missing_file_fails_with_reason(self, qapp, password, tmp_path):
        worker = EncryptDecryptWorker([str(tmp_path / "gone.txt")], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        assert recorders["file_result"].calls[0][1] == "failed"
        assert recorders["file_result"].calls[0][2].startswith("File not found")

    def test_cancelled_before_run_processes_nothing(self, qapp, make_file, password, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        worker.cancel()
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 0, 0)
        assert recorders["file_result"].calls == []
        assert os.path.exists(src)

    def test_job_exception_counts_as_failed_for_that_file(self, qapp, make_file, password, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)

        def raiser(*_args, **_kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(aes_core, "encrypt_file", raiser)
        src = make_file()
        worker = EncryptDecryptWorker([src], password, mode="encrypt", enc_algo="aes256_gcm")
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 1, 0)
        _path, outcome, reason, _output, message = recorders["file_result"].calls[0]
        assert outcome == "failed" and "disk exploded" in reason and "disk exploded" in message

    def test_multiple_files_report_final_counts(self, qapp, password, tmp_path, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        paths = []
        for i in range(3):
            p = tmp_path / f"file{i}.bin"
            p.write_bytes(os.urandom(256))
            paths.append(str(p))
        worker = EncryptDecryptWorker(paths, password, mode="encrypt", enc_algo="aes256_gcm", threads=2)
        recorders = self._connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (3, 3, 0, 0)
        assert recorders["files_progress"].calls[-1] == (3, 3)
        assert sorted(c[0] for c in recorders["file_started"].calls) == sorted(paths)
