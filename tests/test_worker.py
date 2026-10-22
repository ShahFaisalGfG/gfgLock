import os
import time
from functools import partial
from typing import Callable, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gfglock.core import file_ops
from gfglock.core.file_ops import FileResult
from gfglock.core.format_v2 import KeyRing
from gfglock.services import worker as worker_mod
from gfglock.services.worker import (
    MIN_READ_SIZE,
    EncryptDecryptWorker,
    WorkerSignals,
    available_memory,
    capped_read_size,
)
from gfglock.utils import logging as log_mod

MB = 1024 * 1024
_SIGNAL_NAMES = ("progress", "file_started", "file_progress", "file_result", "temps_removed", "error", "finished")


@pytest.fixture(scope="session")
def qapp():
    """The suite's one QApplication: a bare QCoreApplication made here first would break the tests
    that need a GUI application (icons, the clipboard)."""
    return QApplication.instance() or QApplication([])


class _Recorder:
    """Collects every argument tuple emitted by a connected Qt signal."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def _connect(worker: EncryptDecryptWorker) -> dict[str, _Recorder]:
    recorders = {name: _Recorder() for name in _SIGNAL_NAMES}
    for name, recorder in recorders.items():
        getattr(worker.signals, name).connect(recorder, Qt.ConnectionType.DirectConnection)
    return recorders


def _as_partial(job: Callable) -> partial:
    """Narrow a _build_job() result to functools.partial for white-box inspection."""
    return cast(partial, job)


@pytest.fixture
def fake_ops(monkeypatch):
    """Instant file operations: every file is 'encrypted' without touching it. Returns the call log."""
    calls: list[dict] = []

    def fake_encrypt(path, keys, algorithm, encrypt_name=False, read_size=0, progress=None, stop=None):
        calls.append({"path": path, "algorithm": algorithm, "read_size": read_size, "stop": stop})
        if progress:
            progress(float(os.path.getsize(path)) if os.path.exists(path) else 1.0)
        return FileResult(True, f"Encrypted: {path} -> {path}.gfglock", "done", output=f"{path}.gfglock")

    monkeypatch.setattr(worker_mod.file_ops, "encrypt_file", fake_encrypt)
    monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda folders: 0)
    return calls


@pytest.fixture
def all_logs(monkeypatch):
    """Turn logging on at the 'Everything' level and return (critical, general) log paths."""
    monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "all"}})
    return log_mod.get_critical_log_file(), log_mod.get_general_log_file()


def _read(path: str) -> str:
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


class TestWorkerSignals:
    def test_all_signals_deliver_exact_arguments(self, qapp):
        signals = WorkerSignals()
        recorders = {name: _Recorder() for name in _SIGNAL_NAMES}
        for name in _SIGNAL_NAMES:
            getattr(signals, name).connect(recorders[name], Qt.ConnectionType.DirectConnection)

        signals.progress.emit(1.0, 2.0)
        signals.file_started.emit("f.txt")
        signals.file_progress.emit("f.txt", 0.5)
        signals.file_result.emit("f.txt", "done", "", "f.txt.gfglock")
        signals.temps_removed.emit(3)
        signals.error.emit("oops")
        signals.finished.emit(1.5, 2, 1, 1, 0)

        assert recorders["progress"].calls == [(1.0, 2.0)]
        assert recorders["file_started"].calls == [("f.txt",)]
        assert recorders["file_progress"].calls == [("f.txt", 0.5)]
        assert recorders["file_result"].calls == [("f.txt", "done", "", "f.txt.gfglock")]
        assert recorders["temps_removed"].calls == [(3,)]
        assert recorders["error"].calls == [("oops",)]
        assert recorders["finished"].calls == [(1.5, 2, 1, 1, 0)]


class TestReadSizeCap:
    """threads x 8 buffers x read size stays within a quarter of the free memory."""

    @pytest.mark.parametrize("read_size,threads,available,expected", [
        (0, 4, 16 * 1024 * MB, 0),               # plenty of memory: the default stays the default
        (64 * MB, 4, 16 * 1024 * MB, 64 * MB),  # 4 x 8 x 64 MB = 2 GB of 16 GB: allowed
        (64 * MB, 8, 1024 * MB, 4 * MB),        # 1 GB free: 8 threads x 8 buffers share 256 MB
        (0, 16, 1024 * MB, 2 * MB),             # the default (4 MB) is lowered too
        (16 * MB, 64, 64 * MB, 1 * MB),         # never below 1 MiB
        (8 * MB, 3, 400 * MB, 4 * MB),          # 400 MB / 4 / 24 = 4.17 MB, rounded down to whole MiB
        (8 * MB, 2, None, 8 * MB),               # free memory unknown: as chosen
    ])
    def test_cap(self, read_size, threads, available, expected):
        assert capped_read_size(read_size, threads, available) == expected

    def test_never_above_the_chosen_size(self):
        for available in (MB, 100 * MB, 10**12):
            assert capped_read_size(2 * MB, 1, available) <= 2 * MB

    def test_free_memory_is_measured(self):
        free = available_memory()
        assert free is not None and free > MIN_READ_SIZE

    def test_the_run_uses_the_capped_size(self, qapp, make_file, keys, fake_ops, monkeypatch):
        monkeypatch.setattr(worker_mod, "available_memory", lambda: 64 * MB)
        worker = EncryptDecryptWorker([make_file()], keys, threads=4, read_size=32 * MB)
        worker.run()
        assert fake_ops[0]["read_size"] == 1 * MB


class TestProgress:
    def test_totals_are_the_input_sizes(self, qapp, tmp_path, keys, fake_ops):
        paths = []
        for i, size in enumerate((1000, 3000)):
            path = tmp_path / f"f{i}.bin"
            path.write_bytes(bytes(size))
            paths.append(str(path))
        worker = EncryptDecryptWorker(paths + [str(tmp_path / "gone.txt")], keys)
        recorders = _connect(worker)
        worker.run()
        assert worker.total_bytes == 4000
        assert recorders["progress"].calls[-1] == (4000.0, 4000.0)

    def test_per_file_progress_reports_whole_percents_once(self, qapp, tmp_path, keys):
        """0% shows when the file starts and 100% when its result arrives; only the steps between are sent."""
        src = str(tmp_path / "thousand.gfglock")
        with open(src, "wb") as fh:
            fh.write(bytes(1000))
        worker = EncryptDecryptWorker([src], keys, mode="decrypt")
        worker._sizes[src] = 1000
        recorder = _Recorder()
        worker.signals.file_progress.connect(recorder, Qt.ConnectionType.DirectConnection)
        callback = worker._make_progress_callback(src)
        for _ in range(4):
            callback(1.0)       # 0.1% each: still 0%
        callback(496.0)         # 50%
        callback(500.0)         # 100%
        callback(50.0)          # an engine counting past the size still reads 100%
        assert recorder.calls == [(src, 0.5)]
        assert worker._done_bytes == 1000

    def test_run_progress_is_sent_at_most_every_interval(self, qapp, tmp_path, keys, fake_ops):
        paths = []
        for i in range(300):
            (tmp_path / f"{i}.bin").write_bytes(b"x" * 10)
            paths.append(str(tmp_path / f"{i}.bin"))
        worker = EncryptDecryptWorker(paths, keys)
        recorders = _connect(worker)
        start = time.monotonic()
        worker.run()
        bound = (time.monotonic() - start) / worker_mod.PROGRESS_INTERVAL_S + 2
        assert len(recorders["progress"].calls) <= bound
        assert recorders["progress"].calls[-1] == (3000.0, 3000.0)

    def test_a_failed_file_still_counts_as_processed(self, qapp, tmp_path, keys, monkeypatch):
        path = tmp_path / "a.bin"
        path.write_bytes(bytes(500))
        monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda folders: 0)
        monkeypatch.setattr(worker_mod.file_ops, "encrypt_file",
                            lambda *a, **k: FileResult(False, "Critical error", "failed", "Disk full"))
        worker = EncryptDecryptWorker([str(path)], keys)
        recorders = _connect(worker)
        worker.run()
        assert recorders["progress"].calls[-1] == (500.0, 500.0)


class TestBuildJob:
    """_build_job passes the run's keys, algorithm, read size and stop token to file_ops."""

    def test_encrypt_job(self, make_file, keys):
        src = make_file()
        worker = EncryptDecryptWorker([src], keys, mode="encrypt", encrypt_name=True, algorithm="chacha")
        job = _as_partial(worker._build_job(src, 2 * MB))
        assert job.func is file_ops.encrypt_file
        assert job.args == (src, keys, "chacha")
        assert job.keywords["encrypt_name"] is True and job.keywords["read_size"] == 2 * MB
        assert job.keywords["stop"] is worker._stop and callable(job.keywords["progress"])

    def test_decrypt_job(self, keys):
        worker = EncryptDecryptWorker(["file.gfgcha"], keys, mode="decrypt")
        job = _as_partial(worker._build_job("file.gfgcha", 0))
        assert job.func is file_ops.decrypt_file
        assert job.args == ("file.gfgcha", keys)
        assert job.keywords["stop"] is worker._stop

    def test_constructor_does_not_touch_the_files(self, keys, monkeypatch):
        """Sizing happens in run(), off the GUI thread."""
        monkeypatch.setattr(worker_mod.os.path, "getsize", lambda _p: pytest.fail("sized on construction"))
        EncryptDecryptWorker(["a.txt"] * 3, keys)


