# py_cipher.py - pure-Python file transforms, used when the native C++ module is unavailable.
#
# Mirrors native/src/aes_cpu.cpp exactly (same file layout, same contract): stream input_path
# into output_path, never delete or rename anything, and return the stored file name as raw,
# untrusted bytes. gfglock/core/file_ops.py owns naming, validation, and cleanup for both.
#
# Layout: salt(16) | nonce(12) or iv(16) | chunk_size u32 BE | E(name + NUL + data) | tag(16, AEAD)

from __future__ import annotations

import os
import struct
from collections.abc import Callable
from secrets import token_bytes

from Crypto.Cipher import ChaCha20_Poly1305  # type: ignore[import]
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:
    # cryptography moved CFB to its "decrepit" namespace and is removing the old location.
    from cryptography.hazmat.decrepit.ciphers.modes import CFB
except ImportError:  # releases from before the move
    from cryptography.hazmat.primitives.ciphers.modes import CFB
from gfglock.utils.helpers import derive_key

SALT_SIZE = 16
NONCE_SIZE = 12
IV_SIZE = 16
TAG_SIZE = 16
CHUNK_FIELD_SIZE = 4
BUFFER_SIZE = 1024 * 1024
SMALL_FILE_THRESHOLD = 10 * 1024 * 1024
PROGRESS_UPDATE_INTERVAL = 100 * 1024 * 1024
MAX_NAME_BYTES = 4096

_IV_SIZES = {"gcm": NONCE_SIZE, "cfb": IV_SIZE, "chacha": NONCE_SIZE}
_AEAD = {"gcm": True, "cfb": False, "chacha": True}

ProgressFn = Callable[[float], None] | None


class _StreamCipher:
    """One streaming interface over cryptography (AES) and pycryptodome (ChaCha20-Poly1305)."""

    def __init__(self, algorithm: str, key: bytes, iv: bytes, encrypt: bool) -> None:
        self._algorithm = algorithm
        if algorithm == "chacha":
            self._chacha = ChaCha20_Poly1305.new(key=key, nonce=iv)
            self._encrypt = encrypt
            return
        mode = modes.GCM(iv) if algorithm == "gcm" else CFB(iv)
        cipher = Cipher(algorithms.AES(key), mode)
        self._ctx = cipher.encryptor() if encrypt else cipher.decryptor()

    def update(self, data: bytes) -> bytes:
        """Encrypt or decrypt the next piece of the stream."""
        if self._algorithm == "chacha":
            return self._chacha.encrypt(data) if self._encrypt else self._chacha.decrypt(data)
        return self._ctx.update(data)

    def finish_encrypt(self) -> bytes:
        """Finish encryption and return the trailing bytes (final block + tag for AEAD)."""
        if self._algorithm == "chacha":
            return self._chacha.digest()
        tail = self._ctx.finalize()
        return tail + self._ctx.tag if self._algorithm == "gcm" else tail  # type: ignore[attr-defined]

    def finish_decrypt(self, tag: bytes | None) -> bytes:
        """Finish decryption, verifying the tag for AEAD ciphers (raises on mismatch)."""
        if self._algorithm != "cfb" and tag is None:
            raise ValueError("missing authentication tag")
        if self._algorithm == "chacha":
            self._chacha.verify(tag)  # type: ignore[arg-type]  # checked non-None above
            return b""
        if self._algorithm == "gcm":
            return self._ctx.finalize_with_tag(tag)  # type: ignore[attr-defined]
        return self._ctx.finalize()


def encrypt_stream(
    algorithm: str,
    input_path: str,
    output_path: str,
    original_name: str,
    password: str,
    chunk_size: int = 0,
    progress: ProgressFn = None,
) -> tuple[bool, str]:
    """Encrypt input_path into output_path. Returns (ok, error)."""
    try:
        file_size = os.path.getsize(input_path)
        if file_size < SMALL_FILE_THRESHOLD or chunk_size < 0:
            chunk_size = 0
        salt = token_bytes(SALT_SIZE)
        iv = token_bytes(_IV_SIZES[algorithm])
        cipher = _StreamCipher(algorithm, derive_key(password, salt), iv, encrypt=True)
        name_meta = original_name.encode("utf-8") + b"\0"
        total_read = 0
        batch = 0.0
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            fout.write(salt + iv + struct.pack(">I", chunk_size))
            fout.write(cipher.update(name_meta))
            _report(progress, len(name_meta))
            while data := fin.read(BUFFER_SIZE):
                total_read += len(data)
                fout.write(cipher.update(data))
                batch = _batched(progress, batch, len(data))
            _report(progress, batch)
            if total_read != file_size:
                return False, "the source file changed size while it was being read"
            fout.write(cipher.finish_encrypt())
        return True, ""
    except (OSError, ValueError) as error:
        return False, str(error)


def decrypt_stream(
    algorithm: str,
    input_path: str,
    output_path: str,
    password: str,
    progress: ProgressFn = None,
) -> tuple[bool, str, bytes]:
    """Decrypt input_path into output_path. Returns (ok, error, stored_name_bytes)."""
    try:
        total_size = os.path.getsize(input_path)
        header_size = SALT_SIZE + _IV_SIZES[algorithm] + CHUNK_FIELD_SIZE
        tag_size = TAG_SIZE if _AEAD[algorithm] else 0
        if total_size < header_size + tag_size + 1:
            return False, "the file is too small to be a valid encrypted file", b""
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            salt = fin.read(SALT_SIZE)
            iv = fin.read(_IV_SIZES[algorithm])
            fin.read(CHUNK_FIELD_SIZE)  # informational only
            cipher = _StreamCipher(algorithm, derive_key(password, salt), iv, encrypt=False)
            name = bytearray()
            got_name = False

            def consume(plain: bytes) -> None:
                nonlocal got_name
                if got_name:
                    fout.write(plain)
                    return
                head, sep, rest = plain.partition(b"\0")
                name.extend(head)
                if len(name) > MAX_NAME_BYTES:
                    raise ValueError("wrong password or the file is corrupted")
                if sep:
                    got_name = True
                    fout.write(rest)

            remaining = total_size - header_size - tag_size
            batch = 0.0
            while remaining > 0:
                data = fin.read(min(remaining, BUFFER_SIZE))
                if not data:
                    return False, "the file is truncated or corrupted", b""
                remaining -= len(data)
                consume(cipher.update(data))
                batch = _batched(progress, batch, len(data))
            _report(progress, batch)
            tag = fin.read(tag_size) if tag_size else None
            try:
                consume(cipher.finish_decrypt(tag))
            except (InvalidTag, ValueError):  # cryptography / pycryptodome tag mismatch
                return False, "wrong password or the file was modified (authentication failed)", b""
            if not got_name:
                return False, "wrong password or the file is corrupted", b""
        return True, "", bytes(name)
    except (OSError, ValueError) as error:
        return False, str(error), b""


def _batched(progress: ProgressFn, batch: float, n: int) -> float:
    """Accumulate progress and report it every PROGRESS_UPDATE_INTERVAL bytes."""
    batch += n
    if batch >= PROGRESS_UPDATE_INTERVAL:
        _report(progress, batch)
        return 0.0
    return batch


def _report(progress: ProgressFn, n: float) -> None:
    """Send a progress amount when there is something to report."""
    if progress and n > 0:
        progress(float(n))
