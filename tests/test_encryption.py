# test_encryption.py - round trips, legacy v1 files, and the v2 format's integrity guarantees, run on
# the native engine (when its API 5 module is built) and on the Python engine.

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from gfglock.core import file_ops, format_v2, native_bridge, py_cipher
from gfglock.core.format_v2 import Header, KdfParams, KeyRing
from tests.v1_writer import HEADER_SIZES, SALT_SIZE, v1_bytes, v1_key

FIXTURES = Path(__file__).parent / "fixtures" / "v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
KEPT_FIXTURES = {"20261021120500_e5f6a7b8.gfglck"}  # hidden-name CFB: the restored name can't confirm it
CHUNK = 1 << format_v2.DEFAULT_CHUNK_LOG2
STRIDE = CHUNK + format_v2.TAG_SIZE
HEADER = format_v2.HEADER_SIZE
NAME = "data.bin"
METADATA = 2 + len(NAME) + 8
REPO = Path(__file__).resolve().parent.parent

requires_native = pytest.mark.skipif(not native_bridge.NATIVE_AVAILABLE,
                                     reason="the native module (API 5) is not built")


@pytest.fixture(params=[pytest.param(True, id="native", marks=requires_native), pytest.param(False, id="python")])
def engine(request, monkeypatch):
    """Run the test on the native engine, then on the Python one."""
    if not request.param:
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
    return request.param


def _encrypt(path, keys: KeyRing, algorithm: str = "gcm", **options) -> str:
    """Encrypt path through file_ops and return the encrypted file, failing the test otherwise."""
    result = file_ops.encrypt_file(str(path), keys, algorithm, **options)
    assert result.outcome == "done", result
    return result.output


def _reference_seal(algorithm: str, header: bytes, key: bytes, prefix: bytes, chunk: int, plain: bytes) -> bytes:
    """The v2 file the spec defines, computed directly with cryptography's one-shot AEADs."""
    aead = AESGCM(key) if algorithm == "gcm" else ChaCha20Poly1305(key)
    pieces = [plain[i:i + chunk] for i in range(0, len(plain), chunk)]
    return header + b"".join(aead.encrypt(format_v2.chunk_nonce(prefix, i, i == len(pieces) - 1), piece, header)
                             for i, piece in enumerate(pieces))


class TestV1Files:
    """Files written by gfgLock 3.1.0 keep opening, on both engines."""

    @pytest.mark.parametrize("name", sorted(MANIFEST["files"]))
    def test_fixture_decrypts_to_its_stored_name(self, engine, tmp_path, name):
        info = MANIFEST["files"][name]
        encrypted = shutil.copy(FIXTURES / name, tmp_path / name)

        result = file_ops.decrypt_file(str(encrypted), KeyRing(MANIFEST["password"]))

        assert result.outcome == "done", result
        assert os.path.basename(result.output) == info["stored_name"]
        assert hashlib.sha256(Path(result.output).read_bytes()).hexdigest() == info["sha256"]
        if name in KEPT_FIXTURES:
            assert os.path.exists(encrypted) and "CFB" in result.reason
        else:
            assert not os.path.exists(encrypted) and result.reason == ""

    @pytest.mark.parametrize("name", ["report.docx.gfglock", "notes.txt.gfglck", "photo.jpg.gfgcha"])
    def test_writer_matches_the_shipped_engines(self, name, sample_data):
        """tests/v1_writer.py reproduces a 3.1.0 file of each algorithm byte for byte."""
        info = MANIFEST["files"][name]
        raw = (FIXTURES / name).read_bytes()
        salt, iv = raw[:SALT_SIZE], raw[SALT_SIZE:HEADER_SIZES[info["algorithm"]] - 4]
        data = sample_data if info["size"] else b""

        rebuilt = v1_bytes(info["algorithm"], v1_key(MANIFEST["password"], salt), salt, iv,
                           info["stored_name"].encode("utf-8"), data)

        assert rebuilt == raw

    def test_wrong_password_fails_and_keeps_the_file(self, engine, tmp_path):
        encrypted = shutil.copy(FIXTURES / "photo.jpg.gfgcha", tmp_path)
        result = file_ops.decrypt_file(str(encrypted), KeyRing("not the password"))
        assert result.outcome == "failed" and "authentication failed" in result.reason
        assert sorted(os.listdir(tmp_path)) == ["photo.jpg.gfgcha"]

    def test_pycryptodome_loads_only_for_v1_chacha(self):
        """Start-up imports file_ops; pycryptodome is needed only to decrypt v1 ChaCha files."""
        code = "import sys, gfglock.core.file_ops; print('Crypto' in sys.modules)"
        done = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True)
        assert done.stdout.strip().splitlines()[-1] == "False"