class TestCancel:
    def test_cancel_sets_the_flag_and_the_stop_token(self, keys):
        worker = EncryptDecryptWorker(["a.txt"], keys)
        assert worker._cancelled is False and not worker._stop.cancelled
        worker.cancel()
        assert worker._cancelled is True and worker._stop.cancelled

    def test_cancelled_before_run_processes_nothing(self, qapp, make_file, keys, fake_ops):
        src = make_file()
        worker = EncryptDecryptWorker([src], keys)
        worker.cancel()
        recorders = _connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 0, 0)
        assert recorders["file_result"].calls == [] and fake_ops == []


class TestRun:
    """run() drives the executor and reports each file once, with the totals at the end."""

    def test_results_and_counts(self, qapp, tmp_path, keys, fake_ops):
        paths = []
        for i in range(5):
            path = tmp_path / f"file{i}.bin"
            path.write_bytes(os.urandom(64))
            paths.append(str(path))
        worker = EncryptDecryptWorker(paths, keys, threads=3)
        recorders = _connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (5, 5, 0, 0)
        assert sorted(c[0] for c in recorders["file_started"].calls) == sorted(paths)
        assert sorted(recorders["file_result"].calls) == sorted((p, "done", "", f"{p}.gfglock") for p in paths)
        assert {call["algorithm"] for call in fake_ops} == {"gcm"}
        assert all(call["stop"] is worker._stop for call in fake_ops)

    def test_job_exception_counts_as_failed_for_that_file(self, qapp, make_file, keys, monkeypatch, all_logs):
        def raiser(*_args, **_kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(worker_mod.file_ops, "encrypt_file", raiser)
        monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda folders: 0)
        src = make_file()
        worker = EncryptDecryptWorker([src], keys)
        recorders = _connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 1, 0)
        _path, outcome, reason, output = recorders["file_result"].calls[0]
        assert outcome == "failed" and "disk exploded" in reason and output == ""
        assert "disk exploded" in _read(all_logs[0])

    def test_stale_temps_are_reported_once(self, qapp, make_file, keys, fake_ops, monkeypatch):
        folders = []
        monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda f: folders.append(list(f)) or 2)
        src = make_file()
        worker = EncryptDecryptWorker([src, src.replace("payload", "other")], keys)
        recorders = _connect(worker)
        worker.run()
        assert recorders["temps_removed"].calls == [(2,)]
        assert folders == [[os.path.dirname(src)]]

    def test_no_notice_when_no_temps_were_left(self, qapp, make_file, keys, fake_ops):
        worker = EncryptDecryptWorker([make_file()], keys)
        recorders = _connect(worker)
        worker.run()
        assert recorders["temps_removed"].calls == []

    def test_a_folder_in_use_by_another_run_is_not_cleared(self, qapp, make_file, keys, fake_ops, monkeypatch):
        """Temp files of a run in the other tab are closed between steps; they must not count as leftovers."""
        cleared = []
        monkeypatch.setattr(worker_mod.file_ops, "remove_stale_temps", lambda f: cleared.append(list(f)) or 0)
        src = make_file()
        with worker_mod._claim_folders([os.path.dirname(src)]) as free:
            assert free == [os.path.dirname(src)]
            EncryptDecryptWorker([src], keys).run()
        EncryptDecryptWorker([src], keys).run()
        assert cleared == [[], [os.path.dirname(src)]]
        assert worker_mod._claims == {}

    def test_the_run_log_pairs_no_hidden_name_with_its_original(self, qapp, make_file, keys, fake_ops, all_logs):
        """With Hide file names on, an encrypted file is logged by its new name only (A8)."""
        src = make_file("secret plan.txt")
        EncryptDecryptWorker([src], keys, encrypt_name=True).run()
        general = _read(all_logs[1])
        assert f"Encrypted: {src}.gfglock" in general and "->" not in general

    def test_the_run_log_keeps_the_full_line_without_hidden_names(self, qapp, make_file, keys, fake_ops, all_logs):
        src = make_file("notes.txt")
        EncryptDecryptWorker([src], keys).run()
        assert f"Encrypted: {src} -> {src}.gfglock" in _read(all_logs[1])

    def test_the_run_reads_the_settings_once(self, qapp, tmp_path, keys, fake_ops, monkeypatch):
        reads = []
        monkeypatch.setattr(log_mod, "load_settings", lambda: reads.append(1) or {"advanced": {}})
        paths = []
        for i in range(20):
            (tmp_path / f"{i}.txt").write_bytes(b"x")
            paths.append(str(tmp_path / f"{i}.txt"))
        EncryptDecryptWorker(paths, keys).run()
        assert reads == [1]


