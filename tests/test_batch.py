"""The run loop shared by the window and the command line (core/batch.py), and its Qt wrapper."""

import os
import threading
import time
from collections import Counter
from functools import partial
from typing import Callable, cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gfglock.core import batch, file_ops, locks, reasons
from gfglock.core.batch import (
    MIN_READ_SIZE,
    BatchRun,
    RunListener,
    RunOptions,
    RunResult,
    available_memory,
    capped_read_size,
    options_from_settings,
    space_shortages,
    summarize,
    time_left,
)
from gfglock.core.file_ops import FileResult
from gfglock.core.format_v2 import KeyRing
from gfglock.services.worker import EncryptDecryptWorker
from gfglock.utils import logging as log_mod

MB = 1024 * 1024


class Recorder(RunListener):
    """Collects every report of a run."""

    def __init__(self) -> None:
        self.progress_calls: list[tuple[int, int, float]] = []
        self.started: list[str] = []
        self.file_progress_calls: list[tuple[str, float]] = []
        self.results: list[tuple[str, FileResult]] = []
        self.temps: list[int] = []
        self.errors: list[str] = []
        self._lock = threading.Lock()

    def progress(self, done, total, eta):
        with self._lock:
            self.progress_calls.append((done, total, eta))

    def file_started(self, path):
        with self._lock:
            self.started.append(path)

    def file_progress(self, path, fraction):
        self.file_progress_calls.append((path, fraction))

    def file_result(self, path, result):
        with self._lock:
            self.results.append((path, result))

    def temps_removed(self, count):
        self.temps.append(count)

    def error(self, message):
        self.errors.append(message)


def _run(paths, keys, listener=None, **options) -> tuple[RunResult, BatchRun]:
    run = BatchRun(paths, keys, RunOptions(**options), listener)
    return run.run(), run


def _as_partial(job: Callable) -> partial:
    """Narrow a _build_job() result to functools.partial for white-box inspection."""
    return cast(partial, job)


