"""Keep the originals, save to another folder, check without writing, and read a header (core/file_ops.py)."""

import ctypes
import os
from ctypes import wintypes

import pytest

from gfglock.core import file_ops, native_bridge, reasons
from gfglock.core.format_v2 import KeyRing

from .conftest import FAST_KDF
from .test_encryption import FIXTURES, MANIFEST


@pytest.fixture(params=["native", "python"])
def backend(request, monkeypatch):
    if request.param == "python":
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
    elif not native_bridge.NATIVE_AVAILABLE:
        pytest.skip("the native module (API 5) is not built")
    return request.param


def _write(path, data: bytes) -> str:
    path.write_bytes(data)
    return str(path)


class TestKeepAndOutputFolder:
    def test_keep_the_original_when_encrypting(self, backend, tmp_path, keys):
        source = _write(tmp_path / "a.txt", b"keep me")
        result = file_ops.encrypt_file(source, keys, "gcm", keep_original=True)
        assert result.outcome == "done" and os.path.exists(source)
        assert sorted(os.listdir(tmp_path)) == ["a.txt", "a.txt.gfglock"]

    def test_encrypt_into_another_folder(self, backend, tmp_path, keys):
        source = _write(tmp_path / "a.txt", b"move me")
        out = tmp_path / "vault"
        out.mkdir()
        result = file_ops.encrypt_file(source, keys, "chacha", output_dir=str(out))
        assert result.output == str(out / "a.txt.gfgcha") and not os.path.exists(source)
        decrypted = file_ops.decrypt_file(result.output, keys, output_dir=str(tmp_path), keep_original=True)
        assert decrypted.output == str(tmp_path / "a.txt") and os.path.exists(result.output)
        assert (tmp_path / "a.txt").read_bytes() == b"move me"

    def test_a_kept_original_may_have_other_hard_links(self, backend, tmp_path, keys):
        source = _write(tmp_path / "a.txt", b"linked")
        os.link(source, tmp_path / "b.txt")
        assert file_ops.encrypt_file(source, keys, "gcm").category == reasons.HARD_LINK
        assert file_ops.encrypt_file(source, keys, "gcm", keep_original=True).outcome == "done"


class TestVerify:
    def test_the_right_password_checks_and_nothing_is_written(self, backend, tmp_path, keys):
        encrypted = file_ops.encrypt_file(_write(tmp_path / "a.txt", b"data" * 1000), keys, "gcm").output
        result = file_ops.verify_file(encrypted, KeyRing(keys.password, FAST_KDF))
        assert (result.outcome, result.category, result.output) == ("done", reasons.VERIFIED, "")
        assert os.listdir(tmp_path) == ["a.txt.gfglock"]

    def test_a_wrong_password_or_a_changed_byte_fails(self, backend, tmp_path, keys):
        encrypted = file_ops.encrypt_file(_write(tmp_path / "a.txt", b"data" * 1000), keys, "gcm").output
        assert file_ops.verify_file(encrypted, KeyRing("nope", FAST_KDF)).category == reasons.WRONG_PASSWORD
        raw = bytearray(open(encrypted, "rb").read())
        raw[-5] ^= 1
        open(encrypted, "wb").write(bytes(raw))
        assert file_ops.verify_file(encrypted, keys).category == reasons.WRONG_PASSWORD
        assert os.listdir(tmp_path) == ["a.txt.gfglock"]

    def test_a_plain_file_is_skipped(self, tmp_path, keys):
        assert file_ops.verify_file(_write(tmp_path / "a.txt", b"x"), keys).category == reasons.NOT_ENCRYPTED

    @pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
    def test_files_from_gfglock_3_1_check_too(self, backend, name):
        """The old formats are read to the end as well; CFB can only have its stored name checked."""
        result = file_ops.verify_file(str(FIXTURES / name), KeyRing(MANIFEST["password"]))
        assert (result.outcome, result.category) == ("done", reasons.VERIFIED)
        assert ("stored name" in result.reason) == name.endswith(".gfglck")


class TestDescribe:
    def test_a_v2_header(self, tmp_path, keys):
        encrypted = file_ops.encrypt_file(_write(tmp_path / "a.txt", b"x"), keys, "chacha", encrypt_name=True).output
        info = file_ops.describe_file(encrypted)
        assert (info["format"], info["algorithm"], info["kdf"], info["hidden_name"]) == (2, "chacha20-poly1305",
                                                                                         "argon2id", True)
        assert info["kdf_iterations"] == FAST_KDF.iterations and info["authenticated"] is True

    def test_a_file_gfglock_didnt_make(self, tmp_path):
        with pytest.raises(file_ops.FormatError):
            file_ops.describe_file(_write(tmp_path / "a.txt", b"x"))


class TestRemovable:
    def test_a_file_open_in_another_program_is_found_before_any_work(self, backend, tmp_path, keys):
        """Word and many players open files without letting others delete them; that used to be found
        only after the encrypted copy was written."""
        source = _write(tmp_path / "open.docx", b"busy")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        handle = kernel32.CreateFileW(source, 0x80000000, 0x1 | 0x2, None, 3, 0, None)  # read, share read/write
        assert handle and handle != wintypes.HANDLE(-1).value
        try:
            result = file_ops.encrypt_file(source, keys, "gcm")
        finally:
            kernel32.CloseHandle(handle)
        assert (result.outcome, result.category) == ("failed", reasons.IN_USE)
        assert os.listdir(tmp_path) == ["open.docx"]
