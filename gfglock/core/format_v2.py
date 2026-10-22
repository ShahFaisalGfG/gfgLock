# format_v2.py - the v2 encrypted file layout and its keys, shared by the native and Python engines.
#
# Header (HEADER_SIZE bytes, written in the clear and used as the AAD of every chunk):
#   magic "GFGLOCK" | version u8 (2) | algorithm u8 | kdf u8 | memory_kib u32 | iterations u32 |
#   lanes u8 | chunk_log2 u8 | flags u8 (0) | kdf_salt(16) | file_salt(16) | nonce_prefix(7)
# Plaintext stream: name_len u16 | name (UTF-8) | mtime_ns i64 | file data
# The stream is sealed in chunks of 2**chunk_log2 plaintext bytes; chunk i is encrypted with the
# nonce  nonce_prefix | i as u32 | 1 for the final chunk else 0  and ends with a 16-byte tag.
# Integers are big-endian. The metadata always fits in the first chunk (chunks are >= 64 KiB).
#
# Keys: the run's master key is Argon2id(NFC(password), kdf_salt), derived once per run and
# shared by every file of that run; each file's key is HKDF-SHA256(master, file_salt, info).
# This module owns the layout; the engines (native/src/aes_cpu.cpp, py_cipher.py) only seal and
# open the chunk stream with the key, nonce prefix, and header they are given.

from __future__ import annotations

import struct
import threading
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from secrets import token_bytes

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"GFGLOCK"
VERSION = 2
ALGORITHM_IDS = {"gcm": 1, "chacha": 2}
ALGORITHM_NAMES = {code: name for name, code in ALGORITHM_IDS.items()}
KDF_ARGON2ID = 1

SALT_SIZE = 16
NONCE_PREFIX_SIZE = 7
TAG_SIZE = 16
KEY_SIZE = 32
MAX_NAME_BYTES = 1024
METADATA_OVERHEAD = 2 + 8  # name_len u16 + mtime_ns i64
DEFAULT_CHUNK_LOG2 = 20  # 1 MiB of plaintext per chunk
MIN_CHUNK_LOG2 = 16
MAX_CHUNK_LOG2 = 24
MAX_CHUNKS = 2**32  # the chunk counter is a u32

# The message both engines return when a cancel token stops them; file_ops reports it as a skip.
ENGINE_STOPPED = "stopped"

_HEADER = struct.Struct(">7sBBBIIBBB16s16s7s")
HEADER_SIZE = _HEADER.size
_METADATA_HEAD = struct.Struct(">H")
_MTIME = struct.Struct(">q")
_MTIME_MIN, _MTIME_MAX = -(2**63), 2**63 - 1
_FILE_KEY_INFO = b"gfgLock v2 file key"
# Argon2id memory that derivations may use at once, across every run: threads opening files from
# many runs (or a crafted header asking for 1 GiB) would otherwise each take their own share.
_KDF_MEMORY_BUDGET_KIB = 1024 * 1024


class FormatError(ValueError):
    """A v2 header or metadata block that is malformed or outside the accepted limits."""


@dataclass(frozen=True)
class KdfParams:
    """Argon2id cost settings, stored in every header so they can rise in later versions."""

    memory_kib: int = 256 * 1024
    iterations: int = 3
    lanes: int = 4

    def check(self) -> None:
        """Raise FormatError unless the costs are within what a header may ask for."""
        if not 1 <= self.lanes <= 16:
            raise FormatError("unsupported key derivation lanes")
        if not 1 <= self.iterations <= 10:
            raise FormatError("unsupported key derivation iterations")
        if not 8 * self.lanes <= self.memory_kib <= 1024 * 1024:
            raise FormatError("unsupported key derivation memory")


DEFAULT_KDF = KdfParams()


