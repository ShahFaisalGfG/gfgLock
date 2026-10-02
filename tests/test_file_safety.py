# test_file_safety.py - regression tests for data-loss and path-safety bugs in file encryption.
#
# Each test runs against both cipher backends (native C++ and pure Python) because file_ops.py
# applies the same rules to both.

import os

import pytest

from gfglock.core import aes256_gcm_cfb as aes_core
from gfglock.core import chacha20_poly1305 as chacha_core
from gfglock.core import file_ops, native_bridge

PASSWORD = "correct horse battery staple"

BACKENDS = [
    pytest.param(True, id="native", marks=pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE, reason="native module not loaded")),
    pytest.param(False, id="python"),
]


@pytest.fixture(params=BACKENDS)
def backend(request, monkeypatch):
    """Run the test with the native module on, then with the Python fallback."""
    if not request.param:
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
    return request.param


def _write(path, data: bytes):
    path.write_bytes(data)
    return str(path)


def _leftover_temp_files(folder) -> list[str]:
    return [n for n in os.listdir(folder) if n.endswith(file_ops.TEMP_SUFFIX)]


def _flip_name_bytes(enc_path: str, header_size: int, old: str, new: str) -> None:
    """Rewrite the stored name in a CFB file without the password (CFB ciphertext is malleable)."""
    assert len(old) == len(new)
    data = bytearray(open(enc_path, "rb").read())
    for i, (a, b) in enumerate(zip(old.encode(), new.encode())):
        data[header_size + i] ^= a ^ b
    open(enc_path, "wb").write(bytes(data))


class TestNoCollisions:
    def test_same_stem_different_extension_both_survive(self, backend, tmp_path):
        """report.docx and report.pdf used to both become report.gfglock, destroying one file."""
        docx = _write(tmp_path / "report.docx", b"DOCX")
        pdf = _write(tmp_path / "report.pdf", b"PDF")
        assert aes_core.encrypt_file(docx, PASSWORD)[0]
        assert aes_core.encrypt_file(pdf, PASSWORD)[0]
        encrypted = sorted(os.listdir(tmp_path))
        assert encrypted == ["report.docx.gfglock", "report.pdf.gfglock"]
        for name in encrypted:
            assert aes_core.decrypt_file(str(tmp_path / name), PASSWORD)[0]
        assert (tmp_path / "report.docx").read_bytes() == b"DOCX"
        assert (tmp_path / "report.pdf").read_bytes() == b"PDF"

    def test_existing_encrypted_name_gets_suffix(self, backend, tmp_path):
        """A file already named like the output is never overwritten."""
        _write(tmp_path / "a.txt.gfgcha", b"unrelated")
        src = _write(tmp_path / "a.txt", b"secret")
        ok, msg = chacha_core.encrypt_file(src, PASSWORD)
        assert ok, msg
        assert (tmp_path / "a.txt.gfgcha").read_bytes() == b"unrelated"
        assert (tmp_path / "a.txt (2).gfgcha").exists()

    def test_decrypt_never_overwrites_existing_file(self, backend, tmp_path):
        src = _write(tmp_path / "notes.txt", b"version 1")
        assert aes_core.encrypt_file(src, PASSWORD)[0]
        _write(tmp_path / "notes.txt", b"version 2 - newer work")
        ok, msg = aes_core.decrypt_file(str(tmp_path / "notes.txt.gfglock"), PASSWORD)
        assert ok, msg
        assert (tmp_path / "notes.txt").read_bytes() == b"version 2 - newer work"
        assert (tmp_path / "notes (2).txt").read_bytes() == b"version 1"


class TestTamperedNames:
    CFB_HEADER = 16 + 16 + 4

    @pytest.mark.parametrize("evil", ["..\\x.tx", "NUL.txt", "a.t:xyz", "c:\\x.tx"])
    def test_cfb_name_cannot_escape_or_hit_devices(self, backend, tmp_path, evil):
        """A bit-flipped CFB name (no password needed) must not write outside the folder or to a device/stream."""
        folder = tmp_path / "inbox"
        folder.mkdir()
        src = _write(folder / "abc.txt", b"payload")
        assert aes_core.encrypt_file(src, PASSWORD, AEAD=False)[0]
        enc = str(folder / "abc.txt.gfglck")
        _flip_name_bytes(enc, self.CFB_HEADER, "abc.txt", evil)

        ok, msg = aes_core.decrypt_file(enc, PASSWORD)

        assert not ok and "wrong password or the file is corrupted" in msg
        assert os.path.exists(enc), "the encrypted file must be kept"
        assert sorted(os.listdir(folder)) == ["abc.txt.gfglck"]
        assert sorted(os.listdir(tmp_path)) == ["inbox"]

    def test_gcm_tampering_fails_authentication_and_leaves_nothing(self, backend, tmp_path):
        src = _write(tmp_path / "doc.txt", b"x" * 1000)
        assert aes_core.encrypt_file(src, PASSWORD)[0]
        enc = tmp_path / "doc.txt.gfglock"
        data = bytearray(enc.read_bytes())
        data[40] ^= 0x01
        enc.write_bytes(bytes(data))

        ok, msg = aes_core.decrypt_file(str(enc), PASSWORD)

        assert not ok and "authentication failed" in msg
        assert sorted(os.listdir(tmp_path)) == ["doc.txt.gfglock"]


