# file_ops.py - safe file-level encryption and decryption, shared by the native and Python engines.
#
# The engines (native C++ or pure Python) only turn one file into another. Everything that decides
# which files exist afterwards lives here, in one place:
#   * new files use the v2 format (format_v2.py); v1 files from 3.1 and older still decrypt, and a
#     file that starts with the v2 magic is read as v2 whatever its extension;
#   * output goes to a fresh temp file (".<16 hex>.gfgpart") in the same folder, created exclusively;
#   * the result is checked (its exact size after encrypting, the stored name after decrypting) and
#     flushed to disk before anything else happens; decrypting also restores the stored modification
#     time and copies the Mark of the Web (the Zone.Identifier stream) from the encrypted file;
#   * it is then renamed to a name that does not exist yet (never overwriting a file);
#   * the source is deleted only while it is still the file that was read (same file id, volume,
#     size, and modification time), so a file replaced or edited meanwhile is never lost. If the
#     source can't be deleted (read-only, or open in another program), the new copy is removed
#     again, so a file never ends up in both forms;
#   * a stop token ends a file early: its temp file is removed and the source is untouched.
# Links, hard-linked files, and leftover temp files are skipped: encrypting them would leave the data
# readable through the link or the file's other names.
# The file name stored inside an encrypted file is untrusted (files can come from anyone), so it is
# validated as a single plain Windows file name before use. Legacy AES-CFB files have no
# authentication, so a wrong password can still yield a valid-looking name: such a file is deleted
# only when the restored name matches its own name, and kept otherwise.

from __future__ import annotations

import os
import re
import time
import unicodedata
from collections.abc import Iterable
from secrets import token_hex

from gfglock.core import format_v2, native_bridge, py_cipher
from gfglock.core.format_v2 import ENGINE_STOPPED, FormatError, KeyRing
from gfglock.core.py_cipher import ProgressFn, StopToken
from gfglock.utils.console import safe_print
from gfglock.utils.helpers import generate_encrypted_name

# Algorithm code -> encrypted file extension. CFB files can only be decrypted.
EXTENSIONS = {"gcm": ".gfglock", "chacha": ".gfgcha", "cfb": ".gfglck"}
ENCRYPT_ALGORITHMS = ("gcm", "chacha")
ALGORITHM_FOR_EXT = {ext: algo for algo, ext in EXTENSIONS.items()}
ENCRYPTED_EXTS = frozenset(EXTENSIONS.values())

TEMP_SUFFIX = ".gfgpart"
_TEMP_NAME = re.compile(r"\.[0-9a-f]{16}\.gfgpart", re.IGNORECASE)
_ZONE_STREAM = ":Zone.Identifier"
_MAX_NAME_LENGTH = 255  # UTF-16 code units in one NTFS name
_MAX_UNIQUE_ATTEMPTS = 10_000
_INVALID_NAME_CHARS = frozenset('<>:"/\\|?*')
# Zero-width non-joiner and joiner are format characters that Persian, Urdu and Hindi names and
# emoji sequences need; every other format character (bidi overrides such as U+202E) is refused.
_ALLOWED_FORMAT_CHARS = frozenset("‌‍")
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"]
    + [f"{port}{digit}" for port in ("COM", "LPT") for digit in "0123456789¹²³"]
)

_NOT_FOUND = "File not found; it may have been moved or deleted"
# The reason of a file a stop token ended: it stays as it was, so a later run should process it.
STOPPED_REASON = "Stopped before it finished; the file was not changed"
_HARD_LINKED = "Other hard links to this file would stay readable"
_CFB_KEPT = ("The encrypted file was kept because the old CFB format can't confirm the password; "
             "delete it once the decrypted file opens")
_CHANGED = ("the file changed while gfgLock was reading it, so nothing was changed. "
            "Try again once no other program is using it")
_UNSAFE_NAME = "the name stored in the file isn't a safe Windows file name"


