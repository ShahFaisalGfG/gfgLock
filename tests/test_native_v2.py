"""Tests for the native engine (gfglock_native API 5): v2 seal/open, v1 decrypt, cancel, and locking.

Every v2 file is compared with one built here from cryptography's AEAD classes and
format_v2.chunk_nonce, so the layout is checked independently of py_cipher.
"""

import ctypes
import hashlib
import json
import random
import sys
import threading
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from gfglock.core import format_v2

_CORE = Path(__file__).resolve().parents[1] / "gfglock" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
native = pytest.importorskip("gfglock_native")
if getattr(native, "API_VERSION", 0) < 5:
    pytest.skip("gfglock_native is older than API 5; run scripts/build_native.ps1", allow_module_level=True)

AUTH_FAILED = "wrong password or the file was modified (authentication failed)"
TRUNCATED = "the file is truncated or corrupted"
CORRUPTED = "the file is corrupted"
SIZE_CHANGED = "the source file changed size while it was being read"
STOPPED = format_v2.ENGINE_STOPPED

KEY = bytes(range(32))
PREFIX = bytes.fromhex("a1b2c3d4e5f607")
CHUNK_LOG2 = 16
CHUNK = 1 << CHUNK_LOG2
UNIT = CHUNK + format_v2.TAG_SIZE
NAME = "résumé ü.pdf"
METADATA = format_v2.pack_metadata(NAME, 1_700_000_000_123_456_789)
AEADS = {"gcm": AESGCM, "chacha": ChaCha20Poly1305}
ALGORITHMS = tuple(AEADS)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "v1"
BIG_SIZE = 128 * 1024 * 1024 + 3  # past the 100 MB progress interval, so the callback fires mid-file


def _data(size: int, seed: int = 7) -> bytes:
    return random.Random(seed).randbytes(size)


def _header(algorithm: str, chunk_log2: int = CHUNK_LOG2) -> bytes:
    return format_v2.Header(algorithm, format_v2.KdfParams(64, 1, 1), bytes(16), bytes(range(16, 32)),
                            PREFIX, chunk_log2).pack()


def _reference(algorithm: str, plaintext: bytes, chunk_log2: int = CHUNK_LOG2, key: bytes = KEY) -> bytes:
    """The v2 file for this plaintext stream (metadata + data), built with cryptography alone."""
    header = _header(algorithm, chunk_log2)
    chunk = 1 << chunk_log2
    pieces = [plaintext[i:i + chunk] for i in range(0, len(plaintext), chunk)] or [b""]
    aead = AEADS[algorithm](key)
    sealed = (aead.encrypt(format_v2.chunk_nonce(PREFIX, i, i == len(pieces) - 1), piece, header)
              for i, piece in enumerate(pieces))
    return header + b"".join(sealed)


def _seal(src: Path, dst: Path, algorithm: str, chunk_log2: int = CHUNK_LOG2, **options):
    return native.seal_file(algorithm, str(src), str(dst), header=_header(algorithm, chunk_log2), key=KEY,
                            nonce_prefix=PREFIX, chunk_size=1 << chunk_log2, metadata=METADATA, **options)


def _open(src: Path, dst: Path, algorithm: str, chunk_log2: int = CHUNK_LOG2, header: bytes | None = None,
          key: bytes = KEY, **options):
    return native.open_file(algorithm, str(src), str(dst), header=header or _header(algorithm, chunk_log2),
                            key=key, nonce_prefix=PREFIX, chunk_size=1 << chunk_log2, **options)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _call_in_thread(fn, timeout: float = 120.0):
    """Run fn on a worker thread and return its result; fails instead of hanging the suite."""
    result = []
    worker = threading.Thread(target=lambda: result.append(fn()), daemon=True)
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), "the native call did not return"
    return result[0]


