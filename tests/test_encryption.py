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


def _verify_name_roundtrip(
    src: str,
    pw: str,
    original: bytes,
    encrypt_fn: Callable,
    decrypt_fn: Callable,
    ext: str,
) -> None:
    """Assert encrypt_fn (with encrypt_name=True baked in) randomizes filename; decrypt restores it."""
    try:
        original_stem = os.path.splitext(os.path.basename(src))[0]
        enc_ok, msg = encrypt_fn(src, pw)
        assert enc_ok, f"Encrypt failed: {msg}"
        enc_path = _find_enc(os.path.dirname(src), ext)
        enc_stem = os.path.splitext(os.path.basename(enc_path))[0]
        assert original_stem not in enc_stem, (
            f"Encrypted stem '{enc_stem}' still exposes original stem '{original_stem}'"
        )
        dec_ok, msg = decrypt_fn(enc_path, pw)
        assert dec_ok, f"Decrypt failed: {msg}"
        restored = os.path.join(os.path.dirname(enc_path), os.path.basename(src))
        with open(restored, "rb") as f:
            assert f.read() == original, "Recovered data does not match original"
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

    def test_gcm_enc_name(self, make_file, password, sample_data):
        """AES-256-GCM native encrypt_name=True must randomize and restore filename."""
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=True, encrypt_name=True),
            aes_core.decrypt_file, ".gfglock",
        )

    def test_cfb_enc_name(self, make_file, password, sample_data):
        """AES-256-CFB native encrypt_name=True must randomize and restore filename."""
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=False, encrypt_name=True),
            aes_core.decrypt_file, ".gfglck",
        )

    def test_chacha_enc_name(self, make_file, password, sample_data):
        """ChaCha20-Poly1305 native encrypt_name=True must randomize and restore filename."""
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: chacha_core.encrypt_file(p, pw, encrypt_name=True),
            chacha_core.decrypt_file, ".gfgcha",
        )