@pytest.fixture(scope="session")
def qapp():
    """The suite's one QApplication."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fake_ops(monkeypatch):
    """Instant file operations: every file is 'encrypted' without touching it. Returns the call log."""
    calls: list[dict] = []

    def fake_encrypt(path, keys, algorithm, encrypt_name=False, read_size=0, progress=None, stop=None,
                     keep_original=False, output_dir=""):
        calls.append({"path": path, "algorithm": algorithm, "read_size": read_size, "stop": stop,
                      "keep_original": keep_original, "output_dir": output_dir})
        if progress:
            progress(float(os.path.getsize(path)) if os.path.exists(path) else 1.0)
        return FileResult(True, f"Encrypted: {path} -> {path}.gfglock", "done", output=f"{path}.gfglock")

    monkeypatch.setattr(batch.file_ops, "encrypt_file", fake_encrypt)
    monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda folders: 0)
    return calls


@pytest.fixture
def all_logs(monkeypatch):
    """Turn logging on at the 'Everything' level and return (critical, general) log paths."""
    monkeypatch.setattr(log_mod, "load_settings", lambda: {"advanced": {"enable_logs": True, "log_level": "all"}})
    return log_mod.get_critical_log_file(), log_mod.get_general_log_file()


def _read(path: str) -> str:
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


class TestOptions:
    def test_from_the_saved_settings(self, monkeypatch):
        monkeypatch.setattr(batch.os, "cpu_count", lambda: 8)
        settings = {"encryption": {"cpu_threads": 6, "read_size": 8 * MB, "encrypt_filenames": True,
                                   "keep_originals": True, "output_dir": "D:\\Vault"},
                    "advanced": {"encryption_mode": "chacha20_poly1305", "clamp_cpu_threads": True}}
        options = options_from_settings("encrypt", settings)
        assert options == RunOptions("encrypt", "chacha", True, 6, 8 * MB, True, "D:\\Vault")

    def test_given_values_win_and_threads_stay_within_the_cpu(self, monkeypatch):
        monkeypatch.setattr(batch.os, "cpu_count", lambda: 4)
        settings = {"encryption": {"encrypt_filenames": True, "keep_originals": True, "output_dir": "D:\\Vault"}}
        options = options_from_settings("encrypt", settings, algorithm="aes256_gcm", hide_names=False,
                                        threads=32, keep_originals=False, output_dir="")
        assert (options.algorithm, options.hide_names, options.threads) == ("gcm", False, 3)
        assert (options.keep_originals, options.output_dir) == (False, "")

    def test_cfb_or_an_unknown_method_means_the_default(self):
        assert options_from_settings("encrypt", {}, algorithm="aes256_cfb").algorithm == "gcm"

    def test_checking_writes_nowhere_and_hides_nothing(self):
        settings = {"decryption": {"output_dir": "D:\\Out", "keep_originals": True},
                    "encryption": {"encrypt_filenames": True}}
        options = options_from_settings("verify", settings)
        assert (options.output_dir, options.hide_names, options.replaces) == ("", False, False)


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

    def test_the_run_uses_the_capped_size(self, make_file, keys, fake_ops, monkeypatch):
        monkeypatch.setattr(batch, "available_memory", lambda: 64 * MB)
        _run([make_file()], keys, threads=4, read_size=32 * MB)
        assert fake_ops[0]["read_size"] == 1 * MB


class TestSpace:
    def test_a_drive_with_room_passes(self, tmp_path):
        assert space_shortages([(str(tmp_path / "a.bin"), 1000)], RunOptions(threads=2)) == []

    def test_replaced_originals_need_room_for_the_largest_files_at_once(self, tmp_path, monkeypatch):
        sizes = [(str(tmp_path / f"{i}.bin"), size * MB) for i, size in enumerate((10, 40, 30, 20))]
        monkeypatch.setattr(batch, "_free_space", lambda _folder: 1)
        replaced = space_shortages(sizes, RunOptions(threads=2))
        kept = space_shortages(sizes, RunOptions(threads=2, keep_originals=True))
        assert replaced[0].needed < kept[0].needed
        margin = file_ops.SPACE_MARGIN
        assert 70 * MB + margin < replaced[0].needed < 71 * MB + margin  # the 40 and 30 MB files at once
        assert 100 * MB + margin < kept[0].needed < 101 * MB + margin    # every result stays
        assert "Free up" in replaced[0].text() and replaced[0].drive in replaced[0].text()

    def test_checking_needs_no_space(self, tmp_path, monkeypatch):
        monkeypatch.setattr(batch, "_free_space", lambda _folder: 0)
        assert space_shortages([(str(tmp_path / "a.gfglock"), 10 * MB)], RunOptions("verify")) == []


class TestProgress:
    def test_totals_are_the_input_sizes(self, tmp_path, keys, fake_ops):
        paths = []
        for i, size in enumerate((1000, 3000)):
            path = tmp_path / f"f{i}.bin"
            path.write_bytes(bytes(size))
            paths.append(str(path))
        recorder = Recorder()
        _result, run = _run(paths + [str(tmp_path / "gone.txt")], keys, recorder)
        assert run.total_bytes == 4000
        assert recorder.progress_calls[-1][:2] == (4000, 4000)

    def test_per_file_progress_reports_whole_percents_once(self, tmp_path, keys):
        """0% shows when the file starts and 100% when its result arrives; only the steps between are sent."""
        src = str(tmp_path / "thousand.gfglock")
        with open(src, "wb") as fh:
            fh.write(bytes(1000))
        recorder = Recorder()
        run = BatchRun([src], keys, RunOptions("decrypt"), recorder)
        run._sizes[src] = 1000
        callback = run._make_progress_callback(src)
        for _ in range(4):
            callback(1.0)       # 0.1% each: still 0%
        callback(496.0)         # 50%
        callback(500.0)         # 100%
        callback(50.0)          # an engine counting past the size still reads 100%
        assert recorder.file_progress_calls == [(src, 0.5)]
        assert run._done_bytes == 1000

    def test_run_progress_is_sent_at_most_every_interval(self, tmp_path, keys, fake_ops):
        paths = []
        for i in range(300):
            (tmp_path / f"{i}.bin").write_bytes(b"x" * 10)
            paths.append(str(tmp_path / f"{i}.bin"))
        recorder = Recorder()
        start = time.monotonic()
        _run(paths, keys, recorder)
        bound = (time.monotonic() - start) / batch.PROGRESS_INTERVAL_S + 2
        assert len(recorder.progress_calls) <= bound
        assert recorder.progress_calls[-1][:2] == (3000, 3000)

    def test_a_failed_file_still_counts_as_processed(self, tmp_path, keys, monkeypatch):
        path = tmp_path / "a.bin"
        path.write_bytes(bytes(500))
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda folders: 0)
        monkeypatch.setattr(batch.file_ops, "encrypt_file",
                            lambda *a, **k: FileResult(False, "Critical error", "failed", "In use", category="in_use"))
        recorder = Recorder()
        result, _run_ = _run([str(path)], keys, recorder)
        assert recorder.progress_calls[-1][:2] == (500, 500)
        assert result.failures == Counter({"in_use": 1})

    @pytest.mark.parametrize("done,total,elapsed,expected", [
        (0, 100, 10.0, -1.0),    # nothing read yet
        (50, 100, 1.0, -1.0),    # too early to tell
        (25, 100, 10.0, 30.0),   # a quarter in 10 s: 30 s to go
        (100, 100, 10.0, -1.0),  # finished
    ])
    def test_time_left(self, done, total, elapsed, expected):
        assert time_left(done, total, elapsed) == expected


class TestBuildJob:
    """_build_job passes the run's keys, options, read size and stop token to file_ops."""

    def test_encrypt_job(self, make_file, keys):
        src = make_file()
        run = BatchRun([src], keys, RunOptions("encrypt", "chacha", hide_names=True, keep_originals=True,
                                               output_dir="D:\\Out"))
        job = _as_partial(run._build_job(src, 2 * MB))
        assert job.func is file_ops.encrypt_file
        assert job.args == (src, keys, "chacha")
        assert job.keywords["encrypt_name"] is True and job.keywords["read_size"] == 2 * MB
        assert job.keywords["keep_original"] is True and job.keywords["output_dir"] == "D:\\Out"
        assert job.keywords["stop"] is run._stop and callable(job.keywords["progress"])

    def test_decrypt_and_verify_jobs(self, keys):
        decrypt = _as_partial(BatchRun(["f.gfgcha"], keys, RunOptions("decrypt"))._build_job("f.gfgcha", 0))
        verify = _as_partial(BatchRun(["f.gfgcha"], keys, RunOptions("verify"))._build_job("f.gfgcha", 0))
        assert decrypt.func is file_ops.decrypt_file and decrypt.args == ("f.gfgcha", keys)
        assert verify.func is file_ops.verify_file and "output_dir" not in verify.keywords

    def test_constructor_does_not_touch_the_files(self, keys, monkeypatch):
        """Sizing happens in run(), off the GUI thread."""
        monkeypatch.setattr(batch.os.path, "getsize", lambda _p: pytest.fail("sized on construction"))
        BatchRun(["a.txt"] * 3, keys, RunOptions())


