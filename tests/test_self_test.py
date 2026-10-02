# test_self_test.py - unit tests for the build self-test runner (gfglock.utils.self_test)

import pytest

from gfglock.core import native_bridge
from gfglock.utils import self_test
from gfglock.utils.self_test import run_self_test


def _fail() -> None:
    raise ImportError("No module named 'missing_lib'")


class TestRunSelfTest:
    def test_all_passing_returns_zero_and_writes_report(self, tmp_path):
        report = tmp_path / "report.txt"

        code = run_self_test(str(report), checks=[("First", lambda: None), ("Second", lambda: None)])

        assert code == 0
        assert report.read_text(encoding="utf-8").splitlines() == [
            "PASS  First", "PASS  Second", "All 2 checks passed",
        ]

    def test_failure_returns_one_and_keeps_running_later_checks(self, tmp_path):
        report = tmp_path / "report.txt"
        ran = []

        code = run_self_test(str(report), checks=[("Broken", _fail), ("After", lambda: ran.append(True))])

        text = report.read_text(encoding="utf-8")
        assert code == 1
        assert "FAIL  Broken: ImportError(\"No module named 'missing_lib'\")" in text
        assert "PASS  After" in text
        assert text.rstrip().endswith("1 of 2 checks failed")
        assert ran == [True]


class TestChecks:
    def test_missing_native_extension_fails(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)

        with pytest.raises(RuntimeError, match="gfglock_native is missing"):
            self_test._check_native_extension()

    @pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE, reason="needs the built native extension")
    def test_cipher_checks_pass_with_native_extension(self):
        self_test._check_file_round_trip()
        self_test._check_python_fallback()

    def test_valid_qml_passes(self, tmp_path, monkeypatch):
        (tmp_path / "Ok.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
        monkeypatch.setattr(self_test, "resource_path", lambda _relative: str(tmp_path))

        self_test._check_qml()

    def test_missing_qt_module_fails(self, tmp_path, monkeypatch):
        (tmp_path / "Broken.qml").write_text("import QtQuick.DoesNotExist\nItem {}\n", encoding="utf-8")
        monkeypatch.setattr(self_test, "resource_path", lambda _relative: str(tmp_path))

        with pytest.raises(RuntimeError, match="QtQuick.DoesNotExist"):
            self_test._check_qml()