class TestRoundTrip:
    @pytest.mark.parametrize("algorithm", file_ops.ENCRYPT_ALGORITHMS)
    @pytest.mark.parametrize("size, chunks", [
        (0, 1), (CHUNK - METADATA, 1), (CHUNK - METADATA + 1, 2), (3 * CHUNK + 5, 4),
    ], ids=["empty", "one-chunk", "one-chunk-plus-one", "four-chunks"])
    def test_round_trip(self, engine, tmp_path, keys, algorithm, size, chunks):
        data = os.urandom(size)
        source = tmp_path / NAME
        source.write_bytes(data)

        encrypted = _encrypt(source, keys, algorithm)

        assert encrypted == str(tmp_path / (NAME + file_ops.EXTENSIONS[algorithm]))
        raw = Path(encrypted).read_bytes()
        assert format_v2.parse_header(raw).algorithm == algorithm
        assert len(raw) == HEADER + METADATA + size + chunks * format_v2.TAG_SIZE
        result = file_ops.decrypt_file(encrypted, keys)
        assert (result.outcome, result.reason) == ("done", "")
        assert sorted(os.listdir(tmp_path)) == [NAME]
        assert source.read_bytes() == data

    @pytest.mark.parametrize("read_size", [0, 1, 100_000, 10**12], ids=["default", "tiny", "unaligned", "huge"])
    def test_any_read_size_gives_the_same_file(self, engine, tmp_path, keys, read_size):
        """Read sizes are clamped and aligned to whole chunks, so they never change the output."""
        data = os.urandom(3 * CHUNK + 5)
        header, key = keys.new_header("gcm")
        metadata = format_v2.pack_metadata(NAME, 0)
        source, sealed, opened = tmp_path / "in", tmp_path / "sealed", tmp_path / "opened"
        source.write_bytes(data)
        seal = native_bridge.seal_file if engine else py_cipher.seal_stream
        open_stream = native_bridge.open_file if engine else py_cipher.open_stream

        ok, error = seal("gcm", str(source), str(sealed), header.pack(), key, header.nonce_prefix,
                         header.chunk_size, metadata, read_size)
        assert ok, error
        ok, error, stored = open_stream("gcm", str(sealed), str(opened), header.pack(), key,
                                        header.nonce_prefix, header.chunk_size, read_size)

        assert ok, error
        assert stored == metadata and opened.read_bytes() == data
        assert sealed.read_bytes() == _reference_seal("gcm", header.pack(), key, header.nonce_prefix,
                                                       header.chunk_size, metadata + data)

    @pytest.mark.parametrize("requested, used", [
        (0, 4 << 20), (-5, 4 << 20), (1, 64 << 10), (1 << 20, 1 << 20), (10**12, 64 << 20),
    ])
    def test_read_size_is_clamped_like_the_native_engine(self, requested, used):
        assert py_cipher._block_size(requested) == used

    def test_hidden_name_round_trip(self, engine, tmp_path, keys):
        source = tmp_path / "salary 2026.xlsx"
        source.write_bytes(b"numbers")
        encrypted = _encrypt(source, keys, "chacha", encrypt_name=True)
        assert re.fullmatch(r"\d{14}_[0-9a-f]{8}\.gfgcha", os.path.basename(encrypted))
        assert file_ops.decrypt_file(encrypted, keys).outcome == "done"
        assert sorted(os.listdir(tmp_path)) == ["salary 2026.xlsx"]

    def test_progress_counts_every_input_byte(self, engine, tmp_path, keys):
        source = tmp_path / NAME
        source.write_bytes(os.urandom(2 * CHUNK + 3))
        reported: list[float] = []
        encrypted = _encrypt(source, keys, progress=reported.append)
        assert sum(reported) == 2 * CHUNK + 3
        size = os.path.getsize(encrypted)
        reported.clear()
        assert file_ops.decrypt_file(encrypted, keys, progress=reported.append).outcome == "done"
        assert sum(reported) == size


