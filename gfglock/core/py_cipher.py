# py_cipher.py - the pure-Python engine, used when the native C++ module is unavailable.
#
# Mirrors native/src/aes_cpu.cpp (same parameters, results, contract messages, and output bytes; I/O
# failures carry the system's own text, and other programs may still write a source it reads, which
# file_ops' identity check covers): it streams input_path into output_path and never deletes or
# renames anything. gfglock/core/file_ops.py
# owns naming, validation, and cleanup for both engines; gfglock/core/format_v2.py owns the v2 layout.
#
# v2 (seal_stream, open_stream): the caller's header, then metadata + file data sealed in chunks of
#   chunk_size plaintext bytes. Chunk i uses the nonce format_v2.chunk_nonce(prefix, i, last) and the
#   header as its AAD, and is followed by its 16-byte tag. A chunk's plaintext is written only after
#   its tag verifies.
# v1 (decrypt_stream_v1, decrypt only): salt(16) | nonce(12) or iv(16) | chunk_size u32 BE |
#   E(name + NUL + data) | tag(16, AEAD only), keyed with PBKDF2-SHA256(password, salt, 200000).

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from typing import BinaryIO, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

try:
    # cryptography moved CFB to its "decrepit" namespace and is removing the old location.
    from cryptography.hazmat.decrepit.ciphers.modes import CFB
except ImportError:  # releases from before the move
    from cryptography.hazmat.primitives.ciphers.modes import CFB
from gfglock.core import format_v2, native_bridge
from gfglock.core.format_v2 import ENGINE_STOPPED, FormatError

BUFFER_SIZE = 4 * 1024 * 1024  # read size when the caller passes 0 (the default)
MIN_READ_SIZE = 64 * 1024
MAX_READ_SIZE = 64 * 1024 * 1024
PROGRESS_UPDATE_INTERVAL = 100 * 1024 * 1024
TAG_SIZE = format_v2.TAG_SIZE
MIN_CHUNK_SIZE = 1 << format_v2.MIN_CHUNK_LOG2
MAX_CHUNK_SIZE = 1 << format_v2.MAX_CHUNK_LOG2
MAX_HEADER_SIZE = 4096

V1_SALT_SIZE = 16
V1_CHUNK_FIELD_SIZE = 4
V1_MAX_NAME_BYTES = 4096
_V1_IV_SIZES = {"gcm": 12, "cfb": 16, "chacha": 12}
_AEADS = {"gcm": AESGCM, "chacha": ChaCha20Poly1305}


def v1_overhead(algorithm: str) -> int:
    """Bytes a v1 file adds around its encrypted name and data: salt, IV, chunk field, and tag."""
    tag = 0 if algorithm == "cfb" else TAG_SIZE
    return V1_SALT_SIZE + _V1_IV_SIZES[algorithm] + V1_CHUNK_FIELD_SIZE + tag

# Error messages shared word for word with the native engine.
_AUTH_FAILED = "wrong password or the file was modified (authentication failed)"
_TRUNCATED = "the file is truncated or corrupted"
_CORRUPTED = "the file is corrupted"
_SIZE_CHANGED = "the source file changed size while it was being read"
_V1_BAD_NAME = "wrong password or the file is corrupted"

ProgressFn = Callable[[float], None] | None


class StopToken(Protocol):
    """A stop request both engines accept: this module's CancelToken or the native module's."""

    def cancel(self) -> None: ...

    @property
    def cancelled(self) -> bool: ...


class CancelToken:
    """A thread-safe stop request; every engine call holding it stops at its next block."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Ask the engine calls holding this token to stop."""
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """True once cancel() has been called."""
        return self._event.is_set()


class _Stopped(Exception):
    """The cancel token was set."""


class _StreamError(Exception):
    """A failure whose message is one of the engine messages above."""


class _Progress:
    """Counts bytes read from the input and reports them about every 100 MB and once at the end."""

    def __init__(self, callback: ProgressFn) -> None:
        self._callback = callback
        self._pending = 0
        self.total = 0

    def add(self, n: int) -> None:
        """Count n more bytes read."""
        self.total += n
        self._pending += n
        if self._pending >= PROGRESS_UPDATE_INTERVAL:
            self.flush()

    def flush(self) -> None:
        """Report what has not been reported yet."""
        if self._callback and self._pending > 0:
            self._callback(float(self._pending))
        self._pending = 0