class TestModule:
    def test_api_version_and_names(self):
        assert native.API_VERSION == 5
        for name in ("seal_file", "open_file", "decrypt_file_v1", "pbkdf2_sha256", "CancelToken"):
            assert hasattr(native, name), name
        assert not hasattr(native, "encrypt_file")
        assert not hasattr(native, "decrypt_file")

    def test_openssl_versions_match(self):
        runtime, built = native.openssl_version(), native.openssl_build_version()
        assert runtime.count(".") == 2 and runtime.split(".")[0] == "3"
        assert runtime == built

    def test_pbkdf2_matches_hashlib(self):
        salt = bytes(range(16))
        expected = hashlib.pbkdf2_hmac("sha256", b"p\xc3\xa4ss", salt, 1000, 32)
        assert native.pbkdf2_sha256("päss", salt, 1000, 32) == expected

    @pytest.mark.parametrize("iterations, dklen", [(0, 32), (1000, 0), (1000, 1025)])
    def test_pbkdf2_rejects_bad_sizes(self, iterations, dklen):
        with pytest.raises(ValueError):
            native.pbkdf2_sha256("pass", b"salt", iterations, dklen)


class TestCancelToken:
    def test_cancel_sets_cancelled(self):
        token = native.CancelToken()
        assert token.cancelled is False
        token.cancel()
        token.cancel()
        assert token.cancelled is True

    def test_cancelled_is_read_only(self):
        token = native.CancelToken()
        with pytest.raises(AttributeError):
            token.cancelled = True


class TestSeal:
    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    @pytest.mark.parametrize("size", [0, 1, CHUNK - len(METADATA), CHUNK - len(METADATA) + 1, 3 * CHUNK + 12345])
    def test_matches_independent_layout(self, tmp_path, algorithm, size):
        data = _data(size)
        src = _write(tmp_path / "plain.bin", data)
        dst = tmp_path / "sealed.v2"
        assert _seal(src, dst, algorithm) == (True, "")
        sealed = dst.read_bytes()
        assert sealed == _reference(algorithm, METADATA + data)
        assert len(sealed) == format_v2.encrypted_size(size, NAME, CHUNK_LOG2)

    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    def test_block_sizes_give_identical_output(self, tmp_path, algorithm):
        data = _data(5 * 1024 * 1024 + 777)
        src = _write(tmp_path / "plain.bin", data)
        expected = _reference(algorithm, METADATA + data)
        for block_size in (64 * 1024, 1024 * 1024, 4 * 1024 * 1024, 64 * 1024 * 1024):
            dst = tmp_path / f"sealed-{block_size}.v2"
            out = tmp_path / f"opened-{block_size}.bin"
            assert _seal(src, dst, algorithm, block_size=block_size) == (True, "")
            assert dst.read_bytes() == expected, block_size
            assert _open(dst, out, algorithm, block_size=block_size) == (True, "", METADATA)
            assert out.read_bytes() == data

    def test_chunk_larger_than_read_size(self, tmp_path):
        data = _data((1 << 24) + 5)
        src = _write(tmp_path / "plain.bin", data)
        dst = tmp_path / "sealed.v2"
        assert _seal(src, dst, "gcm", chunk_log2=24, block_size=64 * 1024) == (True, "")
        assert dst.read_bytes() == _reference("gcm", METADATA + data, chunk_log2=24)

    def test_progress_counts_source_bytes(self, tmp_path):
        data = _data(300_000)
        src = _write(tmp_path / "plain.bin", data)
        seen = []
        assert _seal(src, tmp_path / "sealed.v2", "gcm", callback=seen.append) == (True, "")
        assert sum(seen) == len(data)
        assert all(isinstance(n, int) for n in seen)

    def test_missing_source(self, tmp_path):
        assert _seal(tmp_path / "missing.bin", tmp_path / "sealed.v2", "gcm") == (False, "cannot open the source file")

    def test_source_is_read_share_only_while_sealing(self, tmp_path):
        src = _write(tmp_path / "plain.bin", _data(200_000))
        attempts = {}

        def probe(_n):
            for mode in ("rb", "r+b"):
                try:
                    with open(src, mode):
                        attempts[mode] = "opened"
                except PermissionError:
                    attempts[mode] = "refused"

        assert _seal(src, tmp_path / "sealed.v2", "gcm", callback=probe) == (True, "")
        assert attempts == {"rb": "opened", "r+b": "refused"}
        with open(src, "r+b"):
            pass

    def test_source_already_open_for_writing(self, tmp_path):
        src = _write(tmp_path / "plain.bin", _data(1000))
        with open(src, "r+b"):
            assert _seal(src, tmp_path / "sealed.v2", "gcm") == (False, "the file is open in another program")

    def test_source_that_grows_is_rejected(self, tmp_path):
        with _GrowingSource(first=b"x" * 100, more=b"y" * 100) as source:
            result = _call_in_thread(lambda: _seal(source.path, tmp_path / "sealed.v2", "gcm",
                                                   callback=lambda _n: source.grow()))
        assert result == (False, SIZE_CHANGED)

    @pytest.mark.parametrize("changes, message", [
        ({"key": bytes(31)}, "key must be 32 bytes"),
        ({"nonce_prefix": bytes(8)}, "nonce_prefix must be 7 bytes"),
        ({"chunk_size": 3 << 16}, "chunk_size must be a power of two"),
        ({"chunk_size": 1 << 15}, "chunk_size must be a power of two"),
        ({"chunk_size": 1 << 25}, "chunk_size must be a power of two"),
        ({"header": b""}, "header must be"),
        ({"metadata": b"\x00\x00" + bytes(8)}, "metadata must be one v2 metadata block"),
        ({"metadata": METADATA + b"x"}, "metadata must be one v2 metadata block"),
        ({"algorithm": "cfb"}, "CFB only decrypts v1 files"),
        ({"algorithm": "xts"}, "unknown algorithm 'xts'"),
    ])
    def test_rejects_arguments_outside_the_limits(self, tmp_path, changes, message):
        src = _write(tmp_path / "plain.bin", b"data")
        args = {"algorithm": "gcm", "input_path": str(src), "output_path": str(tmp_path / "sealed.v2"),
                "header": _header("gcm"), "key": KEY, "nonce_prefix": PREFIX, "chunk_size": CHUNK,
                "metadata": METADATA} | changes
        with pytest.raises(ValueError, match=message):
            native.seal_file(**args)