class _OperationError(Exception):
    """A failure with a message meant for the user."""


class _Stopped(Exception):
    """The run's stop token ended the file before it finished."""


class FileResult(tuple):
    """What happened to one file. Unpacks as (ok, message) for callers that only need that.

    `outcome` is "done", "skipped", or "failed"; `reason` says why in a few words for the file
    list (a "done" row can carry one too), and `output` is the file that was written ("" unless done).
    """

    outcome: str
    reason: str
    output: str

    def __new__(cls, ok: bool, message: str, outcome: str, reason: str = "", output: str = "") -> "FileResult":
        result = super().__new__(cls, (ok, message))
        result.outcome = outcome
        result.reason = reason
        result.output = output
        return result


def is_encrypted_path(path: str) -> bool:
    """True when the path has one of gfgLock's encrypted extensions (any letter case)."""
    return os.path.splitext(path)[1].lower() in ENCRYPTED_EXTS


def new_stop_token() -> StopToken:
    """A stop token for one run: cancel() ends the files in progress and leaves their sources as they were."""
    return native_bridge.new_cancel_token() if native_bridge.NATIVE_AVAILABLE else py_cipher.CancelToken()


def encrypt_file(
    path: str,
    keys: KeyRing,
    algorithm: str,
    encrypt_name: bool = False,
    read_size: int = 0,
    progress: ProgressFn = None,
    stop: StopToken | None = None,
) -> FileResult:
    """Encrypt one file next to itself and delete the original once the result is safely on disk.

    The encrypted file keeps the full original name (report.docx -> report.docx.gfglock) so files that
    differ only by extension can't collide, and gets " (2)" etc. if the name is taken.
    """
    if algorithm not in ENCRYPT_ALGORITHMS:
        return FileResult(False, f"Critical error while encrypting {path}: unknown algorithm {algorithm!r}",
                          "failed", f"Unknown encryption method {algorithm!r}")
    skipped = _skip_reason(path)
    if skipped:
        return skipped
    if is_encrypted_path(path):
        return FileResult(False, f"{path} is already encrypted", "skipped", "Already encrypted")

    folder = os.path.dirname(os.path.abspath(path))
    name = os.path.basename(path)
    temp = None
    try:
        source = os.stat(path, follow_symlinks=False)
        if source.st_nlink > 1:
            return FileResult(False, f"{path} has other hard links", "skipped", _HARD_LINKED)
        target = generate_encrypted_name(path, encrypt_name, EXTENSIONS[algorithm])
        _check_names(name, target, encrypt_name)
        _check_removable(path)
        header, key = keys.new_header(algorithm)
        metadata = format_v2.pack_metadata(name, source.st_mtime_ns)
        expected = format_v2.encrypted_size(source.st_size, name, header.chunk_log2)
        temp = _create_temp(folder)
        _seal(path, temp, header, key, metadata, read_size, progress, stop)
        if os.path.getsize(temp) != expected:
            if os.path.getsize(path) != source.st_size:
                raise _OperationError(_CHANGED)
            raise _OperationError("the encrypted file is incomplete (disk full?)")
        _flush_to_disk(temp)
        _copy_zone_mark(path, temp)  # so the restored file is marked as downloaded again
        final = _move_to_unique_name(temp, folder, target)
        temp = None
        _confirm_unchanged(path, source, final)
        _remove_source(path, final)
        return _report(FileResult(True, f"Encrypted: {path} -> {final}", "done", output=final))
    except _Stopped:
        return FileResult(False, f"Stopped: {path} was not changed", "skipped", STOPPED_REASON)
    except (_OperationError, FormatError, OSError) as error:
        reason = _describe(error)
        return _report(FileResult(False, f"Critical error while encrypting {path}: {reason}", "failed", _sentence(reason)))
    finally:
        _discard(temp)  # set to None once the output is in place