class TestLayout:
    """Both engines write exactly the file the spec defines, so each opens the other's files."""

    @pytest.mark.parametrize("algorithm", file_ops.ENCRYPT_ALGORITHMS)
    def test_fixed_inputs_give_the_reference_bytes(self, engine, tmp_path, algorithm):
        header = Header(algorithm, KdfParams(64, 1, 1), b"k" * 16, b"f" * 16, b"n" * 7, chunk_log2=16)
        key, data = bytes(range(32)), bytes(range(256)) * 600
        metadata = format_v2.pack_metadata("fixed.bin", 1_700_000_000_000_000_000)
        source, sealed = tmp_path / "in", tmp_path / "out"
        source.write_bytes(data)
        seal = native_bridge.seal_file if engine else py_cipher.seal_stream

        ok, error = seal(algorithm, str(source), str(sealed), header.pack(), key, header.nonce_prefix,
                         header.chunk_size, metadata)

        assert ok, error
        assert sealed.read_bytes() == _reference_seal(algorithm, header.pack(), key, header.nonce_prefix,
                                                       header.chunk_size, metadata + data)

    def test_open_needs_the_stored_header(self, engine, tmp_path, keys):
        header, key = keys.new_header("chacha")
        source, sealed, opened = tmp_path / "in", tmp_path / "sealed", tmp_path / "opened"
        source.write_bytes(b"data")
        assert py_cipher.seal_stream("chacha", str(source), str(sealed), header.pack(), key, header.nonce_prefix,
                                     header.chunk_size, format_v2.pack_metadata(NAME, 0))[0]
        other = bytearray(header.pack())
        other[-1] ^= 0x01
        open_stream = native_bridge.open_file if engine else py_cipher.open_stream

        result = open_stream("chacha", str(sealed), str(opened), bytes(other), key, header.nonce_prefix,
                             header.chunk_size)

        assert result == (False, "wrong password or the file was modified (authentication failed)", b"")

    @pytest.mark.parametrize("change, message", [
        ({"algorithm": "cfb"}, "CFB only decrypts v1 files"),
        ({"key": b"short"}, "key must be 32 bytes"),
        ({"nonce_prefix": b"p" * 8}, "nonce_prefix must be 7 bytes"),
        ({"chunk_size": 3 << 16}, "chunk_size must be a power of two"),
        ({"metadata": b"\x00\x05abc"}, "metadata must be one v2 metadata block"),
    ])
    def test_bad_arguments_are_reported(self, engine, tmp_path, change, message):
        source = tmp_path / "in"
        source.write_bytes(b"data")
        arguments = {"algorithm": "gcm", "input_path": str(source), "output_path": str(tmp_path / "out"),
                     "header": b"h" * HEADER, "key": b"k" * 32, "nonce_prefix": b"p" * 7,
                     "chunk_size": CHUNK, "metadata": format_v2.pack_metadata(NAME, 0)} | change
        seal = native_bridge.seal_file if engine else py_cipher.seal_stream

        ok, error = seal(**arguments)

        assert not ok and error.startswith(message)

    @requires_native
    @pytest.mark.parametrize("algorithm", file_ops.ENCRYPT_ALGORITHMS)
    @pytest.mark.parametrize("native_writes", [True, False], ids=["native-to-python", "python-to-native"])
    def test_other_engine_opens_the_file(self, tmp_path, keys, monkeypatch, algorithm, native_writes):
        data = os.urandom(2 * CHUNK + 77)
        source = tmp_path / NAME
        source.write_bytes(data)
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", native_writes)
        encrypted = _encrypt(source, keys, algorithm)
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", not native_writes)

        result = file_ops.decrypt_file(encrypted, keys)

        assert result.outcome == "done", result
        assert source.read_bytes() == data