@dataclass(frozen=True)
class Header:
    """One file's v2 header. `pack()` gives the exact bytes written and authenticated."""

    algorithm: str
    kdf: KdfParams
    kdf_salt: bytes
    file_salt: bytes
    nonce_prefix: bytes
    chunk_log2: int = DEFAULT_CHUNK_LOG2

    @property
    def chunk_size(self) -> int:
        """Plaintext bytes per chunk."""
        return 1 << self.chunk_log2

    def pack(self) -> bytes:
        """The header bytes as stored at the start of the file."""
        return _HEADER.pack(MAGIC, VERSION, ALGORITHM_IDS[self.algorithm], KDF_ARGON2ID,
                            self.kdf.memory_kib, self.kdf.iterations, self.kdf.lanes,
                            self.chunk_log2, 0, self.kdf_salt, self.file_salt, self.nonce_prefix)


def has_magic(prefix: bytes) -> bool:
    """True when the bytes start with the magic of v2 and every later version.

    A v1 file starts with a random salt, which matches the magic with odds of 2**-56.
    """
    return prefix[:len(MAGIC)] == MAGIC


def parse_header(raw: bytes) -> Header:
    """Parse and validate a v2 header; raises FormatError for anything outside the limits."""
    if len(raw) < len(MAGIC) + 1:
        raise FormatError("the file is too small to be a valid encrypted file")
    if raw[:len(MAGIC)] == MAGIC and raw[len(MAGIC)] > VERSION:
        raise FormatError("the file was made by a newer gfgLock version")
    if len(raw) < HEADER_SIZE:
        raise FormatError("the file is too small to be a valid encrypted file")
    (magic, version, algorithm_id, kdf_id, memory_kib, iterations, lanes,
     chunk_log2, flags, kdf_salt, file_salt, nonce_prefix) = _HEADER.unpack(raw[:HEADER_SIZE])
    if magic != MAGIC or version != VERSION:
        raise FormatError("not a gfgLock v2 file")
    if algorithm_id not in ALGORITHM_NAMES:
        raise FormatError("the file uses an encryption method this version doesn't know")
    if kdf_id != KDF_ARGON2ID or flags != 0:
        raise FormatError("the file was made by a newer gfgLock version")
    if not MIN_CHUNK_LOG2 <= chunk_log2 <= MAX_CHUNK_LOG2:
        raise FormatError("unsupported chunk size")
    kdf = KdfParams(memory_kib, iterations, lanes)
    kdf.check()
    return Header(ALGORITHM_NAMES[algorithm_id], kdf, kdf_salt, file_salt, nonce_prefix, chunk_log2)


def chunk_nonce(nonce_prefix: bytes, index: int, last: bool) -> bytes:
    """The 12-byte nonce of chunk `index`."""
    return nonce_prefix + struct.pack(">IB", index, 1 if last else 0)


def pack_metadata(name: str, mtime_ns: int) -> bytes:
    """The metadata that starts the plaintext stream: the original name and modification time."""
    raw = name.encode("utf-8")
    if not raw or len(raw) > MAX_NAME_BYTES:
        raise FormatError("the file name is too long to store")
    # NTFS times before 1677 or after 2262 (a damaged timestamp, say) don't fit in an i64 of nanoseconds.
    return _METADATA_HEAD.pack(len(raw)) + raw + _MTIME.pack(min(max(mtime_ns, _MTIME_MIN), _MTIME_MAX))


def metadata_size(first_chunk: bytes) -> int:
    """Length of the metadata block at the start of the first chunk's plaintext."""
    if len(first_chunk) < _METADATA_HEAD.size:
        raise FormatError("the file is corrupted")
    (name_len,) = _METADATA_HEAD.unpack_from(first_chunk)
    if not 1 <= name_len <= MAX_NAME_BYTES or len(first_chunk) < METADATA_OVERHEAD + name_len:
        raise FormatError("the file is corrupted")
    return METADATA_OVERHEAD + name_len


def unpack_metadata(metadata: bytes) -> tuple[bytes, int]:
    """Split a metadata block into (raw name bytes, mtime_ns). The name is untrusted."""
    size = metadata_size(metadata)
    name_len = size - METADATA_OVERHEAD
    (mtime_ns,) = _MTIME.unpack_from(metadata, _METADATA_HEAD.size + name_len)
    return metadata[_METADATA_HEAD.size:_METADATA_HEAD.size + name_len], mtime_ns