class TestRealFiles:
    """Runs through file_ops and the engine itself, with a cheap key ring."""

    def test_encrypt_then_decrypt(self, qapp, make_file, keys, sample_data):
        src = make_file("report.docx")
        encrypt = EncryptDecryptWorker([src], keys, algorithm="gcm")
        recorders = _connect(encrypt)
        encrypt.run()
        assert recorders["finished"].calls[0][1:] == (1, 1, 0, 0)
        path, outcome, reason, output = recorders["file_result"].calls[0]
        assert (path, outcome, reason, output) == (src, "done", "", src + ".gfglock")
        assert not os.path.exists(src)

        decrypt = EncryptDecryptWorker([output], keys, mode="decrypt")
        recorders = _connect(decrypt)
        decrypt.run()
        assert recorders["file_result"].calls[0][1] == "done"
        with open(src, "rb") as fh:
            assert fh.read() == sample_data

    def test_wrong_password_reports_failure_with_reason(self, qapp, make_file, keys):
        src = make_file()
        EncryptDecryptWorker([src], keys).run()
        worker = EncryptDecryptWorker([src + ".gfglock"], KeyRing("wrong-password"), mode="decrypt")
        recorders = _connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (1, 0, 1, 0)
        _path, outcome, reason, output = recorders["file_result"].calls[0]
        assert outcome == "failed" and output == "" and "wrong password" in reason.lower()

    def test_a_stopped_file_is_skipped_and_left_unchanged(self, qapp, make_file, keys, sample_data):
        """The stop token reaches the engine: the file in progress ends as skipped."""
        src = make_file()
        worker = EncryptDecryptWorker([src], keys)
        recorders = _connect(worker)
        worker._stop.cancel()  # as if Stop was pressed just after the file started
        worker.run()
        _path, outcome, reason, output = recorders["file_result"].calls[0]
        assert (outcome, output) == ("skipped", "") and reason.startswith("Stopped")
        assert open(src, "rb").read() == sample_data
        assert [name for name in os.listdir(os.path.dirname(src)) if name.endswith(".gfgpart")] == []

    def test_threads_report_progress_without_losing_bytes(self, qapp, tmp_path, keys):
        paths = []
        for i in range(6):
            path = tmp_path / f"f{i}.bin"
            path.write_bytes(os.urandom(200_000))
            paths.append(str(path))
        worker = EncryptDecryptWorker(paths, keys, threads=3)
        recorders = _connect(worker)
        worker.run()
        assert recorders["finished"].calls[0][1:] == (6, 6, 0, 0)
        assert recorders["progress"].calls[-1] == (1_200_000.0, 1_200_000.0)