class TestIntegrity:
    """Any change to a v2 file fails to open and keeps it, on both engines."""

    @staticmethod
    def _encrypted(folder: Path, keys: KeyRing, size: int = 2 * CHUNK + 500) -> Path:
        source = folder / NAME
        source.write_bytes(os.urandom(size))
        return Path(_encrypt(source, keys))

    @staticmethod
    def _assert_rejected(encrypted: Path, keys: KeyRing, message: str) -> None:
        before = encrypted.read_bytes()
        result = file_ops.decrypt_file(str(encrypted), keys)
        assert result.outcome == "failed" and message in result[1], result
        assert sorted(os.listdir(encrypted.parent)) == [encrypted.name]
        assert encrypted.read_bytes() == before

    @pytest.mark.parametrize("offset, xor, message", [
        (0, 0x01, "authentication failed"),   # magic: read as a v1 file, which fails its tag
        (7, 0x01, "newer gfgLock"),           # version 2 -> 3
        (8, 0x03, "authentication failed"),   # algorithm 1 -> 2: another key and cipher
        (8, 0x01, "encryption method"),       # algorithm 1 -> 0: unknown
        (9, 0x01, "newer gfgLock"),           # KDF id
        (13, 0x01, "authentication failed"),  # Argon2 memory
        (17, 0x02, "authentication failed"),  # Argon2 iterations
        (18, 0x02, "authentication failed"),  # Argon2 lanes
        (19, 0x01, "authentication failed"),  # chunk size
        (20, 0x01, "newer gfgLock"),          # flags
        (21, 0x80, "authentication failed"),  # KDF salt
        (37, 0x80, "authentication failed"),  # file salt
        (53, 0x80, "authentication failed"),  # nonce prefix
    ], ids=["magic", "version", "algorithm", "unknown-algorithm", "kdf", "memory", "iterations", "lanes",
            "chunk-size", "flags", "kdf-salt", "file-salt", "nonce-prefix"])
    def test_header_change_fails(self, engine, tmp_path, keys, offset, xor, message):
        encrypted = self._encrypted(tmp_path, keys)
        raw = bytearray(encrypted.read_bytes())
        raw[offset] ^= xor
        encrypted.write_bytes(bytes(raw))
        self._assert_rejected(encrypted, keys, message)

    @pytest.mark.parametrize("change, message", [
        (lambda raw: raw[:HEADER + 2 * STRIDE], "authentication failed"),
        (lambda raw: raw[:HEADER + 2 * STRIDE + 10], "truncated or corrupted"),
        (lambda raw: raw[:HEADER], "truncated or corrupted"),
        (lambda raw: raw[:HEADER] + raw[HEADER + STRIDE:HEADER + 2 * STRIDE] + raw[HEADER:HEADER + STRIDE]
         + raw[HEADER + 2 * STRIDE:], "authentication failed"),
        (lambda raw: raw[:-1] + bytes([raw[-1] ^ 0x01]), "authentication failed"),
        (lambda raw: raw + b"\x00", "authentication failed"),
        (lambda raw: raw + raw[HEADER:HEADER + STRIDE], "authentication failed"),
    ], ids=["cut-at-chunk-boundary", "cut-inside-tag", "header-only", "chunks-swapped", "tag-flipped",
            "byte-appended", "chunk-appended"])
    def test_body_change_fails(self, engine, tmp_path, keys, change, message):
        encrypted = self._encrypted(tmp_path, keys)
        encrypted.write_bytes(change(encrypted.read_bytes()))
        self._assert_rejected(encrypted, keys, message)

    def test_wrong_password_stops_at_the_first_chunk(self, monkeypatch, tmp_path, keys, password):
        """Checked on the Python engine, which reports what it read when it fails (native reports nothing then)."""
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        encrypted = self._encrypted(tmp_path, keys, size=4 * CHUNK)
        reported: list[float] = []

        result = file_ops.decrypt_file(str(encrypted), KeyRing("wrong " + password), read_size=1 << 16,
                                       progress=reported.append)

        assert result.outcome == "failed" and result.reason.startswith("Wrong password")
        assert sum(reported) < os.path.getsize(encrypted)
        assert sorted(os.listdir(tmp_path)) == [encrypted.name]

    def test_v2_file_renamed_to_cfb_extension_opens_as_v2(self, engine, tmp_path, keys):
        source = tmp_path / "notes.txt"
        source.write_bytes(b"authenticated")
        renamed = tmp_path / "anything.gfglck"
        os.rename(_encrypt(source, keys), renamed)

        result = file_ops.decrypt_file(str(renamed), keys)

        assert (result.outcome, result.reason) == ("done", "")
        assert sorted(os.listdir(tmp_path)) == ["notes.txt"]

    @pytest.mark.parametrize("extension", [".gfglock", ".gfglck"])
    def test_a_newer_version_says_so_and_keeps_the_file(self, engine, tmp_path, keys, extension):
        encrypted = self._encrypted(tmp_path, keys)
        newer = tmp_path / f"from_3.3{extension}"
        os.rename(encrypted, newer)
        with open(newer, "r+b") as fh:
            fh.seek(len(format_v2.MAGIC))
            fh.write(bytes([format_v2.VERSION + 1]))

        result = file_ops.decrypt_file(str(newer), keys)

        assert result.outcome == "failed" and "newer gfgLock version" in result.reason
        assert sorted(os.listdir(tmp_path)) == [newer.name]

    def test_short_output_from_an_engine_keeps_the_encrypted_file(self, monkeypatch, tmp_path, keys):
        monkeypatch.setattr(native_bridge, "NATIVE_AVAILABLE", False)
        encrypted = self._encrypted(tmp_path, keys)
        open_stream = py_cipher.open_stream

        def dropping_a_byte(*args, **kwargs):
            result = open_stream(*args, **kwargs)
            with open(args[2], "r+b") as fh:
                fh.truncate(os.path.getsize(args[2]) - 1)
            return result

        monkeypatch.setattr(py_cipher, "open_stream", dropping_a_byte)
        result = file_ops.decrypt_file(str(encrypted), keys)

        assert result.outcome == "failed" and "incomplete" in result.reason
        assert sorted(os.listdir(tmp_path)) == [encrypted.name]