class TestCancel:
    def test_cancel_sets_the_flag_and_the_stop_token(self, keys):
        run = BatchRun(["a.txt"], keys, RunOptions())
        assert run.cancelled is False and not run._stop.cancelled
        run.cancel()
        assert run.cancelled is True and run._stop.cancelled

    def test_cancelled_before_run_processes_nothing(self, make_file, keys, fake_ops):
        src = make_file()
        recorder = Recorder()
        run = BatchRun([src], keys, RunOptions(), recorder)
        run.cancel()
        result = run.run()
        assert (result.total, result.done, result.failed, result.skipped, result.cancelled) == (1, 0, 0, 0, True)
        assert recorder.results == [] and fake_ops == []

    def test_a_full_drive_stops_the_rest_of_the_run(self, tmp_path, keys, monkeypatch):
        paths = []
        for i in range(5):
            (tmp_path / f"{i}.bin").write_bytes(b"x")
            paths.append(str(tmp_path / f"{i}.bin"))
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda folders: 0)
        monkeypatch.setattr(batch.file_ops, "encrypt_file", lambda *a, **k: FileResult(
            False, "Critical error", "failed", "The drive is full", category=reasons.DISK_FULL))
        result, _run_ = _run(paths, keys, threads=1)
        assert result.failed == 1 and result.cancelled and "is full" in result.halt
        assert "Free up space, then press Encrypt again." in summarize(result, "press Encrypt")