class TestOpen:
    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    @pytest.mark.parametrize("size", [0, 1, CHUNK - len(METADATA), 2 * CHUNK + 99])
    def test_round_trip_of_independent_file(self, tmp_path, algorithm, size):
        data = _data(size, seed=size)
        src = _write(tmp_path / "file.v2", _reference(algorithm, METADATA + data))
        out = tmp_path / "plain.bin"
        assert _open(src, out, algorithm) == (True, "", METADATA)
        assert out.read_bytes() == data

    def test_progress_counts_the_whole_file(self, tmp_path):
        src = _write(tmp_path / "file.v2", _reference("chacha", METADATA + _data(300_000)))
        seen = []
        assert _open(src, tmp_path / "plain.bin", "chacha", callback=seen.append)[0]
        assert sum(seen) == src.stat().st_size

    def test_empty_body(self, tmp_path):
        src = _write(tmp_path / "file.v2", _header("gcm"))
        assert _open(src, tmp_path / "plain.bin", "gcm") == (False, TRUNCATED, b"")

    @pytest.mark.parametrize("remainder", [1, 16])
    @pytest.mark.parametrize("full_chunks", [0, 2])
    def test_final_remainder_too_short(self, tmp_path, remainder, full_chunks):
        sealed = _reference("gcm", METADATA + _data(3 * CHUNK))
        cut = len(_header("gcm")) + full_chunks * UNIT + remainder
        src = _write(tmp_path / "file.v2", sealed[:cut])
        assert _open(src, tmp_path / "plain.bin", "gcm") == (False, TRUNCATED, b"")

    def test_tag_only_final_chunk(self, tmp_path):
        src = _write(tmp_path / "file.v2", _reference("gcm", b""))
        assert _open(src, tmp_path / "plain.bin", "gcm") == (False, TRUNCATED, b"")

    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    def test_truncated_at_a_chunk_boundary(self, tmp_path, algorithm):
        sealed = _reference(algorithm, METADATA + _data(3 * CHUNK))
        src = _write(tmp_path / "file.v2", sealed[:len(_header(algorithm)) + 2 * UNIT])
        assert _open(src, tmp_path / "plain.bin", algorithm) == (False, AUTH_FAILED, b"")

    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    def test_tampered_chunk_is_never_written(self, tmp_path, algorithm):
        data = _data(3 * CHUNK)
        sealed = bytearray(_reference(algorithm, METADATA + data))
        sealed[len(_header(algorithm)) + UNIT + 10] ^= 0x01
        src = _write(tmp_path / "file.v2", bytes(sealed))
        out = tmp_path / "plain.bin"
        assert _open(src, out, algorithm, block_size=CHUNK) == (False, AUTH_FAILED, b"")
        written = out.read_bytes()
        assert len(written) <= CHUNK - len(METADATA)
        assert written == data[:len(written)]

    def test_reordered_chunks(self, tmp_path):
        sealed = _reference("gcm", METADATA + _data(3 * CHUNK))
        start = len(_header("gcm"))
        chunks = [sealed[start + i * UNIT:start + (i + 1) * UNIT] for i in range(4)]
        swapped = sealed[:start] + chunks[1] + chunks[0] + b"".join(chunks[2:])
        src = _write(tmp_path / "file.v2", swapped)
        assert _open(src, tmp_path / "plain.bin", "gcm") == (False, AUTH_FAILED, b"")

    @pytest.mark.parametrize("algorithm", ALGORITHMS)
    def test_wrong_key(self, tmp_path, algorithm):
        src = _write(tmp_path / "file.v2", _reference(algorithm, METADATA + _data(1000)))
        wrong = bytes([KEY[0] ^ 1]) + KEY[1:]
        assert _open(src, tmp_path / "plain.bin", algorithm, key=wrong) == (False, AUTH_FAILED, b"")

    def test_tampered_header(self, tmp_path):
        sealed = bytearray(_reference("gcm", METADATA + _data(1000)))
        sealed[30] ^= 0x01  # a KDF salt byte; the caller parses the stored header and passes it on
        src = _write(tmp_path / "file.v2", bytes(sealed))
        header = bytes(sealed[:len(_header("gcm"))])
        assert _open(src, tmp_path / "plain.bin", "gcm", header=header) == (False, AUTH_FAILED, b"")

    def test_header_that_differs_from_the_file(self, tmp_path):
        src = _write(tmp_path / "file.v2", _reference("gcm", METADATA + _data(1000)))
        other = _header("gcm")[:-1] + b"\x00"
        assert _open(src, tmp_path / "plain.bin", "gcm", header=other) == (False, AUTH_FAILED, b"")

    @pytest.mark.parametrize("plaintext", [
        b"\x00",
        b"\x00\x00" + bytes(8) + b"data",
        b"\x04\x01" + bytes(1025 + 8),
        b"\x00\x05" + b"name." + bytes(7),
    ], ids=["one-byte", "empty-name", "name-too-long", "short-mtime"])
    def test_bad_metadata(self, tmp_path, plaintext):
        src = _write(tmp_path / "file.v2", _reference("gcm", plaintext))
        assert _open(src, tmp_path / "plain.bin", "gcm") == (False, CORRUPTED, b"")

    def test_rejects_cfb(self, tmp_path):
        src = _write(tmp_path / "file.v2", _reference("gcm", METADATA))
        with pytest.raises(ValueError, match="CFB only decrypts v1 files"):
            _open(src, tmp_path / "plain.bin", "cfb", header=_header("gcm"))


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """A folder with a BIG_SIZE plaintext (zeros) and its sealed copy; emptied after the module."""
    folder = tmp_path_factory.mktemp("big")
    with open(folder / "big.bin", "wb") as fh:
        fh.truncate(BIG_SIZE)
    assert _seal(folder / "big.bin", folder / "big.v2", "gcm") == (True, "")
    yield folder
    for path in folder.iterdir():
        path.unlink()


