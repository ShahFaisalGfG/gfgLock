import hashlib
import importlib
import importlib.abc
import os
import sys

import pytest

from gfglock.core import native_bridge

_MISSING = object()

requires_native = pytest.mark.skipif(
    not native_bridge.NATIVE_AVAILABLE,
    reason="the native module (API 5) is not built",
)

_NATIVE_NAMES = ("pbkdf2_sha256", "seal_file", "open_file", "decrypt_file_v1", "CancelToken",
                 "openssl_version", "openssl_build_version")


class _FailingLoader(importlib.abc.MetaPathFinder):
    """Makes `import gfglock_native` fail the way a .pyd with a missing DLL does."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "gfglock_native":
            raise ImportError("DLL load failed while importing gfglock_native")
        return None


@pytest.fixture
def reload_bridge(monkeypatch):
    """Reload native_bridge under the test's import conditions, and restore it afterwards."""
    yield lambda: importlib.reload(native_bridge)
    monkeypatch.undo()
    importlib.reload(native_bridge)


class TestNativeAvailableFlag:
    def test_is_bool(self):
        assert isinstance(native_bridge.NATIVE_AVAILABLE, bool)

    @requires_native
    def test_native_exports(self):
        native = native_bridge._native
        assert native is not None
        assert native.API_VERSION >= native_bridge.REQUIRED_API_VERSION == 5
        for name in _NATIVE_NAMES:
            assert callable(getattr(native, name, None)), f"{name} missing or not callable on the native module"


class TestImportDetection:
    def test_missing_module_falls_back(self, monkeypatch, reload_bridge):
        monkeypatch.setitem(sys.modules, "gfglock_native", None)
        reloaded = reload_bridge()
        assert reloaded.NATIVE_AVAILABLE is False and reloaded._native is None

    @pytest.mark.parametrize("api_version", [None, 4], ids=["no-version", "api-4"])
    def test_outdated_module_is_ignored(self, monkeypatch, reload_bridge, capfd, api_version):
        """A module from before the v2 format must not be used: its transforms write v1 files."""
        fake = type(sys)("gfglock_native")
        if api_version is not None:
            setattr(fake, "API_VERSION", api_version)
        monkeypatch.setitem(sys.modules, "gfglock_native", fake)
        reloaded = reload_bridge()
        assert reloaded.NATIVE_AVAILABLE is False and reloaded._native is None
        assert "outdated" in capfd.readouterr().out

    def test_module_that_fails_to_load_is_reported(self, monkeypatch, reload_bridge, capfd):
        monkeypatch.delitem(sys.modules, "gfglock_native", raising=False)
        monkeypatch.setattr(sys, "meta_path", [_FailingLoader(), *sys.meta_path])
        reloaded = reload_bridge()
        assert reloaded.NATIVE_AVAILABLE is False and reloaded._native is None
        assert "DLL load failed" in capfd.readouterr().out


class TestDeriveKey:
    def test_fallback_key(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        salt = b"static-salt-16by"
        key = native_bridge.derive_key("secret", salt, iterations=1000)
        assert key == hashlib.pbkdf2_hmac("sha256", b"secret", salt, 1000, dklen=32)

    @requires_native
    def test_native_matches_python(self, monkeypatch):
        salt = b"another-salt-val"
        native_key = native_bridge.derive_key("secret", salt, iterations=1000)
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        assert native_bridge.derive_key("secret", salt, iterations=1000) == native_key


class TestWrappersWithoutNative:
    """With the native engine off, every wrapper reports an error instead of raising."""

    def test_transforms_report_an_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        out = str(tmp_path / "out")
        results = [
            native_bridge.seal_file("gcm", "in", out, b"h", b"k" * 32, b"p" * 7, 1 << 20, b"m"),
            native_bridge.open_file("gcm", "in", out, b"h", b"k" * 32, b"p" * 7, 1 << 20),
            native_bridge.decrypt_file_v1("gcm", "in.gfglock", out, "pw"),
        ]
        for result in results:
            assert result[0] is False and result[1] == "the native engine is not loaded"
        assert results[1][2] == results[2][2] == b""
        assert not os.path.exists(out)

    def test_token_needs_the_module(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="not loaded"):
            native_bridge.new_cancel_token()

    def test_openssl_versions_are_empty(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        assert native_bridge.openssl_version() == native_bridge.openssl_build_version() == ""


@requires_native
class TestNativeModule:
    def test_runs_on_the_openssl_it_was_built_with(self):
        assert native_bridge.openssl_version() == native_bridge.openssl_build_version() != ""

    def test_unknown_algorithm_reports_error(self, tmp_path):
        source = tmp_path / "in"
        source.write_bytes(b"x")
        ok, message = native_bridge.seal_file("rot13", str(source), str(tmp_path / "o"), b"h" * 60,
                                              b"k" * 32, b"p" * 7, 1 << 20, b"\x00\x01a" + bytes(8))
        assert ok is False and "unknown algorithm" in message

    def test_cancel_token(self):
        token = native_bridge.new_cancel_token()
        assert token.cancelled is False
        token.cancel()
        assert token.cancelled is True


class TestPathHelpers:
    def test_core_dir(self):
        path = native_bridge._core_dir()
        assert os.path.isdir(path)
        assert os.path.abspath(path) == path

    def test_frozen_dir_default(self, monkeypatch):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        assert native_bridge._frozen_core_dir() == native_bridge._core_dir()

    def test_frozen_dir_meipass(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert native_bridge._frozen_core_dir() == os.path.join(str(tmp_path), "gfglock", "core")