class TestFailuresKeepTheSource:
    def test_wrong_password_keeps_file_and_cleans_temp(self, backend, tmp_path):
        src = _write(tmp_path / "f.bin", b"data")
        assert chacha_core.encrypt_file(src, PASSWORD)[0]
        ok, _ = chacha_core.decrypt_file(str(tmp_path / "f.bin.gfgcha"), "wrong")
        assert not ok
        assert sorted(os.listdir(tmp_path)) == ["f.bin.gfgcha"]

    def test_truncated_file_is_rejected(self, backend, tmp_path):
        enc = _write(tmp_path / "short.gfglock", b"\x00" * 20)
        ok, msg = aes_core.decrypt_file(enc, PASSWORD)
        assert not ok and "too small" in msg
        assert os.path.exists(enc)
        assert not _leftover_temp_files(tmp_path)

    def test_backend_failure_keeps_source(self, tmp_path, monkeypatch):
        src = _write(tmp_path / "keep.txt", b"important")
        monkeypatch.setattr(file_ops, "_backend_encrypt", lambda *a, **k: (False, "disk full"))
        ok, msg = aes_core.encrypt_file(src, PASSWORD)
        assert not ok and "disk full" in msg
        assert sorted(os.listdir(tmp_path)) == ["keep.txt"]

    def test_incomplete_output_keeps_source(self, tmp_path, monkeypatch):
        """A backend that reports success but writes a short file must not cost the original."""
        src = _write(tmp_path / "keep.txt", b"important")

        def short_write(algorithm, src_path, dst, name, password, chunk_size, progress):
            open(dst, "wb").write(b"partial")
            return True, ""

        monkeypatch.setattr(file_ops, "_backend_encrypt", short_write)
        ok, msg = aes_core.encrypt_file(src, PASSWORD)
        assert not ok and "incomplete" in msg
        assert sorted(os.listdir(tmp_path)) == ["keep.txt"]

    def test_already_encrypted_check_ignores_case(self, backend, tmp_path):
        """Encrypting A.GFGLOCK used to target the same file on NTFS and delete it."""
        src = _write(tmp_path / "A.GFGLOCK", b"already encrypted")
        ok, msg = aes_core.encrypt_file(src, PASSWORD)
        assert not ok and "already encrypted" in msg
        assert (tmp_path / "A.GFGLOCK").read_bytes() == b"already encrypted"


class TestNames:
    def test_non_ascii_names_round_trip(self, backend, tmp_path):
        src = _write(tmp_path / "résumé - ü 文件.txt", b"cv")
        ok, msg = aes_core.encrypt_file(src, PASSWORD)
        assert ok, msg
        ok, msg = aes_core.decrypt_file(str(tmp_path / "résumé - ü 文件.txt.gfglock"), PASSWORD)
        assert ok, msg
        assert (tmp_path / "résumé - ü 文件.txt").read_bytes() == b"cv"

    def test_encrypted_name_option_hides_and_restores(self, backend, tmp_path):
        src = _write(tmp_path / "salary.xlsx", b"numbers")
        assert aes_core.encrypt_file(src, PASSWORD, encrypt_name=True)[0]
        (enc,) = os.listdir(tmp_path)
        assert "salary" not in enc
        assert aes_core.decrypt_file(str(tmp_path / enc), PASSWORD)[0]
        assert (tmp_path / "salary.xlsx").read_bytes() == b"numbers"


class TestSafeOriginalName:
    @pytest.mark.parametrize("name", ["report.docx", "My File (1).tar.gz", "ünïcødé.txt", ".hidden", "a"])
    def test_accepts_ordinary_names(self, name):
        assert file_ops.safe_original_name(name.encode()) == name

    @pytest.mark.parametrize("raw", [
        b"", b".", b"..", b"..\\evil.exe", b"sub/evil", b"C:\\Windows\\x", b"file.txt:stream",
        b"NUL", b"nul.txt", b"COM1", b"lpt9.log", b"trailing.", b"trailing ", b"tab\there",
        b"\xff\xfe broken utf8", b"x" * 300,
    ])
    def test_rejects_unsafe_names(self, raw):
        assert file_ops.safe_original_name(raw) is None
