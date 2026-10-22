# test_file_safety.py - regression tests for data-loss and path-safety bugs in file encryption.
#
# Each test runs against both engines (native C++ when its API 5 module is built, and pure Python)
# because file_ops.py applies the same rules to both.

import functools
import os
import shutil
from pathlib import Path

import pytest
from cryptography.hazmat.decrepit.ciphers.modes import CFB
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

from gfglock.core import file_ops, format_v2, native_bridge, py_cipher
from gfglock.core.format_v2 import KeyRing
from tests.v1_writer import HEADER_SIZES, v1_bytes, v1_key

FIXTURES = Path(__file__).parent / "fixtures" / "v1"
V1_SALT = bytes(range(16))
KEPT_REASON = "The encrypted file was kept because the old CFB format can't confirm the password"


@pytest.fixture(params=[
    pytest.param(True, id="native", marks=pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE,
                                                             reason="the native module (API 5) is not built")),
    pytest.param(False, id="python"),
])
def backend(request, monkeypatch):
    """Run the test with the native engine, then with the Python one."""
    if not request.param:
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
    return request.param


@functools.cache
def _v1_key(password: str) -> bytes:
    """The v1 key for V1_SALT, derived once per password for the whole module."""
    return v1_key(password, V1_SALT)


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return str(path)


def _encrypt(path: str, keys: KeyRing, algorithm: str = "gcm", **options) -> str:
    result = file_ops.encrypt_file(path, keys, algorithm, **options)
    assert result.outcome == "done", result
    return result.output


def _leftover_temp_files(folder: Path) -> list[str]:
    return [n for n in os.listdir(folder) if n.endswith(file_ops.TEMP_SUFFIX)]


def _cfb_misread_by(path: Path, password: str, wrong: str, data: bytes) -> str:
    """Write a CFB file of notes.txt that `wrong` decrypts to another valid short name; return that name.

    About 1 IV in 450 does this, which is how often a wrong password used to cost the encrypted file.
    """
    right_key, wrong_key = _v1_key(password), _v1_key(wrong)
    start = HEADER_SIZES["cfb"]
    for counter in range(100_000):
        iv = counter.to_bytes(16, "big")
        raw = v1_bytes("cfb", right_key, V1_SALT, iv, b"notes.txt", data)
        guess = Cipher(algorithms.AES(wrong_key), CFB(iv)).decryptor().update(raw[start:start + 64])
        name, nul, _ = guess.partition(b"\0")
        restored = file_ops.safe_original_name(name) if nul else None
        if restored and os.path.normcase(restored) != "notes.txt":
            path.write_bytes(raw)
            return restored
    raise AssertionError("no IV made the wrong password yield a valid name")


class TestNoCollisions:
    def test_same_stem_different_extension_both_survive(self, backend, tmp_path, keys):
        """report.docx and report.pdf used to both become report.gfglock, destroying one file."""
        docx = _write(tmp_path / "report.docx", b"DOCX")
        pdf = _write(tmp_path / "report.pdf", b"PDF")
        _encrypt(docx, keys)
        _encrypt(pdf, keys)
        encrypted = sorted(os.listdir(tmp_path))
        assert encrypted == ["report.docx.gfglock", "report.pdf.gfglock"]
        for name in encrypted:
            assert file_ops.decrypt_file(str(tmp_path / name), keys).outcome == "done"
        assert (tmp_path / "report.docx").read_bytes() == b"DOCX"
        assert (tmp_path / "report.pdf").read_bytes() == b"PDF"

    def test_existing_encrypted_name_gets_suffix(self, backend, tmp_path, keys):
        """A file already named like the output is never overwritten."""
        _write(tmp_path / "a.txt.gfgcha", b"unrelated")
        _encrypt(_write(tmp_path / "a.txt", b"secret"), keys, "chacha")
        assert (tmp_path / "a.txt.gfgcha").read_bytes() == b"unrelated"
        assert (tmp_path / "a.txt (2).gfgcha").exists()

    def test_decrypt_never_overwrites_existing_file(self, backend, tmp_path, keys):
        encrypted = _encrypt(_write(tmp_path / "notes.txt", b"version 1"), keys)
        _write(tmp_path / "notes.txt", b"version 2 - newer work")
        assert file_ops.decrypt_file(encrypted, keys).outcome == "done"
        assert (tmp_path / "notes.txt").read_bytes() == b"version 2 - newer work"
        assert (tmp_path / "notes (2).txt").read_bytes() == b"version 1"