class TestRun:
    """run() drives the executor and reports each file once, with the totals at the end."""

    def test_results_and_counts(self, tmp_path, keys, fake_ops):
        paths = []
        for i in range(5):
            path = tmp_path / f"file{i}.bin"
            path.write_bytes(os.urandom(64))
            paths.append(str(path))
        recorder = Recorder()
        result, run = _run(paths, keys, recorder, threads=3)
        assert (result.total, result.done, result.failed, result.skipped) == (5, 5, 0, 0)
        assert sorted(recorder.started) == sorted(paths)
        assert sorted((path, res.outcome, res.output) for path, res in recorder.results) == sorted(
            (p, "done", f"{p}.gfglock") for p in paths)
        assert sorted(result.outputs) == sorted(f"{p}.gfglock" for p in paths)
        assert {call["algorithm"] for call in fake_ops} == {"gcm"}
        assert all(call["stop"] is run._stop for call in fake_ops)

    def test_job_exception_counts_as_failed_for_that_file(self, make_file, keys, monkeypatch, all_logs):
        def raiser(*_args, **_kwargs):
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(batch.file_ops, "encrypt_file", raiser)
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda folders: 0)
        recorder = Recorder()
        result, _run_ = _run([make_file()], keys, recorder)
        assert (result.done, result.failed) == (0, 1)
        _path, res = recorder.results[0]
        assert res.outcome == "failed" and res.category == "unknown" and res.output == ""
        assert "disk exploded" in _read(all_logs[0])

    def test_stale_temps_are_reported_once(self, make_file, keys, fake_ops, monkeypatch):
        folders = []
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda f: folders.append(list(f)) or 2)
        src = make_file()
        recorder = Recorder()
        _run([src, src.replace("payload", "other")], keys, recorder)
        assert recorder.temps == [2]
        assert folders == [[os.path.dirname(src)]]

    def test_the_output_folder_is_the_one_cleared(self, make_file, keys, fake_ops, monkeypatch, tmp_path):
        folders = []
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda f: folders.append(list(f)) or 0)
        out = tmp_path / "out"
        out.mkdir()
        _run([make_file()], keys, output_dir=str(out))
        assert folders == [[str(out)]]

    def test_checking_clears_nothing(self, make_file, keys, monkeypatch):
        folders = []
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda f: folders.append(list(f)) or 0)
        _run([make_file("x.gfglock")], keys, mode="verify")
        assert folders == [[]]

    def test_no_notice_when_no_temps_were_left(self, make_file, keys, fake_ops):
        recorder = Recorder()
        _run([make_file()], keys, recorder)
        assert recorder.temps == []

    def test_a_folder_in_use_by_another_run_is_not_cleared(self, make_file, keys, fake_ops, monkeypatch):
        """Temp files of a run in the other tab, or in the command line, are closed between steps;
        they must not count as leftovers."""
        cleared = []
        monkeypatch.setattr(batch.file_ops, "remove_stale_temps", lambda f: cleared.append(list(f)) or 0)
        src = make_file()
        with locks.claim_folders([os.path.dirname(src)]) as free:
            assert free == [os.path.dirname(src)]
            _run([src], keys)
        _run([src], keys)
        assert cleared == [[], [os.path.dirname(src)]]

    def test_the_run_log_pairs_no_hidden_name_with_its_original(self, make_file, keys, fake_ops, all_logs):
        """With Hide file names on, an encrypted file is logged by its new name only (A8)."""
        src = make_file("secret plan.txt")
        _run([src], keys, hide_names=True)
        general = _read(all_logs[1])
        assert f"Encrypted: {src}.gfglock" in general and "->" not in general

    def test_the_run_log_keeps_the_full_line_without_hidden_names(self, make_file, keys, fake_ops, all_logs):
        src = make_file("notes.txt")
        _run([src], keys)
        assert f"Encrypted: {src} -> {src}.gfglock" in _read(all_logs[1])

    def test_the_run_reads_the_settings_once(self, tmp_path, keys, fake_ops, monkeypatch):
        reads = []
        monkeypatch.setattr(log_mod, "load_settings", lambda: reads.append(1) or {"advanced": {}})
        paths = []
        for i in range(20):
            (tmp_path / f"{i}.txt").write_bytes(b"x")
            paths.append(str(tmp_path / f"{i}.txt"))
        _run(paths, keys)
        assert reads == [1]


