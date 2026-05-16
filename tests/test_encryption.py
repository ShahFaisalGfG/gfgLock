import glob
import os
from typing import Callable

import pytest

from gfglock.core import aes256_gcm_cfb as aes_core
from gfglock.core import chacha20_poly1305 as chacha_core
from gfglock.core import native_bridge

requires_native = pytest.mark.skipif(
    not native_bridge.NATIVE_AVAILABLE,
    reason="Native C++ extension not loaded",
)


def _find_enc(directory: str, ext: str) -> str:
    """Locate the first encrypted file matching *{ext} in directory."""
    try:
        matches = glob.glob(os.path.join(directory, f"*{ext}"))
        assert matches, f"No *{ext} file found in {directory}"
        return matches[0]
    except AssertionError:
        raise
    except Exception as exc:
        pytest.fail(str(exc))


def _verify_roundtrip(
    src: str,
    pw: str,
    original: bytes,
    encrypt_fn: Callable,
    decrypt_fn: Callable,
    ext: str,
) -> None:
    """Encrypt src, decrypt the result, assert recovered bytes equal original."""
    try:
        enc_ok, msg = encrypt_fn(src, pw)
        assert enc_ok, f"Encrypt failed: {msg}"
        enc_path = _find_enc(os.path.dirname(src), ext)
        dec_ok, msg = decrypt_fn(enc_path, pw)
        assert dec_ok, f"Decrypt failed: {msg}"
        restored = os.path.join(os.path.dirname(enc_path), os.path.basename(src))
        with open(restored, "rb") as f:
            assert f.read() == original, "Recovered data does not match original"
    except AssertionError:
        raise
    except Exception as exc:
        pytest.fail(str(exc))


def _cross_roundtrip(
    src: str,
    pw: str,
    original: bytes,
    encrypt_fn: Callable,
    decrypt_fn: Callable,
    ext: str,
    py_first: bool,
    monkeypatch,
) -> None:
    """Encrypt with one path and decrypt with the other; assert data integrity."""
    try:
        if py_first:
            monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        enc_ok, msg = encrypt_fn(src, pw)
        assert enc_ok, f"Encrypt failed: {msg}"
        enc_path = _find_enc(os.path.dirname(src), ext)
        if py_first:
            monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", True)
        else:
            monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        dec_ok, msg = decrypt_fn(enc_path, pw)
        assert dec_ok, f"Cross-path decrypt failed: {msg}"
        restored = os.path.join(os.path.dirname(enc_path), os.path.basename(src))
        with open(restored, "rb") as f:
            assert f.read() == original, "Cross-path recovered data does not match original"
    except AssertionError:
        raise
    except Exception as exc:
        pytest.fail(str(exc))


@requires_native
class TestNativeAcceleration:
    """Round-trip tests using the native C++ accelerated path."""

    def test_gcm_roundtrip(self, make_file, password, sample_data):
        """AES-256-GCM native encrypt → decrypt must recover original bytes."""
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=True),
            aes_core.decrypt_file, ".gfglock",
        )

    def test_cfb_roundtrip(self, make_file, password, sample_data):
        """AES-256-CFB native encrypt → decrypt must recover original bytes."""
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=False),
            aes_core.decrypt_file, ".gfglck",
        )

    def test_chacha_roundtrip(self, make_file, password, sample_data):
        """ChaCha20-Poly1305 native encrypt → decrypt must recover original bytes."""
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            chacha_core.encrypt_file, chacha_core.decrypt_file, ".gfgcha",
        )


class TestPythonFallback:
    """Round-trip tests with native C++ disabled — exercises the pure-Python path."""

    def test_gcm_roundtrip(self, make_file, password, sample_data, monkeypatch):
        """AES-256-GCM Python fallback encrypt → decrypt must recover original bytes."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=True),
            aes_core.decrypt_file, ".gfglock",
        )

    def test_cfb_roundtrip(self, make_file, password, sample_data, monkeypatch):
        """AES-256-CFB Python fallback encrypt → decrypt must recover original bytes."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=False),
            aes_core.decrypt_file, ".gfglck",
        )

    def test_chacha_roundtrip(self, make_file, password, sample_data, monkeypatch):
        """ChaCha20-Poly1305 Python fallback encrypt → decrypt must recover original bytes."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_roundtrip(
            src, password, sample_data,
            chacha_core.encrypt_file, chacha_core.decrypt_file, ".gfgcha",
        )


@requires_native
class TestCrossCompatibility:
    """Ciphertext produced by one path must be decryptable by the other path."""

    @pytest.mark.parametrize("py_first", [False, True], ids=["native→py", "py→native"])
    def test_gcm_compat(self, py_first, make_file, password, sample_data, monkeypatch):
        """GCM ciphertext must be cross-compatible between native and Python paths."""
        src = make_file()
        _cross_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=True),
            aes_core.decrypt_file, ".gfglock", py_first, monkeypatch,
        )

    @pytest.mark.parametrize("py_first", [False, True], ids=["native→py", "py→native"])
    def test_cfb_compat(self, py_first, make_file, password, sample_data, monkeypatch):
        """CFB ciphertext must be cross-compatible between native and Python paths."""
        src = make_file()
        _cross_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=False),
            aes_core.decrypt_file, ".gfglck", py_first, monkeypatch,
        )

    @pytest.mark.parametrize("py_first", [False, True], ids=["native→py", "py→native"])
    def test_chacha_compat(self, py_first, make_file, password, sample_data, monkeypatch):
        """ChaCha20 ciphertext must be cross-compatible between native and Python paths."""
        src = make_file()
        _cross_roundtrip(
            src, password, sample_data,
            chacha_core.encrypt_file, chacha_core.decrypt_file, ".gfgcha", py_first, monkeypatch,
        )