class TestStop:
    """A stop token ends the file in progress as skipped: no output, no temp file, source untouched."""

    def test_stop_from_the_progress_callback(self, engine, tmp_path, keys):
        source = tmp_path / "large.bin"
        with open(source, "wb") as fh:
            # Zeros that cost no disk writes; progress is reported every 100 MB, so the file must pass that.
            fh.truncate(py_cipher.PROGRESS_UPDATE_INTERVAL + 3 * py_cipher.BUFFER_SIZE)
        before = os.stat(source)
        stop = file_ops.new_stop_token()

        result = file_ops.encrypt_file(str(source), keys, "gcm", progress=lambda _n: stop.cancel(), stop=stop)

        assert (result.outcome, result.reason) == ("skipped", "Stopped before it finished; the file was not changed")
        assert stop.cancelled
        assert sorted(os.listdir(tmp_path)) == ["large.bin"]
        assert (os.stat(source).st_size, os.stat(source).st_mtime_ns) == (before.st_size, before.st_mtime_ns)

    def test_stopped_decrypt_keeps_the_encrypted_file(self, engine, tmp_path, keys):
        source = tmp_path / NAME
        source.write_bytes(os.urandom(2 * CHUNK))
        encrypted = _encrypt(source, keys)
        stop = file_ops.new_stop_token()
        stop.cancel()

        result = file_ops.decrypt_file(encrypted, keys, stop=stop)

        assert result.outcome == "skipped" and result.reason.startswith("Stopped")
        assert sorted(os.listdir(tmp_path)) == [os.path.basename(encrypted)]