class TestSummary:
    def _result(self, mode="encrypt", total=4, **counts) -> RunResult:
        return RunResult(mode, total, elapsed=2.1, **counts)

    def test_all_done_says_how_long(self):
        assert summarize(self._result(done=4), "press Encrypt") == "All 4 files encrypted in 2.1 s."
        assert summarize(self._result(total=1, done=1), "press Encrypt") == "1 file encrypted in 2.1 s."

    def test_failures_are_grouped_and_drop_the_timing(self):
        result = self._result("decrypt", 12, done=3, failed=9, failures=Counter({"in_use": 3, "wrong_password": 6}))
        assert summarize(result, "press Decrypt") == "3 of 12 files decrypted. 9 failed: 6 wrong password, 3 in use."

    def test_a_wrong_password_alone_is_named(self):
        result = self._result("decrypt", 3, failed=3, failures=Counter({"wrong_password": 3}))
        assert summarize(result, "press Decrypt") == "Wrong password. Nothing was changed."

    def test_a_check(self):
        assert summarize(self._result("verify", done=4), "press Check") == (
            "All 4 files checked in 2.1 s: the password is right and they're intact.")

    def test_a_stopped_run(self):
        result = self._result(done=1, skipped=1, cancelled=True)
        assert summarize(result, "press Encrypt") == "Stopped: 1 of 4 files encrypted, 1 skipped. The rest were not changed."


class TestRealFiles:
    """Runs through file_ops and the engine itself, with a cheap key ring."""

    def test_encrypt_then_check_then_decrypt(self, make_file, keys, sample_data):
        src = make_file("report.docx")
        result, _run_ = _run([src], keys, algorithm="gcm")
        assert (result.done, result.outputs) == (1, [src + ".gfglock"])
        assert not os.path.exists(src)

        checked, _run_ = _run(result.outputs, keys, mode="verify")
        assert checked.done == 1 and os.listdir(os.path.dirname(src)) == ["report.docx.gfglock"]

        decrypted, _run_ = _run(result.outputs, keys, mode="decrypt")
        assert decrypted.done == 1
        with open(src, "rb") as fh:
            assert fh.read() == sample_data

    def test_wrong_password_reports_failure_with_reason(self, make_file, keys):
        src = make_file()
        _run([src], keys)
        recorder = Recorder()
        result, _run_ = _run([src + ".gfglock"], KeyRing("wrong-password"), recorder, mode="decrypt")
        assert (result.done, result.failed, result.failures) == (0, 1, Counter({"wrong_password": 1}))
        _path, res = recorder.results[0]
        assert res.outcome == "failed" and res.output == "" and res.reason.startswith("Wrong password")

    def test_a_stopped_file_is_counted_apart_and_left_unchanged(self, make_file, keys, sample_data):
        """The stop token reaches the engine: the file in progress ends as stopped."""
        src = make_file()
        recorder = Recorder()
        run = BatchRun([src], keys, RunOptions(), recorder)
        run._stop.cancel()  # as if Stop was pressed just after the file started
        result = run.run()
        _path, res = recorder.results[0]
        assert (res.outcome, res.category, res.output) == ("skipped", "stopped", "")
        assert (result.stopped, result.skipped) == (1, 0)
        assert open(src, "rb").read() == sample_data
        assert [name for name in os.listdir(os.path.dirname(src)) if name.endswith(".gfgpart")] == []

    def test_threads_report_progress_without_losing_bytes(self, tmp_path, keys):
        paths = []
        for i in range(6):
            path = tmp_path / f"f{i}.bin"
            path.write_bytes(os.urandom(200_000))
            paths.append(str(path))
        recorder = Recorder()
        result, _run_ = _run(paths, keys, recorder, threads=3)
        assert result.done == 6
        assert recorder.progress_calls[-1][:2] == (1_200_000, 1_200_000)


class TestWorker:
    """The window's QRunnable passes the run's reports on as signals."""

    def test_signals_carry_the_run(self, qapp, make_file, keys, fake_ops):
        src = make_file()
        worker = EncryptDecryptWorker([src], keys, RunOptions())
        seen: dict[str, list] = {"progress": [], "file_started": [], "file_result": [], "finished": []}
        for name, calls in seen.items():
            getattr(worker.signals, name).connect(lambda *args, calls=calls: calls.append(args),
                                                  Qt.ConnectionType.DirectConnection)
        worker.run()
        assert seen["file_started"] == [(src,)]
        assert seen["file_result"] == [(src, "done", "", "", src + ".gfglock")]
        assert seen["progress"][-1][:2] == (float(len(open(src, "rb").read())),) * 2
        (result,), = seen["finished"]
        assert isinstance(result, RunResult) and result.done == 1

    def test_cancel_reaches_the_run(self, keys):
        worker = EncryptDecryptWorker(["a.txt"], keys, RunOptions())
        worker.cancel()
        assert worker.batch.cancelled