def chunk_count(plaintext_size: int, chunk_log2: int = DEFAULT_CHUNK_LOG2) -> int:
    """Number of chunks a plaintext stream of this size is sealed in (always at least one)."""
    return max(1, -(-plaintext_size // (1 << chunk_log2)))


def encrypted_size(data_size: int, name: str, chunk_log2: int = DEFAULT_CHUNK_LOG2) -> int:
    """Exact size of the v2 file for data_size bytes of data stored under `name`."""
    plaintext = METADATA_OVERHEAD + len(name.encode("utf-8")) + data_size
    chunks = chunk_count(plaintext, chunk_log2)
    if chunks > MAX_CHUNKS:
        raise FormatError("the file is too large")
    return HEADER_SIZE + plaintext + chunks * TAG_SIZE


def password_bytes(password: str) -> bytes:
    """The password as Argon2id input: NFC-normalized UTF-8, so the same text always gives one key."""
    try:
        return unicodedata.normalize("NFC", password).encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("the password contains characters that can't be used") from error


class _MemoryBudget:
    """Lets derivations run together only while their memory fits the limit; a larger one runs alone."""

    def __init__(self, limit_kib: int) -> None:
        self._limit = limit_kib
        self._used = 0
        self._room = threading.Condition()

    @contextmanager
    def hold(self, kib: int) -> Iterator[None]:
        """Wait until kib fits beside the derivations already running, and count it while held."""
        with self._room:
            self._room.wait_for(lambda: self._used == 0 or self._used + kib <= self._limit)
            self._used += kib
        try:
            yield
        finally:
            with self._room:
                self._used -= kib
                self._room.notify_all()


_KDF_BUDGET = _MemoryBudget(_KDF_MEMORY_BUDGET_KIB)


class KeyRing:
    """One run's password and the keys derived from it, safe to share between worker threads.

    Encrypting derives one master key (with one KDF salt) for the whole run. Decrypting derives
    and caches a master key per KDF salt, so all files from one run cost a single Argon2id.
    """

    def __init__(self, password: str, kdf: KdfParams = DEFAULT_KDF) -> None:
        kdf.check()  # files written with costs outside the reader's limits could never be opened
        self._secret = password_bytes(password)
        self.password = password  # v1 files derive their own PBKDF2 key from the raw password
        self._kdf = kdf
        self._run_salt = token_bytes(SALT_SIZE)
        self._masters: dict[tuple[KdfParams, bytes], bytes] = {}
        self._pending: dict[tuple[KdfParams, bytes], threading.Lock] = {}
        self._lock = threading.Lock()

    def new_header(self, algorithm: str) -> tuple[Header, bytes]:
        """A header for one new file (this run's KDF salt, fresh file salt and nonce) and its key."""
        if algorithm not in ALGORITHM_IDS:
            raise ValueError(f"unknown algorithm {algorithm!r}")
        header = Header(algorithm, self._kdf, self._run_salt, token_bytes(SALT_SIZE), token_bytes(NONCE_PREFIX_SIZE))
        return header, self.file_key(header)

    def file_key(self, header: Header) -> bytes:
        """The key of the file this header belongs to."""
        info = _FILE_KEY_INFO + bytes([ALGORITHM_IDS[header.algorithm]])
        hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_SIZE, salt=header.file_salt, info=info)
        return hkdf.derive(self._master(header.kdf, header.kdf_salt))

    def _master(self, kdf: KdfParams, salt: bytes) -> bytes:
        """The Argon2id master key for these settings and salt, derived once and then reused."""
        slot = (kdf, salt)
        with self._lock:
            if slot in self._masters:
                return self._masters[slot]
            pending = self._pending.setdefault(slot, threading.Lock())
        with pending:  # threads opening files of one run wait for a single derivation
            with self._lock:
                if slot in self._masters:
                    return self._masters[slot]
            with _KDF_BUDGET.hold(kdf.memory_kib):
                master = Argon2id(salt=salt, length=KEY_SIZE, iterations=kdf.iterations, lanes=kdf.lanes,
                                  memory_cost=kdf.memory_kib).derive(self._secret)
            with self._lock:
                self._masters[slot] = master
                self._pending.pop(slot, None)
            return master