class TestPythonFallback:
    """Round-trip tests with native C++ disabled - exercises the pure-Python path."""

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

    def test_gcm_enc_name(self, make_file, password, sample_data, monkeypatch):
        """AES-256-GCM Python fallback encrypt_name=True must randomize and restore filename."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=True, encrypt_name=True),
            aes_core.decrypt_file, ".gfglock",
        )

    def test_cfb_enc_name(self, make_file, password, sample_data, monkeypatch):
        """AES-256-CFB Python fallback encrypt_name=True must randomize and restore filename."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: aes_core.encrypt_file(p, pw, AEAD=False, encrypt_name=True),
            aes_core.decrypt_file, ".gfglck",
        )

    def test_chacha_enc_name(self, make_file, password, sample_data, monkeypatch):
        """ChaCha20-Poly1305 Python fallback encrypt_name=True must randomize and restore filename."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        _verify_name_roundtrip(
            src, password, sample_data,
            lambda p, pw: chacha_core.encrypt_file(p, pw, encrypt_name=True),
            chacha_core.decrypt_file, ".gfgcha",
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


_LARGE = 11 * 1024 * 1024 + 123  # three 4 MiB native blocks, the last one partial


class TestNegativePaths:
    """Error-path coverage: wrong password, already-encrypted inputs, non-encrypted inputs."""

    @pytest.mark.parametrize(
        "use_native", [False, pytest.param(True, marks=requires_native)],
        ids=["python", "native"],
    )
    def test_gcm_wrong_pw(self, make_file, password, use_native, monkeypatch):
        """GCM decrypt must fail authentication on wrong password and leave no plaintext."""
        if not use_native:
            monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        aes_core.encrypt_file(src, password, AEAD=True)
        enc = _find_enc(os.path.dirname(src), ".gfglock")
        ok, msg = aes_core.decrypt_file(enc, "wrong-password")
        assert not ok
        if not use_native:
            assert "auth" in msg.lower()
        assert not os.path.exists(os.path.join(os.path.dirname(enc), os.path.basename(src)))

    @pytest.mark.parametrize(
        "use_native", [False, pytest.param(True, marks=requires_native)],
        ids=["python", "native"],
    )
    def test_chacha_wrong_pw(self, make_file, password, use_native, monkeypatch):
        """ChaCha20 decrypt must fail authentication on wrong password and leave no plaintext."""
        if not use_native:
            monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = make_file()
        chacha_core.encrypt_file(src, password)
        enc = _find_enc(os.path.dirname(src), ".gfgcha")
        ok, msg = chacha_core.decrypt_file(enc, "wrong-password")
        assert not ok
        if not use_native:
            assert "auth" in msg.lower()
        assert not os.path.exists(os.path.join(os.path.dirname(enc), os.path.basename(src)))

    @pytest.mark.parametrize("ext,aead", [(".gfglock", True), (".gfglck", False)], ids=["gcm", "cfb"])
    def test_aes_already_enc(self, tmp_path, password, ext, aead, monkeypatch):
        """AES encrypt must refuse files with an encrypted extension without overwriting."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / f"file{ext}"
        data = b"pretend-encrypted"
        src.write_bytes(data)
        ok, msg = aes_core.encrypt_file(str(src), password, AEAD=aead)
        assert not ok
        assert "already" in msg.lower()
        assert src.read_bytes() == data

    def test_chacha_already_enc(self, tmp_path, password, monkeypatch):
        """ChaCha20 encrypt must refuse .gfgcha files without overwriting."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / "file.gfgcha"
        data = b"pretend-encrypted"
        src.write_bytes(data)
        ok, msg = chacha_core.encrypt_file(str(src), password)
        assert not ok
        assert "already" in msg.lower()
        assert src.read_bytes() == data

    def test_aes_non_encrypted(self, tmp_path, password, monkeypatch):
        """AES decrypt must refuse files without an encrypted extension."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / "plaintext.txt"
        data = b"just normal text"
        src.write_bytes(data)
        ok, msg = aes_core.decrypt_file(str(src), password)
        assert not ok
        assert "already decrypted" in msg.lower()
        assert src.read_bytes() == data

    def test_chacha_non_encrypted(self, tmp_path, password, monkeypatch):
        """ChaCha20 decrypt must refuse files without .gfgcha extension."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        src = tmp_path / "plaintext.txt"
        data = b"just normal text"
        src.write_bytes(data)
        ok, msg = chacha_core.decrypt_file(str(src), password)
        assert not ok
        assert "already decrypted" in msg.lower()
        assert src.read_bytes() == data


class TestLargeFiles:
    """Files spanning several native 4 MiB blocks must round-trip on every path and pairing."""

    @pytest.mark.parametrize("encrypt_native, decrypt_native", [
        pytest.param(True, True, marks=requires_native),
        pytest.param(True, False, marks=requires_native),
        pytest.param(False, True, marks=requires_native),
        (False, False),
    ])
    @pytest.mark.parametrize("algorithm, ext", [("gcm", ".gfglock"), ("cfb", ".gfglck"), ("chacha", ".gfgcha")])
    def test_roundtrip(self, tmp_path, password, monkeypatch, algorithm, ext, encrypt_native, decrypt_native):
        data = os.urandom(_LARGE)
        src = tmp_path / "large.bin"
        src.write_bytes(data)
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", encrypt_native)
        if algorithm == "chacha":
            ok, msg = chacha_core.encrypt_file(str(src), password)
        else:
            ok, msg = aes_core.encrypt_file(str(src), password, AEAD=algorithm == "gcm")
        assert ok, f"Encrypt failed: {msg}"
        enc = _find_enc(str(tmp_path), ext)
        with open(enc, "rb") as f:
            header = f.read(16 + (16 if algorithm == "cfb" else 12) + 4)
        assert header[-4:] == bytes(4), "the chunk field must say the data is one stream"
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", decrypt_native)
        decrypt = chacha_core.decrypt_file if algorithm == "chacha" else aes_core.decrypt_file
        ok, msg = decrypt(enc, password)
        assert ok, f"Decrypt failed: {msg}"
        assert src.read_bytes() == data

    @requires_native
    def test_truncated_file_fails_and_is_kept(self, tmp_path, password):
        src = tmp_path / "large.bin"
        src.write_bytes(os.urandom(_LARGE))
        ok, msg = aes_core.encrypt_file(str(src), password)
        assert ok, msg
        enc = _find_enc(str(tmp_path), ".gfglock")
        with open(enc, "r+b") as f:
            f.truncate(os.path.getsize(enc) - 5 * 1024 * 1024)
        ok, msg = aes_core.decrypt_file(enc, password)
        assert not ok
        assert sorted(os.listdir(tmp_path)) == [os.path.basename(enc)]

    @requires_native
    def test_progress_reports_every_byte(self, tmp_path, password):
        src = tmp_path / "large.bin"
        src.write_bytes(os.urandom(_LARGE))
        reported: list[float] = []
        ok, msg = aes_core.encrypt_file(str(src), password, progress_callback=reported.append)
        assert ok, msg
        assert sum(reported) == _LARGE + len("large.bin") + 1  # the data plus the stored name and NUL
