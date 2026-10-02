import hashlib
import importlib
import os
import sys

import pytest

from gfglock.core import native_bridge

_MISSING = object()

requires_native = pytest.mark.skipif(
    not native_bridge.NATIVE_AVAILABLE,
    reason="Native C++ extension not loaded",
)

_NATIVE_FUNCTIONS = ("pbkdf2_sha256", "encrypt_file", "decrypt_file")


def _reload_blocked():
    """Block `import gfglock_native`, reload native_bridge, assert it degrades safely,
    then always restore the module to its original state before returning."""
    original_entry = sys.modules.get("gfglock_native", _MISSING)
    try:
        sys.modules["gfglock_native"] = None  # type: ignore[assignment]
        reloaded = importlib.reload(native_bridge)
        assert reloaded.NATIVE_AVAILABLE is False, "must be False when import is blocked"
        assert reloaded._native is None, "_native must be None when import is blocked"
    except AssertionError:
        raise
    except Exception as exc:
        pytest.fail(str(exc))
    finally:
        if original_entry is _MISSING:
            sys.modules.pop("gfglock_native", None)
        else:
            sys.modules["gfglock_native"] = original_entry  # type: ignore[assignment]
        try:
            importlib.reload(native_bridge)
        except Exception as exc:
            pytest.fail(f"Failed to restore native_bridge state: {exc}")


class TestNativeAvailableFlag:
    """Coverage for what NATIVE_AVAILABLE reflects in this environment."""

    def test_is_bool(self):
        """NATIVE_AVAILABLE must always be a plain bool, never None or another type."""
        assert isinstance(native_bridge.NATIVE_AVAILABLE, bool)

    @requires_native
    def test_native_exports(self):
        """When native is available, every wrapped C++ function must be present and callable."""
        native = native_bridge._native
        assert native is not None
        assert native.API_VERSION >= native_bridge.REQUIRED_API_VERSION
        for name in _NATIVE_FUNCTIONS:
            func = getattr(native, name, None)
            assert callable(func), f"{name} missing or not callable on native module"


class TestImportDetectionLogic:
    """Directly exercises the try/except ImportError block that sets NATIVE_AVAILABLE."""

    def test_blocked_import(self):
        """Simulating the native extension's absence must flip NATIVE_AVAILABLE to False
        via the module's own detection logic, then restore the baseline afterward."""
        baseline = native_bridge.NATIVE_AVAILABLE
        _reload_blocked()
        assert native_bridge.NATIVE_AVAILABLE == baseline


class TestDeriveKey:
    """Coverage for the PBKDF2 key-derivation wrapper and its Python fallback."""

    def test_fallback_key(self, monkeypatch):
        """With native disabled, derive_key must match hashlib's PBKDF2-HMAC-SHA256 exactly."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        salt = b"static-salt-16by"
        key = native_bridge.derive_key("secret", salt, iterations=1000)
        expected = hashlib.pbkdf2_hmac("sha256", b"secret", salt, 1000, dklen=32)
        assert key == expected
        assert len(key) == 32

    @requires_native
    def test_native_matches_py(self, monkeypatch):
        """Native and Python-fallback key derivation must produce identical keys."""
        salt = b"another-salt-val"
        native_key = native_bridge.derive_key("secret", salt, iterations=1000)
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        python_key = native_bridge.derive_key("secret", salt, iterations=1000)
        assert native_key == python_key


class TestFallbackWrappers:
    """When NATIVE_AVAILABLE is False, every wrapper must degrade without raising."""

    def test_encrypt_wrapper_fallback(self, monkeypatch, tmp_path):
        """encrypt_file must return (False, message) instead of raising when native is off."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        ok, msg = native_bridge.encrypt_file("gcm", "missing.bin", str(tmp_path / "out"), "missing.bin", "pw")
        assert ok is False
        assert isinstance(msg, str) and msg

    def test_decrypt_wrapper_fallback(self, monkeypatch, tmp_path):
        """decrypt_file must return (False, message, b"") instead of raising when native is off."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        ok, msg, name = native_bridge.decrypt_file("gcm", "missing.gfglock", str(tmp_path / "out"), "pw")
        assert ok is False and name == b""
        assert isinstance(msg, str) and msg

    @requires_native
    def test_unknown_algorithm_reports_error(self, tmp_path):
        """The native module must reject an unknown algorithm name without crashing."""
        ok, msg = native_bridge.encrypt_file("rot13", "x", str(tmp_path / "o"), "x", "pw")
        assert ok is False and "unknown algorithm" in msg

    def test_outdated_module_is_ignored(self, monkeypatch):
        """A native module older than API version 2 must not be used."""
        fake = type(sys)("gfglock_native")
        monkeypatch.setitem(sys.modules, "gfglock_native", fake)
        try:
            reloaded = importlib.reload(native_bridge)
            assert reloaded.NATIVE_AVAILABLE is False
            assert reloaded._native is None
        finally:
            monkeypatch.undo()
            importlib.reload(native_bridge)


class TestPathHelpers:
    """Coverage for the directory-resolution helpers used to locate the .pyd."""

    def test_core_dir(self):
        """_core_dir must return the absolute, existing gfglock/core directory."""
        path = native_bridge._core_dir()
        assert os.path.isdir(path)
        assert os.path.abspath(path) == path

    def test_frozen_dir_default(self, monkeypatch):
        """Without sys._MEIPASS, _frozen_core_dir must fall back to _core_dir."""
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert native_bridge._frozen_core_dir() == native_bridge._core_dir()

    def test_frozen_dir_meipass(self, monkeypatch, tmp_path):
        """With sys._MEIPASS set, _frozen_core_dir must point under it instead."""
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        expected = os.path.join(str(tmp_path), "gfglock", "core")
        assert native_bridge._frozen_core_dir() == expected


class TestLogHelper:
    """Coverage for the stdout-based _log fallback used to avoid circular imports."""

    def test_log_writes(self, capfd):
        """_log must write the given message to stdout without raising."""
        try:
            native_bridge._log("hello-native-bridge-log")
        except Exception as exc:
            pytest.fail(f"_log raised: {exc}")
        captured = capfd.readouterr()
        assert "hello-native-bridge-log" in captured.out
