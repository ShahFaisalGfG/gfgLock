# test_read_size_test.py - unit tests for gfglock.services.read_size_test (the Preferences speed test)

import os
from collections import namedtuple
from types import SimpleNamespace

import pytest

from gfglock.config.defaults import ReadSizeDefaults
from gfglock.core.file_ops import FileResult
from gfglock.core.format_v2 import KdfParams, KeyRing
from gfglock.core.py_cipher import CancelToken
from gfglock.services import read_size_test
from gfglock.services.read_size_test import (
    ReadSizeTestCancelled,
    ReadSizeTestError,
    ReadSizeTestWorker,
    SpeedResult,
    evict_cache,
    pick_fastest,
    remove_stale,
    run_speed_test,
    thread_counts,
)

MB = 1024 * 1024
DEFAULT = ReadSizeDefaults.DEFAULT_BYTES
# Seconds the fake engine needs to read the large file at each read size; 16 MB is clearly fastest
# for encrypting, while for decrypting nothing beats the default by 5%.
ENCRYPT_READ = {1 * MB: 1.0, 4 * MB: 1.0, 8 * MB: 0.9, 16 * MB: 0.5, 32 * MB: 0.6, 64 * MB: 0.7}
DECRYPT_READ = {size: 1.0 for size in ENCRYPT_READ} | {8 * MB: 0.97}
# Flushing the large file to disk: the same for every size, and large enough that counting it would
# hide the 16 MB win (100.5 s vs 101 s is under 5%).
FLUSH_S = 100.0
# How much faster a batch runs with each number of files at a time (limit 7, default 4).
ENCRYPT_SPEEDUP = {1: 1.0, 2: 1.9, 4: 3.5, 7: 3.6}  # 7 is under 5% faster than 4: keep the default
DECRYPT_SPEEDUP = {1: 1.0, 2: 3.0, 4: 2.0, 7: 1.5}  # 2 files at a time wins clearly


