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

    def test_openssl_check_needs_the_native_extension(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)

        with pytest.raises(RuntimeError, match="needs the native extension"):
            self_test._check_openssl()

    @pytest.mark.parametrize("runtime, built, passes", [("3.6.5", "3.6.5", True), ("3.5.1", "3.6.5", False)])
    def test_openssl_check_compares_runtime_and_build(self, monkeypatch, runtime, built, passes):
        """A bundle that loaded another libcrypto (for example one found on PATH) must fail."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", True)
        monkeypatch.setattr(native_bridge, "openssl_version", lambda: runtime)
        monkeypatch.setattr(native_bridge, "openssl_build_version", lambda: built)

        if passes:
            self_test._check_openssl()
        else:
            with pytest.raises(RuntimeError, match="OpenSSL 3.5.1 is loaded"):
                self_test._check_openssl()

    def test_engine_check_passes_on_the_python_engine(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)

        self_test._check_engines()

    @pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE, reason="the native module (API 5) is not built")
    def test_engine_check_passes_with_both_engines(self):
        self_test._check_engines()

    def test_file_round_trip_passes(self):
        """The one test at the default Argon2id cost, as the frozen build runs it (native when built)."""
        self_test._check_file_round_trip()

    def test_valid_qml_passes(self, tmp_path, monkeypatch):
        (tmp_path / "Ok.qml").write_text("import QtQuick\nItem {}\n", encoding="utf-8")
        monkeypatch.setattr(self_test, "resource_path", lambda _relative: str(tmp_path))

        self_test._check_qml()

    def test_missing_qt_module_fails(self, tmp_path, monkeypatch):
        (tmp_path / "Broken.qml").write_text("import QtQuick.DoesNotExist\nItem {}\n", encoding="utf-8")
        monkeypatch.setattr(self_test, "resource_path", lambda _relative: str(tmp_path))

        with pytest.raises(RuntimeError, match="QtQuick.DoesNotExist"):
            self_test._check_qml()
