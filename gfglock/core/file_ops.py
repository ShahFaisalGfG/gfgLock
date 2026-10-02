# file_ops.py - safe file-level encryption and decryption, shared by the native and Python ciphers.
#
# The cipher backends (native C++ or pure Python) only turn one file into another. Everything that
# decides which files exist afterwards lives here, in one place:
#   * output goes to a fresh hidden temp file in the same folder, created exclusively;
#   * the result is size-checked and flushed to disk before anything else happens;
#   * it is then renamed to a name that does not exist yet (never overwriting a file);
#   * only after that is the source deleted.
# The file name stored inside an encrypted file is untrusted (AES-CFB is malleable, and files can
# come from anyone), so it is validated as a single plain Windows file name before use.

from __future__ import annotations

import os
from collections.abc import Callable
from secrets import token_hex

from gfglock.core import native_bridge, py_cipher
from gfglock.utils.helpers import generate_encrypted_name, predict_encrypted_size, safe_print

# Algorithm code -> encrypted file extension.
EXTENSIONS = {"gcm": ".gfglock", "cfb": ".gfglck", "chacha": ".gfgcha"}
ALGORITHM_FOR_EXT = {ext: algo for algo, ext in EXTENSIONS.items()}
ENCRYPTED_EXTS = frozenset(EXTENSIONS.values())
_SIZE_MODE = {"gcm": "GCM", "cfb": "CFB", "chacha": "CHACHA"}

TEMP_SUFFIX = ".gfgpart"
_MAX_NAME_LENGTH = 255
_MAX_UNIQUE_ATTEMPTS = 10_000
_INVALID_NAME_CHARS = frozenset('<>:"/\\|?*')
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(10)]
    + [f"LPT{i}" for i in range(10)]
)

ProgressFn = Callable[[float], None] | None


class _OperationError(Exception):
    """A failure with a message meant for the user."""


def is_encrypted_path(path: str) -> bool:
    """True when the path has one of gfgLock's encrypted extensions (any letter case)."""
    return os.path.splitext(path)[1].lower() in ENCRYPTED_EXTS


def encrypt_file(
    path: str,
    password: str,
    algorithm: str,
    encrypt_name: bool = False,
    chunk_size: int | None = None,
    progress: ProgressFn = None,
) -> tuple[bool, str]:
    """Encrypt one file next to itself and delete the original once the result is safely on disk.

    The encrypted file keeps the full original name (report.docx -> report.docx.gfglock) so files
    that differ only by extension can't collide, and gets " (2)" etc. if the name is taken.
    """
    if algorithm not in EXTENSIONS:
        return False, f"Critical error while encrypting {path}: unknown algorithm {algorithm!r}"
    if not os.path.isfile(path):
        return False, f"Critical error: {path} not found"
    if is_encrypted_path(path):
        return False, f"{path} is already encrypted"

    folder = os.path.dirname(os.path.abspath(path))
    temp = None
    try:
        temp = _create_temp(folder)
        ok, error = _backend_encrypt(algorithm, path, temp, os.path.basename(path), password, chunk_size, progress)
        if not ok:
            raise _OperationError(error or "encryption failed")
        expected = predict_encrypted_size(path, _SIZE_MODE[algorithm])
        if os.path.getsize(temp) != expected:
            raise _OperationError("the encrypted file is incomplete (disk full?)")
        _flush_to_disk(temp)
        final = _move_to_unique_name(temp, folder, generate_encrypted_name(path, encrypt_name, EXTENSIONS[algorithm]))
        temp = None
        os.remove(path)
        return _report(True, f"Encrypted: {path} -> {final}")
    except (_OperationError, OSError) as error:
        _discard(temp)
        return _report(False, f"Critical error while encrypting {path}: {_describe(error)}")