class TestMetadata:
    def test_mtime_and_mark_of_the_web_are_restored(self, engine, tmp_path, keys):
        source = tmp_path / "download.pdf"
        source.write_bytes(b"%PDF-1.7")
        mtime_ns = 1_500_000_000_123_456_700  # NTFS keeps 100 ns steps
        os.utime(source, ns=(1_600_000_000_000_000_000, mtime_ns))
        encrypted = _encrypt(source, keys)
        mark = b"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://example.com/file.pdf\r\n"
        with open(encrypted + ":Zone.Identifier", "wb") as fh:
            fh.write(mark)

        result = file_ops.decrypt_file(encrypted, keys)

        assert result.outcome == "done", result
        assert os.stat(result.output).st_mtime_ns == mtime_ns
        with open(result.output + ":Zone.Identifier", "rb") as fh:
            assert fh.read() == mark

    def test_mark_of_the_web_survives_encrypt_and_decrypt(self, engine, tmp_path, keys):
        source = tmp_path / "invoice.docm"
        source.write_bytes(b"macros")
        mark = b"[ZoneTransfer]\r\nZoneId=3\r\n"
        with open(str(source) + ":Zone.Identifier", "wb") as fh:
            fh.write(mark)

        encrypted = _encrypt(source, keys)
        with open(encrypted + ":Zone.Identifier", "rb") as fh:
            assert fh.read() == mark
        result = file_ops.decrypt_file(encrypted, keys)

        assert result.outcome == "done", result
        with open(result.output + ":Zone.Identifier", "rb") as fh:
            assert fh.read() == mark

    def test_a_time_outside_64_bits_still_encrypts(self, engine, tmp_path, keys):
        """NTFS allows times back to 1601; the earliest ones don't fit in an i64 of nanoseconds."""
        source = tmp_path / "old.txt"
        source.write_bytes(b"very old")
        os.utime(source, ns=(1_600_000_000_000_000_000, -11_644_473_599_999_999_900))

        encrypted = _encrypt(source, keys)
        result = file_ops.decrypt_file(encrypted, keys)

        assert result.outcome == "done", result
        assert Path(result.output).read_bytes() == b"very old"

    @requires_native
    def test_a_path_the_native_engine_cant_take_uses_the_python_one(self, tmp_path, keys):
        """A lone surrogate is a valid NTFS name but not valid UTF-8, which the native engine needs."""
        folder = tmp_path / "odd\ud800name"
        folder.mkdir()
        source = folder / "notes.txt"
        source.write_bytes(b"still encrypted")

        result = file_ops.decrypt_file(_encrypt(source, keys), keys)

        assert result.outcome == "done", result
        assert Path(result.output).read_bytes() == b"still encrypted"

    def test_unmarked_file_gets_no_mark(self, engine, tmp_path, keys):
        source = tmp_path / "local.txt"
        source.write_bytes(b"made here")
        result = file_ops.decrypt_file(_encrypt(source, keys), keys)
        assert result.outcome == "done"
        with pytest.raises(FileNotFoundError):
            open(result.output + ":Zone.Identifier", "rb").close()