def seal_stream(
    algorithm: str,
    input_path: str,
    output_path: str,
    header: bytes,
    key: bytes,
    nonce_prefix: bytes,
    chunk_size: int,
    metadata: bytes,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: ProgressFn = None,
) -> tuple[bool, str]:
    """Write header, then metadata + the input file sealed in chunks, to output_path. Returns (ok, error)."""
    progress = _Progress(callback)
    try:
        aead = _aead(algorithm, header, key, nonce_prefix, chunk_size)
        _check_metadata(metadata)
        _check_stop(cancel)
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            size = os.fstat(fin.fileno()).st_size
            chunks = -(-(len(metadata) + size) // chunk_size)
            if chunks > format_v2.MAX_CHUNKS:
                raise _StreamError("the file is too large")
            fout.write(header)
            index = 0
            for piece in _plain_chunks(fin, metadata, chunk_size, _block_size(block_size), cancel, progress):
                if index == chunks:
                    raise _StreamError(_SIZE_CHANGED)
                nonce = format_v2.chunk_nonce(nonce_prefix, index, index == chunks - 1)
                fout.write(aead.encrypt(nonce, piece, header))
                index += 1
        if index != chunks or progress.total != size:
            raise _StreamError(_SIZE_CHANGED)
        return True, ""
    except _Stopped:
        return False, ENGINE_STOPPED
    except OSError as error:
        return False, _os_message(error)
    except (_StreamError, ValueError) as error:
        return False, str(error)
    finally:
        progress.flush()


def open_stream(
    algorithm: str,
    input_path: str,
    output_path: str,
    header: bytes,
    key: bytes,
    nonce_prefix: bytes,
    chunk_size: int,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: ProgressFn = None,
) -> tuple[bool, str, bytes]:
    """Open the chunk stream after `header`: write the file data to output_path, return (ok, error, metadata)."""
    progress = _Progress(callback)
    try:
        aead = _aead(algorithm, header, key, nonce_prefix, chunk_size)
        _check_stop(cancel)
        stride = chunk_size + TAG_SIZE
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            body = os.fstat(fin.fileno()).st_size - len(header)
            if body <= 0:
                raise _StreamError(_TRUNCATED)
            # The header is every chunk's AAD, so a stored header that differs could never verify.
            if fin.read(len(header)) != header:
                raise _StreamError(_AUTH_FAILED)
            progress.add(len(header))
            chunks, tail = divmod(body, stride)
            if 0 < tail <= TAG_SIZE:
                raise _StreamError(_TRUNCATED)
            chunks += tail > 0
            if chunks > format_v2.MAX_CHUNKS:
                raise _StreamError(_CORRUPTED)
            metadata = b""
            sealed_chunks = _sealed_chunks(fin, body, stride, _block_size(block_size), cancel, progress)
            for index, sealed in enumerate(sealed_chunks):
                plain = aead.decrypt(format_v2.chunk_nonce(nonce_prefix, index, index == chunks - 1), sealed, header)
                if index == 0:
                    size = format_v2.metadata_size(plain)
                    metadata = plain[:size]
                    fout.write(memoryview(plain)[size:])
                else:
                    fout.write(plain)
        return True, "", metadata
    except InvalidTag:
        return False, _AUTH_FAILED, b""
    except FormatError:
        return False, _CORRUPTED, b""
    except _Stopped:
        return False, ENGINE_STOPPED, b""
    except OSError as error:
        return False, _os_message(error), b""
    except (_StreamError, ValueError) as error:
        return False, str(error), b""
    finally:
        progress.flush()


def decrypt_stream_v1(
    algorithm: str,
    input_path: str,
    output_path: str,
    password: str,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: ProgressFn = None,
) -> tuple[bool, str, bytes]:
    """Decrypt a v1 file into output_path. Returns (ok, error, stored_name_bytes); the name is untrusted."""
    progress = _Progress(callback)
    try:
        if algorithm not in _V1_IV_SIZES:
            raise ValueError(f"unknown algorithm {algorithm!r}")
        _check_stop(cancel)
        iv_size = _V1_IV_SIZES[algorithm]
        header_size = V1_SALT_SIZE + iv_size + V1_CHUNK_FIELD_SIZE
        tag_size = 0 if algorithm == "cfb" else TAG_SIZE
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            total = os.fstat(fin.fileno()).st_size
            if total < header_size + tag_size + 1:
                raise _StreamError("the file is too small to be a valid encrypted file")
            head = fin.read(header_size)  # the chunk field after salt and iv is informational only
            progress.add(len(head))
            key = native_bridge.derive_key(password, head[:V1_SALT_SIZE])
            update, finish = _v1_decryptor(algorithm, key, head[V1_SALT_SIZE:V1_SALT_SIZE + iv_size])
            output = _NameSplitter(fout)
            remaining = total - header_size - tag_size
            step = _block_size(block_size)
            while remaining > 0:
                _check_stop(cancel)
                data = fin.read(min(remaining, step))
                if not data:
                    raise _StreamError(_TRUNCATED)
                remaining -= len(data)
                progress.add(len(data))
                output.write(update(data))
            tag = fin.read(tag_size)
            progress.add(len(tag))
            try:
                output.write(finish(tag))
            except (InvalidTag, ValueError):  # cryptography / pycryptodome tag mismatch
                raise _StreamError(_AUTH_FAILED) from None
            if not output.found:
                raise _StreamError(_V1_BAD_NAME)
        return True, "", bytes(output.name)
    except _Stopped:
        return False, ENGINE_STOPPED, b""
    except OSError as error:
        return False, _os_message(error), b""
    except (_StreamError, ValueError) as error:
        return False, str(error), b""
    finally:
        progress.flush()


class _NameSplitter:
    """Writes v1 plaintext to the output once the stored name and its NUL have been taken off."""

    def __init__(self, out: BinaryIO) -> None:
        self._out = out
        self.name = bytearray()
        self.found = False

    def write(self, plain: bytes) -> None:
        """Pass the next piece of plaintext on, keeping back the name at the start."""
        if self.found:
            self._out.write(plain)
            return
        head, sep, rest = plain.partition(b"\0")
        self.name.extend(head)
        if len(self.name) > V1_MAX_NAME_BYTES:
            raise _StreamError(_V1_BAD_NAME)
        if sep:
            self.found = True
            self._out.write(rest)


def _v1_decryptor(algorithm: str, key: bytes, iv: bytes) -> tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]:
    """(update, finish) for one v1 file; finish checks an AEAD tag and raises on a mismatch."""
    if algorithm == "chacha":
        # Only v1 ChaCha files need pycryptodome (cryptography's ChaCha20Poly1305 can't stream), and
        # importing it costs about 40 ms of start-up, so it loads on first use.
        from Crypto.Cipher import ChaCha20_Poly1305

        chacha = ChaCha20_Poly1305.new(key=key, nonce=iv)

        def verify(tag: bytes) -> bytes:
            chacha.verify(tag)
            return b""

        return chacha.decrypt, verify
    if algorithm == "gcm":
        gcm = Cipher(algorithms.AES(key), modes.GCM(iv)).decryptor()
        return gcm.update, gcm.finalize_with_tag
    cfb = Cipher(algorithms.AES(key), CFB(iv)).decryptor()
    return cfb.update, lambda _tag: cfb.finalize()


