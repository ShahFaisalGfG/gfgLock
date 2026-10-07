# test_read_size_test.py - unit tests for gfglock.services.read_size_test (the Preferences speed test)

import os
from collections import namedtuple

import pytest

from gfglock.services import read_size_test
from gfglock.services.read_size_test import (
    ReadSizeTestCancelled,
    ReadSizeTestError,
    SizeTiming,
    pick_fastest,
    time_read_sizes,
)

MB = 1024 * 1024


class TestTimeReadSizes:
    def test_times_every_size_and_cleans_up(self, tmp_path):
        steps = []
        timings = time_read_sizes([MB, 4 * MB], "gcm", folder=str(tmp_path), file_size=2 * MB,
                                  on_step=lambda done, total: steps.append((done, total)))
        assert [t.read_size for t in timings] == [MB, 4 * MB]
        assert all(t.encrypt_s > 0 and t.decrypt_s > 0 for t in timings)
        assert steps[-1] == (8, 8)  # 2 rounds x 2 sizes x (encrypt + decrypt)
        assert os.listdir(tmp_path) == []

    def test_stops_when_cancelled(self, tmp_path):
        with pytest.raises(ReadSizeTestCancelled):
            time_read_sizes([MB], "gcm", folder=str(tmp_path), file_size=MB, is_cancelled=lambda: True)
        assert os.listdir(tmp_path) == []

    def test_refuses_without_enough_free_space(self, tmp_path, monkeypatch):
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(read_size_test.shutil, "disk_usage", lambda _p: usage(1, 1, MB))
        with pytest.raises(ReadSizeTestError, match="free space"):
            time_read_sizes([MB], "gcm", folder=str(tmp_path), file_size=MB)

    def test_failed_step_is_reported(self, tmp_path, monkeypatch):
        failure = read_size_test.file_ops.FileResult(False, "x", "failed", "Disk full")
        monkeypatch.setattr(read_size_test.file_ops, "encrypt_file", lambda *a, **k: failure)
        with pytest.raises(ReadSizeTestError, match="Disk full"):
            time_read_sizes([MB], "gcm", folder=str(tmp_path), file_size=MB)


class TestPickFastest:
    DEFAULT = 4 * MB

    def _timings(self, **seconds):
        return [SizeTiming(int(name[1:]) * MB, s, s) for name, s in seconds.items()]

    def test_clearly_faster_size_wins(self):
        timings = self._timings(s4=1.0, s32=0.8)
        assert pick_fastest(timings, lambda t: t.encrypt_s, self.DEFAULT) == 32 * MB

    def test_small_difference_keeps_the_default(self):
        timings = self._timings(s4=1.0, s8=0.97)
        assert pick_fastest(timings, lambda t: t.encrypt_s, self.DEFAULT) == 0

    def test_default_size_itself_fastest_keeps_the_default(self):
        timings = self._timings(s1=1.3, s4=1.0)
        assert pick_fastest(timings, lambda t: t.encrypt_s, self.DEFAULT) == 0