def decrypt_file(path: str, password: str, progress: ProgressFn = None) -> tuple[bool, str]:
    """Decrypt one file next to itself under its original name, then delete the encrypted file.

    An existing file with the original name is never overwritten; the restored copy gets a
    " (2)" style suffix instead.
    """
    algorithm = ALGORITHM_FOR_EXT.get(os.path.splitext(path)[1].lower())
    if algorithm is None:
        return False, f"{path} is already decrypted"
    if not os.path.isfile(path):
        return False, f"Critical error: {path} not found"

    folder = os.path.dirname(os.path.abspath(path))
    temp = None
    try:
        temp = _create_temp(folder)
        ok, error, raw_name = _backend_decrypt(algorithm, path, temp, password, progress)
        if not ok:
            raise _OperationError(error or "decryption failed")
        name = safe_original_name(raw_name)
        if name is None:
            # CFB has no authentication, so an unreadable name almost always means a wrong
            # password; the decrypted bytes are garbage and must not replace the encrypted file.
            raise _OperationError("wrong password or the file is corrupted")
        _flush_to_disk(temp)
        final = _move_to_unique_name(temp, folder, name)
        temp = None
        os.remove(path)
        return _report(True, f"Decrypted: {path} -> {final}")
    except (_OperationError, OSError) as error:
        _discard(temp)
        return _report(False, f"Critical error while decrypting {path}: {_describe(error)}")


def safe_original_name(raw: bytes) -> str | None:
    """Return the stored file name if it is a single, ordinary Windows file name, else None.

    Rejects anything that could escape the folder or reach something other than a plain file:
    path separators, drive letters and NTFS streams (':'), device names such as NUL or COM1,
    '.'/'..', control characters, trailing dots or spaces, and invalid UTF-8.
    """
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not name or len(name) > _MAX_NAME_LENGTH or name in (".", ".."):
        return None
    if any(ch in _INVALID_NAME_CHARS or ord(ch) < 32 for ch in name):
        return None
    if name[-1] in " .":
        return None
    if name.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES:
        return None
    return name


def unique_path(folder: str, name: str) -> str:
    """Return folder/name, or folder/'stem (2).ext' and so on when that name is taken."""
    candidate = os.path.join(folder, name)
    if not os.path.lexists(candidate):
        return candidate
    stem, ext = os.path.splitext(name)
    for n in range(2, _MAX_UNIQUE_ATTEMPTS):
        candidate = os.path.join(folder, f"{stem} ({n}){ext}")
        if not os.path.lexists(candidate):
            return candidate
    raise _OperationError(f"no free file name for {name}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _backend_encrypt(algorithm, src, dst, name, password, chunk_size, progress) -> tuple[bool, str]:
    """Run the native cipher when available, else the pure-Python one."""
    cs = int(chunk_size or 0)
    if native_bridge.NATIVE_AVAILABLE:
        return native_bridge.encrypt_file(algorithm, src, dst, name, password, cs, progress)
    return py_cipher.encrypt_stream(algorithm, src, dst, name, password, cs, progress)


def _backend_decrypt(algorithm, src, dst, password, progress) -> tuple[bool, str, bytes]:
    """Run the native cipher when available, else the pure-Python one."""
    if native_bridge.NATIVE_AVAILABLE:
        return native_bridge.decrypt_file(algorithm, src, dst, password, progress)
    return py_cipher.decrypt_stream(algorithm, src, dst, password, progress)


def _create_temp(folder: str) -> str:
    """Create an empty, exclusively owned temp file in folder and return its path."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    for _ in range(100):
        path = os.path.join(folder, f".{token_hex(8)}{TEMP_SUFFIX}")
        try:
            os.close(os.open(path, flags))
            return path
        except FileExistsError:
            continue
    raise _OperationError("could not create a temporary file")


def _flush_to_disk(path: str) -> None:
    """Force the file's data out of the OS cache so a power cut can't lose it after the source is gone."""
    with open(path, "rb+") as fh:
        os.fsync(fh.fileno())


def _move_to_unique_name(temp: str, folder: str, name: str) -> str:
    """Rename temp to a free name in folder, retrying if another file claims the name first."""
    for _ in range(_MAX_UNIQUE_ATTEMPTS):
        target = unique_path(folder, name)
        try:
            os.rename(temp, target)  # never replaces an existing file on Windows
            return target
        except FileExistsError:
            continue
    raise _OperationError(f"no free file name for {name}")


def _discard(path: str | None) -> None:
    """Delete a temp file that will not be used, ignoring a missing file."""
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as error:
        safe_print(f"Could not remove temporary file {path}: {error}")


def _describe(error: Exception) -> str:
    """User-facing text for an error."""
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)


def _report(ok: bool, message: str) -> tuple[bool, str]:
    """Echo the result to the console log and return it."""
    safe_print(message)
    return ok, message