def _plain_chunks(fin: BinaryIO, metadata: bytes, chunk_size: int, block: int,
                  cancel: StopToken | None, progress: _Progress) -> Iterator[bytes | memoryview]:
    """The plaintext stream (metadata, then the file) in chunk_size pieces; the last may be shorter."""
    _check_stop(cancel)
    head = fin.read(chunk_size - len(metadata))
    progress.add(len(head))
    yield metadata + head
    # After the first chunk the file data is chunk-aligned, so whole blocks slice without copying.
    step = max(1, block // chunk_size) * chunk_size
    while True:
        _check_stop(cancel)
        data = fin.read(step)
        if not data:
            return
        progress.add(len(data))
        view = memoryview(data)
        for start in range(0, len(view), chunk_size):
            yield view[start:start + chunk_size]


def _sealed_chunks(fin: BinaryIO, body: int, stride: int, block: int,
                   cancel: StopToken | None, progress: _Progress) -> Iterator[memoryview]:
    """The body's sealed chunks (stride bytes each, the last may be shorter), read whole chunks at a time."""
    step = max(1, block // (stride - TAG_SIZE)) * stride
    remaining = body
    while remaining > 0:
        _check_stop(cancel)
        want = min(step, remaining)
        data = fin.read(want)
        if len(data) != want:
            raise _StreamError(_TRUNCATED)
        remaining -= want
        progress.add(want)
        view = memoryview(data)
        for start in range(0, want, stride):
            yield view[start:start + stride]


def _aead(algorithm: str, header: bytes, key: bytes, nonce_prefix: bytes,
          chunk_size: int) -> AESGCM | ChaCha20Poly1305:
    """The AEAD of a v2 stream, after the parameter checks (and messages) of the native engine."""
    if algorithm == "cfb":
        raise ValueError("CFB only decrypts v1 files; v2 files use gcm or chacha")
    if algorithm not in _AEADS:
        raise ValueError(f"unknown algorithm {algorithm!r}")
    if not 0 < len(header) <= MAX_HEADER_SIZE:
        raise ValueError("header must be 1 to 4096 bytes")
    if len(key) != format_v2.KEY_SIZE:
        raise ValueError("key must be 32 bytes")
    if len(nonce_prefix) != format_v2.NONCE_PREFIX_SIZE:
        raise ValueError("nonce_prefix must be 7 bytes")
    if chunk_size & (chunk_size - 1) or not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("chunk_size must be a power of two from 65536 to 16777216")
    return _AEADS[algorithm](key)


def _check_metadata(metadata: bytes) -> None:
    """Raise ValueError unless metadata is exactly one v2 metadata block."""
    try:
        valid = format_v2.metadata_size(metadata) == len(metadata)
    except FormatError:
        valid = False
    if not valid:
        raise ValueError("metadata must be one v2 metadata block (name length, name, mtime)")


def _block_size(read_size: int) -> int:
    """The read size to use: the default for 0, otherwise clamped like the native engine."""
    if not read_size or read_size <= 0:
        return BUFFER_SIZE
    return max(MIN_READ_SIZE, min(int(read_size), MAX_READ_SIZE))


def _check_stop(cancel: StopToken | None) -> None:
    """Raise _Stopped once the token is set."""
    if cancel is not None and cancel.cancelled:
        raise _Stopped


def _os_message(error: OSError) -> str:
    """The system's description of an I/O error, without the errno prefix and path."""
    return error.strerror or str(error)