class TestStoredNames:
    """The name inside an encrypted file never reaches outside its folder, a device, or a stream."""

    @pytest.mark.parametrize("evil", ["..\\x.txt", "NUL.txt", "a.t:xyz", "c:\\x.tx"])
    def test_v1_name_cannot_escape_or_hit_devices(self, backend, tmp_path, password, evil):
        folder = tmp_path / "inbox"
        folder.mkdir()
        encrypted = folder / "abc.txt.gfglck"
        encrypted.write_bytes(v1_bytes("cfb", _v1_key(password), V1_SALT, bytes(16), evil.encode(), b"payload"))

        result = file_ops.decrypt_file(str(encrypted), KeyRing(password))

        assert result.outcome == "failed" and "wrong password or the file is corrupted" in result[1]
        assert sorted(os.listdir(folder)) == ["abc.txt.gfglck"]
        assert sorted(os.listdir(tmp_path)) == ["inbox"]

    def test_v1_authenticated_name_is_checked_too(self, backend, tmp_path, password):
        encrypted = tmp_path / "abc.txt.gfglock"
        encrypted.write_bytes(v1_bytes("gcm", _v1_key(password), V1_SALT, bytes(12), b"CON.txt", b"payload"))

        result = file_ops.decrypt_file(str(encrypted), KeyRing(password))

        assert result.outcome == "failed" and "isn't a safe Windows file name" in result.reason
        assert sorted(os.listdir(tmp_path)) == ["abc.txt.gfglock"]

    @pytest.mark.parametrize("evil", ["..\\x.txt", "CONIN$", "COM¹.log", "invoice\u202efdp.exe"])
    def test_v2_name_cannot_escape_or_disguise(self, backend, tmp_path, keys, evil):
        """A v2 name is authenticated, but whoever made the file chose it, so it is checked too."""
        source, encrypted = tmp_path / "in", tmp_path / "abc.gfglock"
        source.write_bytes(b"payload")
        header, key = keys.new_header("gcm")
        ok, error = py_cipher.seal_stream("gcm", str(source), str(encrypted), header.pack(), key,
                                          header.nonce_prefix, header.chunk_size, format_v2.pack_metadata(evil, 0))
        assert ok, error
        source.unlink()

        result = file_ops.decrypt_file(str(encrypted), keys)

        assert result.outcome == "failed" and "isn't a safe Windows file name" in result.reason
        assert sorted(os.listdir(tmp_path)) == ["abc.gfglock"]


class TestLegacyCfb:
    """CFB can't tell a wrong password from the right one, so its encrypted file is kept unless the name matches."""

    def test_wrong_password_with_a_valid_name_keeps_the_encrypted_file(self, backend, tmp_path, password, sample_data):
        encrypted = tmp_path / "notes.txt.gfglck"
        wrong = "not " + password
        garbage_name = _cfb_misread_by(encrypted, password, wrong, sample_data)
        before = encrypted.read_bytes()

        misread = file_ops.decrypt_file(str(encrypted), KeyRing(wrong))

        assert misread.outcome == "done" and misread.reason.startswith(KEPT_REASON)
        assert os.path.basename(misread.output) == garbage_name
        assert encrypted.read_bytes() == before

        restored = file_ops.decrypt_file(str(encrypted), KeyRing(password))

        assert (restored.outcome, restored.reason) == ("done", "")
        assert (tmp_path / "notes.txt").read_bytes() == sample_data
        assert not encrypted.exists()

    def test_aead_file_renamed_to_cfb_is_kept(self, backend, tmp_path, password):
        """A GCM file renamed to .gfglck decrypts as CFB garbage; it must never be deleted."""
        encrypted = tmp_path / "report.docx.gfglck"
        shutil.copy(FIXTURES / "report.docx.gfglock", encrypted)
        before = encrypted.read_bytes()

        result = file_ops.decrypt_file(str(encrypted), KeyRing(password))

        assert result.outcome in ("done", "failed")
        assert encrypted.read_bytes() == before