def decrypt_file(
    path: str,
    keys: KeyRing,
    read_size: int = 0,
    progress: ProgressFn = None,
    stop: StopToken | None = None,
) -> FileResult:
    """Decrypt one file next to itself under its original name, then delete the encrypted file.

    An existing file with the original name is never overwritten; the restored copy gets a
    " (2)" style suffix instead.
    """
    skipped = _skip_reason(path)
    if skipped:
        return skipped

    folder = os.path.dirname(os.path.abspath(path))
    temp = None
    try:
        source = os.stat(path, follow_symlinks=False)
        with open(path, "rb") as fh:
            prefix = fh.read(format_v2.HEADER_SIZE)
        legacy = None
        if not format_v2.has_magic(prefix):
            legacy = ALGORITHM_FOR_EXT.get(os.path.splitext(path)[1].lower())
            if legacy is None:
                return FileResult(False, f"{path} is already decrypted", "skipped", "Not an encrypted gfgLock file")
        _check_removable(path)
        temp = _create_temp(folder)
        mtime_ns = None
        if legacy is None:
            name, mtime_ns, expected = _open_v2(prefix, path, temp, keys, source.st_size, read_size, progress, stop)
        else:
            name, expected = _open_v1(legacy, path, temp, keys.password, source.st_size, read_size, progress, stop)
        if os.path.getsize(temp) != expected:  # an engine fault must never cost the encrypted file
            raise _OperationError("the decrypted file is incomplete (disk full?)")
        _flush_to_disk(temp)
        _copy_zone_mark(path, temp)  # before the time: writing a stream updates the modification time
        if mtime_ns is not None:
            _restore_mtime(temp, mtime_ns)
        final = _move_to_unique_name(temp, folder, name)
        temp = None
        if legacy == "cfb" and not _is_own_name(path, name):
            message = f"Decrypted: {path} -> {final}; the encrypted file was kept (CFB can't confirm the password)"
            return _report(FileResult(True, message, "done", _CFB_KEPT, final))
        _confirm_unchanged(path, source, final)
        _remove_source(path, final)
        return _report(FileResult(True, f"Decrypted: {path} -> {final}", "done", output=final))
    except _Stopped:
        return FileResult(False, f"Stopped: {path} was not changed", "skipped", STOPPED_REASON)
    except (_OperationError, FormatError, OSError) as error:
        reason = _describe(error)
        return _report(FileResult(False, f"Critical error while decrypting {path}: {reason}", "failed", _sentence(reason)))
    finally:
        _discard(temp)  # set to None once the output is in place


def remove_stale_temps(folders: Iterable[str]) -> int:
    """Delete the ".<16 hex>.gfgpart" files an interrupted run left in these folders; return how many.

    A temp file that another program still has open can't be deleted and is left alone.
    """
    removed = 0
    for folder in dict.fromkeys(folders):
        try:
            with os.scandir(folder) as scan:
                stale = [entry.path for entry in scan
                         if _TEMP_NAME.fullmatch(entry.name) and entry.is_file(follow_symlinks=False)]
        except OSError as error:
            safe_print(f"Could not look for leftover temporary files in {folder}: {error}")
            continue
        for path in stale:
            try:
                os.remove(path)
                removed += 1
            except OSError as error:  # still open in another program, or already gone
                safe_print(f"Left temporary file {path} in place: {error}")
    return removed


def safe_original_name(raw: bytes) -> str | None:
    """Return the stored file name if it is a single, ordinary Windows file name, else None.

    Rejects anything that could escape the folder, reach something other than a plain file, or
    disguise the name: path separators, drive letters and NTFS streams (':'), device names such as
    NUL, COM1, COM¹ or CONIN$, '.'/'..', control and invisible format characters (such as U+202E),
    trailing dots or spaces, names over 255 UTF-16 units, and invalid UTF-8.
    """
    try:
        name = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not name or _utf16_length(name) > _MAX_NAME_LENGTH or name in (".", ".."):
        return None
    if any(ch in _INVALID_NAME_CHARS or ord(ch) < 32 or _is_hidden_format(ch) for ch in name):
        return None
    if name[-1] in " .":
        return None
    if name.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES:
        return None
    if name.lower().endswith(TEMP_SUFFIX):  # remove_stale_temps would delete it on the next run
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