class _Clock:
    """A perf_counter stand-in that only the fake engine moves forward."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Engine:
    """Stands in for file_ops: renames x <-> x.gfglock, reports progress, and charges the clock."""

    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.workers = 1
        self.events: list[tuple[str, str, int]] = []
        self.fail_with = ""

    def encrypt_file(self, path, keys, algorithm, encrypt_name=False, read_size=0, progress=None, stop=None):
        return self._step("encrypt", path, path + ".gfglock", read_size, progress)

    def decrypt_file(self, path, keys, read_size=0, progress=None, stop=None):
        return self._step("decrypt", path, path[: -len(".gfglock")], read_size, progress)

    def _step(self, direction, path, output, read_size, progress):
        name = os.path.basename(path)
        self.events.append((direction, name, read_size))
        if self.fail_with:
            return FileResult(False, "x", "failed", self.fail_with)
        os.rename(path, output)
        large = name.startswith("speed test.bin")
        if large:
            self.clock.now += (ENCRYPT_READ if direction == "encrypt" else DECRYPT_READ)[read_size]
        else:
            speedup = (ENCRYPT_SPEEDUP if direction == "encrypt" else DECRYPT_SPEEDUP)[self.workers]
            self.clock.now += 1.0 / speedup
        progress(float(os.path.getsize(output)))
        if large:
            self.clock.now += FLUSH_S
        return FileResult(True, "", "done", output=output)


class _Pool:
    """ThreadPoolExecutor stand-in: runs the jobs in order and tells the engine how many run at a time."""

    def __init__(self, engine: _Engine, max_workers: int) -> None:
        engine.workers = max_workers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def map(self, job, items):
        return [job(item) for item in items]


class _SpyKeys(KeyRing):
    """A cheap key ring that records when the master key is derived."""

    def __init__(self, events: list) -> None:
        super().__init__("pw", KdfParams(memory_kib=64, iterations=1, lanes=1))
        self._events = events

    def new_header(self, algorithm):
        self._events.append(("key", "", 0))
        return super().new_header(algorithm)


@pytest.fixture
def engine(monkeypatch):
    """The fake engine, wired in with the stand-in pool and clock; cache eviction is recorded."""
    clock = _Clock()
    fake = _Engine(clock)
    monkeypatch.setattr(read_size_test.file_ops, "encrypt_file", fake.encrypt_file)
    monkeypatch.setattr(read_size_test.file_ops, "decrypt_file", fake.decrypt_file)
    monkeypatch.setattr(read_size_test, "ThreadPoolExecutor", lambda max_workers: _Pool(fake, max_workers))
    monkeypatch.setattr(read_size_test, "time", SimpleNamespace(perf_counter=clock))
    monkeypatch.setattr(read_size_test, "evict_cache", lambda path: fake.events.append(("evict", os.path.basename(path), 0)))
    return fake


def _run(tmp_path, events, **options) -> SpeedResult:
    """run_speed_test with small files, a thread limit of 7 and a default of 4."""
    options = {"file_size": 64 * 1024, "batch_size": 4096, **options}
    return run_speed_test("gcm", 7, 4, keys=_SpyKeys(events), folder=str(tmp_path), **options)


class TestRunSpeedTest:
    def test_picks_the_fastest_values_without_counting_the_flush(self, tmp_path, engine):
        result = _run(tmp_path, engine.events)
        assert result.encrypt.read_size == 16 * MB
        assert result.decrypt.read_size == ReadSizeDefaults.DEFAULT  # nothing was 5% faster
        assert result.encrypt.threads == 4                           # 7 was under 5% faster
        assert result.decrypt.threads == 2
        batch_bytes = 2 * 7 * 4096
        assert result.decrypt.bytes_per_s == pytest.approx(batch_bytes / (14 / 3.0))

    def test_files_at_a_time_runs_with_the_read_size_just_picked(self, tmp_path, engine):
        _run(tmp_path, engine.events)
        batch = [(direction, size) for direction, name, size in engine.events
                 if direction in ("encrypt", "decrypt") and not name.startswith("speed test.bin")]
        assert {size for direction, size in batch if direction == "encrypt"} == {16 * MB}
        assert {size for direction, size in batch if direction == "decrypt"} == {DEFAULT}

    def test_every_value_is_timed_in_two_rounds(self, tmp_path, engine):
        steps: list[tuple[int, int]] = []
        _run(tmp_path, engine.events, on_step=lambda done, total: steps.append((done, total)))
        large = [size for direction, name, size in engine.events if direction == "encrypt" and name == "speed test.bin"]
        assert large == ReadSizeDefaults.TEST_SIZES + ReadSizeDefaults.TEST_SIZES[::-1]  # round two in reverse
        total = 2 * 2 * (len(ReadSizeDefaults.TEST_SIZES) + len(ENCRYPT_SPEEDUP))
        assert steps == [(done, total) for done in range(1, total + 1)]

    def test_key_is_derived_before_any_timed_pass(self, tmp_path, engine):
        _run(tmp_path, engine.events)
        assert engine.events[0][0] == "key"
        assert [event for event in engine.events if event[0] == "key"] == [("key", "", 0)]

    def test_every_input_leaves_the_file_cache_before_it_is_read(self, tmp_path, engine):
        _run(tmp_path, engine.events)
        evicted: set[str] = set()
        for direction, name, _size in engine.events:
            if direction == "evict":
                evicted.add(name)
            elif direction in ("encrypt", "decrypt"):
                assert name in evicted, f"{name} was read without being evicted first"
                evicted.discard(name)

    def test_scratch_files_are_removed(self, tmp_path, engine):
        _run(tmp_path, engine.events)
        assert os.listdir(tmp_path) == []

    def test_a_file_held_open_at_cleanup_doesnt_fail_the_test(self, tmp_path, engine, monkeypatch):
        """An antivirus scanner can hold a scratch file when the folder is deleted (WinError 32)."""
        held = []
        real_decrypt = engine.decrypt_file

        def decrypt_and_hold(path, *args, **kwargs):
            result = real_decrypt(path, *args, **kwargs)
            if not held:
                held.append(open(os.path.join(os.path.dirname(path), "scanned.tmp"), "wb"))
            return result

        monkeypatch.setattr(read_size_test.file_ops, "decrypt_file", decrypt_and_hold)
        try:
            assert isinstance(_run(tmp_path, engine.events), SpeedResult)
        finally:
            held[0].close()
        remove_stale(str(tmp_path))  # the next test run removes what was left
        assert os.listdir(tmp_path) == []

    def test_a_failed_pass_is_reported(self, tmp_path, engine):
        engine.fail_with = "Disk full"
        with pytest.raises(ReadSizeTestError, match="Disk full"):
            _run(tmp_path, engine.events)
        assert os.listdir(tmp_path) == []

    def test_stops_when_cancelled(self, tmp_path, engine):
        stop = CancelToken()
        stop.cancel()
        with pytest.raises(ReadSizeTestCancelled):
            _run(tmp_path, engine.events, stop=stop)
        assert os.listdir(tmp_path) == []

    def test_refuses_without_enough_free_space(self, tmp_path, monkeypatch, engine):
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(read_size_test.shutil, "disk_usage", lambda _p: usage(1, 1, MB))
        with pytest.raises(ReadSizeTestError, match="free space"):
            _run(tmp_path, engine.events, file_size=MB)

    def test_old_scratch_folders_are_removed_first(self, tmp_path, engine):
        stale = tmp_path / "gfglock_speed_abc123"
        stale.mkdir()
        (stale / "speed test.bin").write_bytes(b"x" * 1024)
        kept = tmp_path / "other folder"
        kept.mkdir()
        _run(tmp_path, engine.events)
        assert os.listdir(tmp_path) == ["other folder"]


class TestWithFileOps:
    def test_tiny_run_end_to_end(self, tmp_path, keys):
        """The whole file_ops path (cache eviction included), at sizes small enough for a unit test."""
        result = run_speed_test("gcm", 2, 1, keys=keys, folder=str(tmp_path), sizes=[64 * 1024, DEFAULT],
                                file_size=256 * 1024, batch_size=64 * 1024)
        assert result.encrypt.read_size in (0, 64 * 1024) and result.decrypt.read_size in (0, 64 * 1024)
        assert result.encrypt.threads in (1, 2) and result.encrypt.bytes_per_s > 0
        assert os.listdir(tmp_path) == []


class TestEvictCache:
    def test_evicts_an_existing_file(self, tmp_path):
        path = tmp_path / "data.bin"
        path.write_bytes(os.urandom(64 * 1024))
        evict_cache(str(path))
        assert len(path.read_bytes()) == 64 * 1024

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(OSError):
            evict_cache(str(tmp_path / "gone.bin"))


class TestThreadCounts:
    @pytest.mark.parametrize("limit, default, expected", [
        (7, 4, [1, 2, 4, 7]),
        (8, 4, [1, 2, 4, 8]),
        (12, 6, [1, 2, 4, 6, 8, 12]),
        (1, 1, [1]),
        (3, 8, [1, 2, 3]),  # a default above the limit is timed at the limit
    ])
    def test_powers_of_two_the_limit_and_the_default(self, limit, default, expected):
        assert thread_counts(limit, default) == expected


class TestPickFastest:
    def test_clearly_faster_value_wins(self):
        assert pick_fastest({4 * MB: 1.0, 32 * MB: 0.8}, DEFAULT) == 32 * MB

    def test_small_difference_keeps_the_default(self):
        assert pick_fastest({4 * MB: 1.0, 8 * MB: 0.97}, DEFAULT) == DEFAULT

    def test_default_itself_fastest_keeps_the_default(self):
        assert pick_fastest({1 * MB: 1.3, 4 * MB: 1.0}, DEFAULT) == DEFAULT

    def test_without_a_default_timing_the_fastest_wins(self):
        assert pick_fastest({1: 2.0, 2: 1.0}, 4) == 2


class TestWorker:
    """The worker always reports back, so the Preferences window never stays stuck on Testing."""

    def _finish(self, monkeypatch, outcome) -> list:
        def fake_run(*args, **kwargs):
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(read_size_test, "run_speed_test", fake_run)
        monkeypatch.setattr(read_size_test, "write_log", lambda *a, **k: True)
        worker = ReadSizeTestWorker("gcm", 4, 2)
        finished: list = []
        worker.signals.finished.connect(lambda result, error: finished.append((result, error)))
        worker.run()
        return finished

    def test_result_is_reported(self, monkeypatch):
        result = SpeedResult(read_size_test.Choice(0, 2, 1e8), read_size_test.Choice(0, 2, 1e8))
        assert self._finish(monkeypatch, result) == [(result, "")]

    def test_stop_reports_nothing(self, monkeypatch):
        assert self._finish(monkeypatch, ReadSizeTestCancelled()) == [(None, "")]

    def test_disk_error_is_reported(self, monkeypatch):
        error = PermissionError(13, "Access is denied")
        assert self._finish(monkeypatch, error) == [(None, "The test couldn't finish: Access is denied.")]

    def test_unexpected_error_still_ends_the_test(self, monkeypatch):
        assert self._finish(monkeypatch, KeyError("boom")) == [(None, "The test couldn't finish: 'boom'.")]

    def test_cancel_sets_the_stop_token(self):
        worker = ReadSizeTestWorker("gcm", 4, 2)
        assert not worker._stop.cancelled
        worker.cancel()
        assert worker._stop.cancelled