class TestFailuresKeepTheSource:
    def test_wrong_password_keeps_file_and_cleans_temp(self, backend, tmp_path, keys):
        encrypted = _encrypt(_write(tmp_path / "f.bin", b"data"), keys, "chacha")
        assert file_ops.decrypt_file(encrypted, KeyRing("wrong")).outcome == "failed"
        assert sorted(os.listdir(tmp_path)) == ["f.bin.gfgcha"]

    @pytest.mark.parametrize("data, message", [
        (b"\x00" * 20, "too small"),
        (format_v2.MAGIC + bytes([format_v2.VERSION]) + b"\x01" * 20, "too small"),
    ], ids=["v1", "v2"])
    def test_truncated_file_is_rejected(self, backend, tmp_path, keys, data, message):
        encrypted = _write(tmp_path / "short.gfglock", data)
        result = file_ops.decrypt_file(encrypted, keys)
        assert result.outcome == "failed" and message in result[1]
        assert sorted(os.listdir(tmp_path)) == ["short.gfglock"]

    def test_engine_failure_keeps_source(self, tmp_path, keys, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        monkeypatch.setattr(py_cipher, "seal_stream", lambda *args: (False, "disk full"))
        result = file_ops.encrypt_file(_write(tmp_path / "keep.txt", b"important"), keys, "gcm")
        assert result.outcome == "failed" and "disk full" in result[1]
        assert sorted(os.listdir(tmp_path)) == ["keep.txt"]

    def test_incomplete_output_keeps_source(self, tmp_path, keys, monkeypatch):
        """An engine that reports success but writes a short file must not cost the original."""
        def short_write(_algorithm, _source, output, *_rest):
            Path(output).write_bytes(b"partial")
            return True, ""

        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        monkeypatch.setattr(py_cipher, "seal_stream", short_write)
        result = file_ops.encrypt_file(_write(tmp_path / "keep.txt", b"important"), keys, "gcm")
        assert result.outcome == "failed" and "incomplete" in result[1]
        assert sorted(os.listdir(tmp_path)) == ["keep.txt"]

    def test_unexpected_error_leaves_no_temp_file(self, tmp_path, keys, monkeypatch):
        """Errors other than OSError still remove the partly written temp file."""
        def explode(*_args):
            raise RuntimeError("boom")

        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        monkeypatch.setattr(py_cipher, "seal_stream", explode)
        with pytest.raises(RuntimeError):
            file_ops.encrypt_file(_write(tmp_path / "a.txt", b"data"), keys, "gcm")
        assert sorted(os.listdir(tmp_path)) == ["a.txt"]

    def test_already_encrypted_check_ignores_case(self, backend, tmp_path, keys):
        """Encrypting A.GFGLOCK used to target the same file on NTFS and delete it."""
        result = file_ops.encrypt_file(_write(tmp_path / "A.GFGLOCK", b"already encrypted"), keys, "gcm")
        assert (result.outcome, result.reason) == ("skipped", "Already encrypted")
        assert (tmp_path / "A.GFGLOCK").read_bytes() == b"already encrypted"

    def test_cfb_is_decrypt_only(self, tmp_path, keys):
        result = file_ops.encrypt_file(_write(tmp_path / "a.txt", b"data"), keys, "cfb")
        assert result.outcome == "failed" and result.reason == "Unknown encryption method 'cfb'"
        assert sorted(os.listdir(tmp_path)) == ["a.txt"]


class TestNames:
    def test_non_ascii_names_round_trip(self, backend, tmp_path, keys):
        encrypted = _encrypt(_write(tmp_path / "résumé - ü 文件.txt", b"cv"), keys)
        assert os.path.basename(encrypted) == "résumé - ü 文件.txt.gfglock"
        assert file_ops.decrypt_file(encrypted, keys).outcome == "done"
        assert (tmp_path / "résumé - ü 文件.txt").read_bytes() == b"cv"

    def test_name_too_long_for_the_extension_is_refused(self, backend, tmp_path, keys):
        """The limit is 255 UTF-16 units: 122 emoji are 244 units though only 122 characters."""
        name = "😀" * 122 + ".txt"  # 248 units: room for ".gfgcha" (255) but not ".gfglock" (256)
        source = _write(tmp_path / name, b"data")

        refused = file_ops.encrypt_file(source, keys, "gcm")

        assert refused.outcome == "failed" and "Hide file names" in refused.reason
        assert sorted(os.listdir(tmp_path)) == [name]
        assert file_ops.decrypt_file(_encrypt(source, keys, "chacha"), keys).outcome == "done"
        hidden = _encrypt(source, keys, "gcm", encrypt_name=True)
        assert file_ops.decrypt_file(hidden, keys).outcome == "done"
        assert (tmp_path / name).read_bytes() == b"data"

    def test_name_that_could_not_be_restored_is_refused(self, backend, tmp_path, keys):
        """Decrypting refuses invisible format characters, so encrypting such a name would strand the file."""
        name = "invoice\u202efdp.exe"
        result = file_ops.encrypt_file(_write(tmp_path / name, b"data"), keys, "gcm")
        assert result.outcome == "failed" and "rename the file" in result.reason
        assert sorted(os.listdir(tmp_path)) == [name]


class TestSafeOriginalName:
    @pytest.mark.parametrize("name", [
        "report.docx", "My File (1).tar.gz", "ünïcødé.txt", ".hidden", "a", "COM10.txt", "CONSOLE.log",
        "a" * 255, "😀" * 127 + "a",
        "می‌خواهم.txt",  # Persian with a zero-width non-joiner
        "\U0001f469‍\U0001f4bb notes.txt",  # emoji joined by a zero-width joiner
    ])
    def test_accepts_ordinary_names(self, name):
        assert file_ops.safe_original_name(name.encode()) == name

    @pytest.mark.parametrize("raw", [
        b"", b".", b"..", b"..\\evil.exe", b"sub/evil", b"C:\\Windows\\x", b"file.txt:stream",
        b"NUL", b"nul.txt", b"COM1", b"lpt9.log", b"trailing.", b"trailing ", b"tab\there",
        b"\xff\xfe broken utf8", b"x" * 256,
        b"CONIN$", b"conout$.txt", b"CLOCK$", "COM¹".encode(), "lpt³.log".encode(), "Com² .txt".encode(),
        "invoice\u202efdp.exe".encode(), "zero\u200bwidth.txt".encode(), "\ufeffbom.txt".encode(),
        b".0123456789abcdef.gfgpart", b"left.GFGPART",
        ("😀" * 128).encode(),
    ])
    def test_rejects_unsafe_names(self, raw):
        assert file_ops.safe_original_name(raw) is None


class TestOutcomes:
    """Every result says what happened in words the file list can show."""

    def test_done_names_the_written_file(self, backend, tmp_path, keys):
        result = file_ops.encrypt_file(_write(tmp_path / "f.bin", b"data"), keys, "gcm")
        assert (result.outcome, result.reason) == ("done", "")
        assert result.output == str(tmp_path / "f.bin.gfglock")

    def test_wrong_password_reason(self, backend, tmp_path, keys):
        encrypted = _encrypt(_write(tmp_path / "f.bin", b"data"), keys, "chacha")
        result = file_ops.decrypt_file(encrypted, KeyRing("wrong"))
        assert result.outcome == "failed" and result.output == ""
        assert result.reason.startswith("Wrong password")

    def test_plain_file_is_a_skip(self, tmp_path, keys):
        result = file_ops.decrypt_file(_write(tmp_path / "notes.txt", b"plain text"), keys)
        assert (result.outcome, result.reason) == ("skipped", "Not an encrypted gfgLock file")

    def test_missing_file_reason(self, tmp_path, keys):
        result = file_ops.decrypt_file(str(tmp_path / "gone.gfglock"), keys)
        assert result.outcome == "failed" and result.reason.startswith("File not found")


class TestSourceThatCantBeRemoved:
    """A file must never end up in both forms: if the original stays, the new copy goes."""

    def test_read_only_source_fails_before_any_work(self, backend, tmp_path, keys):
        source = _write(tmp_path / "ro.txt", b"keep me")
        os.chmod(source, 0o444)
        try:
            result = file_ops.encrypt_file(source, keys, "gcm")
            assert result.outcome == "failed" and "read-only" in result.reason.lower()
            assert sorted(os.listdir(tmp_path)) == ["ro.txt"]
        finally:
            os.chmod(source, 0o666)

    def test_locked_source_removes_the_new_copy(self, backend, tmp_path, keys, monkeypatch):
        source = _write(tmp_path / "busy.txt", b"open elsewhere")
        real_remove = os.remove

        def remove(path):
            if path == source:
                raise PermissionError(13, "The process cannot access the file")
            real_remove(path)

        monkeypatch.setattr(file_ops.os, "remove", remove)
        result = file_ops.encrypt_file(source, keys, "gcm")
        assert result.outcome == "failed" and "nothing was changed" in result.reason
        assert sorted(os.listdir(tmp_path)) == ["busy.txt"]

    def test_locked_encrypted_file_keeps_only_the_encrypted_copy(self, backend, tmp_path, keys, monkeypatch):
        encrypted = _encrypt(_write(tmp_path / "a.txt", b"secret"), keys)
        real_remove = os.remove

        def remove(path):
            if path == encrypted:
                raise PermissionError(13, "in use")
            real_remove(path)

        monkeypatch.setattr(file_ops.os, "remove", remove)
        assert file_ops.decrypt_file(encrypted, keys).outcome == "failed"
        assert sorted(os.listdir(tmp_path)) == [os.path.basename(encrypted)]


class TestSourceIdentity:
    """The file deleted at the end is the one that was read; a newer version replacing it survives."""

    @staticmethod
    def _change_source_before_delete(monkeypatch, source: Path, change) -> None:
        real_flush = file_ops._flush_to_disk

        def flush_then_change(path):
            real_flush(path)
            change(source)

        monkeypatch.setattr(file_ops, "_flush_to_disk", flush_then_change)

    @staticmethod
    def _replace(path: Path) -> None:
        """What an editor does on save: write a new file, then move it over the old one."""
        newer = path.with_name("newer.tmp")
        newer.write_bytes(b"version 2 - saved during encryption")
        os.replace(newer, path)

    @staticmethod
    def _append(path: Path) -> None:
        with open(path, "ab") as fh:
            fh.write(b" and more")

    @pytest.mark.parametrize("change", ["_replace", "_append"])
    def test_changed_source_is_never_deleted(self, backend, tmp_path, keys, monkeypatch, change):
        source = tmp_path / "doc.txt"
        source.write_bytes(b"version 1")
        self._change_source_before_delete(monkeypatch, source, getattr(self, change))

        result = file_ops.encrypt_file(str(source), keys, "gcm")

        assert result.outcome == "failed" and "nothing was changed" in result.reason
        assert sorted(os.listdir(tmp_path)) == ["doc.txt"]
        assert source.read_bytes() != b"version 1"

    def test_replaced_encrypted_file_is_never_deleted(self, backend, tmp_path, keys, monkeypatch):
        encrypted = Path(_encrypt(_write(tmp_path / "doc.txt", b"version 1"), keys))
        self._change_source_before_delete(monkeypatch, encrypted, self._replace)

        result = file_ops.decrypt_file(str(encrypted), keys)

        assert result.outcome == "failed" and "nothing was changed" in result.reason
        assert sorted(os.listdir(tmp_path)) == [encrypted.name]


class TestSkippedPaths:
    def test_leftover_temp_file_is_skipped(self, tmp_path, keys):
        temp = _write(tmp_path / (".0123456789abcdef" + file_ops.TEMP_SUFFIX), b"partial")
        assert file_ops.encrypt_file(temp, keys, "gcm").outcome == "skipped"
        assert os.path.exists(temp)

    def test_link_is_skipped_and_target_untouched(self, tmp_path, keys):
        target = _write(tmp_path / "target.txt", b"linked data")
        link = str(tmp_path / "link.txt")
        try:
            os.symlink(target, link)
        except OSError:
            pytest.skip("creating symbolic links needs Developer Mode or admin rights")
        result = file_ops.encrypt_file(link, keys, "gcm")
        assert result.outcome == "skipped" and "link" in result.reason.lower()
        assert sorted(os.listdir(tmp_path)) == ["link.txt", "target.txt"]

    def test_hard_linked_file_is_skipped(self, backend, tmp_path, keys):
        """Deleting one name of a hard-linked file would leave the data readable through the other."""
        original = _write(tmp_path / "original.txt", b"shared data")
        os.link(original, tmp_path / "other name.txt")

        result = file_ops.encrypt_file(original, keys, "gcm")

        assert (result.outcome, result.reason) == ("skipped", "Other hard links to this file would stay readable")
        assert sorted(os.listdir(tmp_path)) == ["original.txt", "other name.txt"]
        assert (tmp_path / "original.txt").read_bytes() == b"shared data"


class TestStaleTemps:
    def test_removes_only_temp_names(self, tmp_path):
        stale = [".0123456789abcdef.gfgpart", ".ABCDEF0123456789.GFGPART"]
        kept = [".0123456789abcde.gfgpart", "x.0123456789abcdef.gfgpart", ".0123456789abcdef.gfgpart.txt",
                ".0123456789abcdeg.gfgpart", "notes.txt"]
        for name in stale + kept:
            _write(tmp_path / name, b"x")
        (tmp_path / ".fedcba9876543210.gfgpart").mkdir()

        assert file_ops.remove_stale_temps([str(tmp_path)]) == 2
        assert sorted(os.listdir(tmp_path)) == sorted(kept + [".fedcba9876543210.gfgpart"])

    def test_file_still_open_is_left_alone(self, tmp_path):
        busy = tmp_path / ".00000000000000aa.gfgpart"
        busy.write_bytes(b"being written")
        with open(busy, "rb"):
            assert file_ops.remove_stale_temps([str(tmp_path)]) == 0
            assert busy.exists()
        assert file_ops.remove_stale_temps([str(tmp_path)]) == 1

    def test_missing_and_repeated_folders(self, tmp_path):
        _write(tmp_path / ".00000000000000bb.gfgpart", b"x")
        folders = [str(tmp_path / "gone"), str(tmp_path), str(tmp_path)]
        assert file_ops.remove_stale_temps(folders) == 1


class TestStopToken:
    def test_python_token(self, monkeypatch):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        token = file_ops.new_stop_token()
        assert isinstance(token, py_cipher.CancelToken) and not token.cancelled
        token.cancel()
        assert token.cancelled

    @pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE, reason="the native module (API 5) is not built")
    def test_native_token(self):
        token = file_ops.new_stop_token()
        assert not isinstance(token, py_cipher.CancelToken) and not token.cancelled
        token.cancel()
        assert token.cancelled