def _seal(path: str, temp: str, header: format_v2.Header, key: bytes, metadata: bytes,
          read_size: int, progress: ProgressFn, stop: StopToken | None) -> None:
    """Seal path into temp with the native engine when it can take the paths, else the Python one."""
    seal = native_bridge.seal_file if _native_for(path, temp) else py_cipher.seal_stream
    _check_engine(*seal(header.algorithm, path, temp, header.pack(), key, header.nonce_prefix,
                        header.chunk_size, metadata, read_size, stop, progress))


def _open_v2(prefix: bytes, path: str, temp: str, keys: KeyRing, size: int, read_size: int,
             progress: ProgressFn, stop: StopToken | None) -> tuple[str, int, int]:
    """Decrypt a v2 file of `size` bytes into temp; return its stored name (validated), modification
    time, and the size the decrypted data must have."""
    header = format_v2.parse_header(prefix)
    opener = native_bridge.open_file if _native_for(path, temp) else py_cipher.open_stream
    ok, error, metadata = opener(header.algorithm, path, temp, prefix, keys.file_key(header),
                                 header.nonce_prefix, header.chunk_size, read_size, stop, progress)
    _check_engine(ok, error)
    raw_name, mtime_ns = format_v2.unpack_metadata(metadata)
    name = safe_original_name(raw_name)
    if name is None:
        raise _OperationError(_UNSAFE_NAME)
    body = size - format_v2.HEADER_SIZE
    chunks = -(-body // (header.chunk_size + format_v2.TAG_SIZE))
    return name, mtime_ns, body - chunks * format_v2.TAG_SIZE - len(metadata)


def _open_v1(algorithm: str, path: str, temp: str, password: str, size: int, read_size: int,
             progress: ProgressFn, stop: StopToken | None) -> tuple[str, int]:
    """Decrypt a v1 file (gfgLock 3.1 and older) of `size` bytes into temp; return its stored name
    (validated) and the size the decrypted data must have."""
    opener = native_bridge.decrypt_file_v1 if _native_for(path, temp) else py_cipher.decrypt_stream_v1
    ok, error, raw_name = opener(algorithm, path, temp, password, read_size, stop, progress)
    _check_engine(ok, error)
    name = safe_original_name(raw_name)
    if name is None:
        # CFB has no authentication, so an unreadable name almost always means a wrong
        # password; the decrypted bytes are garbage and must not replace the encrypted file.
        raise _OperationError("wrong password or the file is corrupted" if algorithm == "cfb" else _UNSAFE_NAME)
    return name, size - py_cipher.v1_overhead(algorithm) - len(raw_name) - 1  # the name ends with a NUL


def _native_for(*paths: str) -> bool:
    """True when the native engine is loaded and can take these paths: it needs them as UTF-8, which
    a name with an unpaired surrogate (allowed by NTFS) can't be."""
    if not native_bridge.NATIVE_AVAILABLE:
        return False
    try:
        for path in paths:
            path.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _check_engine(ok: bool, error: str) -> None:
    """Raise for a failed engine call: a stop ends the file as skipped, anything else as failed."""
    if ok:
        return
    if error == ENGINE_STOPPED:
        raise _Stopped
    raise _OperationError(error or "the encryption engine failed")


def _skip_reason(path: str) -> FileResult | None:
    """A failed or skipped result for paths that must not be processed, else None."""
    if os.path.islink(path):
        return FileResult(False, f"{path} is a link", "skipped", "Links are skipped; add the file the link points to")
    if not os.path.isfile(path):
        return FileResult(False, f"Critical error: {path} not found", "failed", _NOT_FOUND)
    if path.lower().endswith(TEMP_SUFFIX):
        return FileResult(False, f"{path} is a temporary file", "skipped", "Temporary file left by an unfinished job")
    return None


def _check_names(name: str, target: str, hidden: bool) -> None:
    """Fail before any work when the name couldn't be restored on decrypt, or the encrypted name is too long."""
    if safe_original_name(name.encode("utf-8", "surrogatepass")) != name:
        raise _OperationError("the file name can't be restored safely when decrypting; rename the file and try again")
    if not hidden and _utf16_length(target) > _MAX_NAME_LENGTH:
        raise _OperationError("the name is too long to add the encrypted extension; "
                              "turn on Hide file names or shorten the name")


def _utf16_length(name: str) -> int:
    """Length of a name in UTF-16 code units, the unit of the NTFS 255-character limit."""
    return len(name.encode("utf-16-le", "surrogatepass")) // 2


def _is_hidden_format(ch: str) -> bool:
    """True for an invisible format character that could disguise a name (such as U+202E)."""
    return unicodedata.category(ch) == "Cf" and ch not in _ALLOWED_FORMAT_CHARS


def _check_removable(path: str) -> None:
    """Fail before any work when the source can't be deleted afterwards."""
    if not os.access(path, os.W_OK):
        raise _OperationError("the file is read-only; clear Read-only in its Properties and try again")


def _is_own_name(path: str, name: str) -> bool:
    """True when name is the encrypted file's own name without its extension (any letter case)."""
    own = os.path.splitext(os.path.basename(path))[0]
    return os.path.normcase(name) == os.path.normcase(own)


def _version(info: os.stat_result) -> tuple[int, int, int, int]:
    """What identifies one version of a file: file id, volume, size, and modification time."""
    return info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns


def _confirm_unchanged(path: str, before: os.stat_result, output: str) -> None:
    """Remove output and fail unless path is still the file that was read (not replaced or edited)."""
    try:
        unchanged = _version(os.stat(path, follow_symlinks=False)) == _version(before)
    except OSError:  # moved or deleted meanwhile
        unchanged = False
    if not unchanged:
        _discard(output)
        raise _OperationError(_CHANGED)


def _remove_source(source: str, output: str) -> None:
    """Delete the source now that output is in place; if that fails, delete output instead."""
    try:
        os.remove(source)
    except OSError as error:
        _discard(output)
        raise _OperationError(f"the original couldn't be removed ({_describe(error)}), so nothing was changed. "
                              "Close any program using it and try again") from error


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


def _copy_zone_mark(source: str, target: str) -> None:
    """Copy the source's Mark of the Web (its Zone.Identifier stream), so a downloaded file stays marked."""
    try:
        with open(source + _ZONE_STREAM, "rb") as fh:
            mark = fh.read()
    except FileNotFoundError:  # the usual case: the file was not downloaded
        return
    except OSError as error:
        safe_print(f"Could not read the Zone.Identifier stream of {source}: {error}")
        return
    try:
        with open(target + _ZONE_STREAM, "wb") as fh:
            fh.write(mark)
    except OSError as error:
        safe_print(f"Could not copy the Zone.Identifier stream to {target}: {error}")


def _restore_mtime(path: str, mtime_ns: int) -> None:
    """Give the decrypted file its original modification time; the data is kept even if this fails."""
    try:
        os.utime(path, ns=(time.time_ns(), mtime_ns))
    except OSError as error:
        safe_print(f"Could not restore the modification time of {path}: {error}")


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


def _sentence(reason: str) -> str:
    """A reason as shown on its own in the file list: capitalized, without a trailing period."""
    reason = reason.strip().rstrip(".")
    return reason[:1].upper() + reason[1:]


def _report(result: FileResult) -> FileResult:
    """Echo the result to the console log and return it."""
    safe_print(result[1])
    return result