class TestCancel:
    @staticmethod
    def _stopping(token, seen):
        def callback(n):
            seen.append(n)
            token.cancel()
        return callback

    def test_seal_stops_from_the_callback(self, big):
        token, seen = native.CancelToken(), []
        result = _call_in_thread(lambda: _seal(big / "big.bin", big / "out.v2", "gcm", block_size=1 << 20,
                                               cancel=token, callback=self._stopping(token, seen)))
        assert result == (False, STOPPED)
        assert 0 < sum(seen) < BIG_SIZE

    def test_open_stops_from_the_callback(self, big):
        token, seen = native.CancelToken(), []
        sealed = big / "big.v2"
        result = _call_in_thread(lambda: _open(sealed, big / "out.bin", "gcm", block_size=1 << 20,
                                               cancel=token, callback=self._stopping(token, seen)))
        assert result == (False, STOPPED, b"")
        assert 0 < sum(seen) < sealed.stat().st_size

    def test_token_cancelled_before_the_call(self, tmp_path):
        token = native.CancelToken()
        token.cancel()
        src = _write(tmp_path / "plain.bin", _data(1000))
        sealed = _write(tmp_path / "file.v2", _reference("gcm", METADATA + _data(1000)))
        v1 = FIXTURES / "report.docx.gfglock"
        assert _seal(src, tmp_path / "a.v2", "gcm", cancel=token) == (False, STOPPED)
        assert _open(sealed, tmp_path / "b.bin", "gcm", cancel=token) == (False, STOPPED, b"")
        assert native.decrypt_file_v1("gcm", str(v1), str(tmp_path / "c.bin"), "x", cancel=token) == (False, STOPPED, b"")


def _manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


class TestDecryptV1:
    @pytest.mark.parametrize("name", sorted(_manifest()["files"]))
    def test_opens_every_fixture(self, tmp_path, name):
        manifest = _manifest()
        entry = manifest["files"][name]
        src = FIXTURES / name
        out = tmp_path / "plain.bin"
        seen = []
        ok, error, stored = native.decrypt_file_v1(entry["algorithm"], str(src), str(out), manifest["password"],
                                                   callback=seen.append)
        assert (ok, error) == (True, "")
        assert stored == entry["stored_name"].encode("utf-8")
        assert hashlib.sha256(out.read_bytes()).hexdigest() == entry["sha256"]
        assert sum(seen) == src.stat().st_size

    @pytest.mark.parametrize("name", ["report.docx.gfglock", "photo.jpg.gfgcha"])
    def test_wrong_password(self, tmp_path, name):
        algorithm = _manifest()["files"][name]["algorithm"]
        result = native.decrypt_file_v1(algorithm, str(FIXTURES / name), str(tmp_path / "plain.bin"), "wrong")
        assert result == (False, AUTH_FAILED, b"")


class _GrowingSource:
    """A named pipe posing as a source file: it holds more bytes than its size at open said.

    Local files can't change while the engine holds them read-share only, so a pipe stands in for
    the network or filter-driver volumes the size check guards against. The pipe first gets
    `first` once the engine connects, then `more` when grow() is called from the progress callback.
    """

    def __init__(self, first: bytes, more: bytes):
        self.path = Path(rf"\\.\pipe\gfglock-test-{uuid.uuid4().hex}")
        self._first, self._more = first, more
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        self._kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                                    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
        self._kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        self._kernel32.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._handle = None
        self._server = None

    def __enter__(self):
        pipe_access_outbound, buffer = 0x2, 1 << 16
        handle = self._kernel32.CreateNamedPipeW(str(self.path), pipe_access_outbound, 0, 1, buffer, buffer, 0, None)
        if handle in (None, wintypes.HANDLE(-1).value):
            pytest.skip(f"named pipes are unavailable (error {ctypes.get_last_error()})")
        self._handle = handle
        self._server = threading.Thread(target=self._serve, daemon=True)
        self._server.start()
        return self

    def _serve(self):
        self._kernel32.ConnectNamedPipe(self._handle, None)
        self._send(self._first)

    def _send(self, data: bytes):
        written = wintypes.DWORD()
        self._kernel32.WriteFile(self._handle, data, len(data), ctypes.byref(written), None)

    def grow(self):
        self._send(self._more)

    def __exit__(self, *exc):
        server = self._server
        assert server is not None, "__exit__ without __enter__"
        if server.is_alive():  # the engine never connected: release ConnectNamedPipe
            try:
                with open(self.path, "rb"):
                    pass
            except OSError:  # the server connected in the meantime; join() below covers it
                pass
        server.join(10)
        self._kernel32.CloseHandle(self._handle)
        return False
