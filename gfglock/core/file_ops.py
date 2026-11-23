# file_ops.py - safe file-level encryption and decryption, shared by the native and Python engines.
#
# The engines (native C++ or pure Python) only turn one file into another. Everything that decides
# which files exist afterwards lives here, in one place:
#   * new files use the v2 format (format_v2.py); v1 files from 3.1 and older still decrypt, and a
#     file that starts with the v2 magic is read as v2 whatever its extension;
#   * output goes to a fresh temp file (".<16 hex>.gfgpart") in the output folder, created exclusively;
#   * the result is checked (its exact size after encrypting, the stored name after decrypting) and
#     flushed to disk before anything else happens; decrypting also restores the stored modification
#     time and copies the Mark of the Web (the Zone.Identifier stream) from the encrypted file;
#   * it is then renamed to a name that does not exist yet (never overwriting a file), next to the
#     source or in the chosen output folder;
#   * the source is deleted only while it is still the file that was read (same file id, volume,
#     size, and modification time), so a file replaced or edited meanwhile is never lost. A source
#     that couldn't be deleted (read-only, or open in another program) is found before any work;
#     if it still can't be deleted afterwards, the new copy is removed again, so a file never ends
#     up in both forms. With keep_original the source stays where it is;
#   * a stop token ends a file early: its temp file is removed and the source is untouched;
#   * verify_file reads a file through without writing anything, which checks the password and data.
# Links, hard-linked files, and leftover temp files are skipped: encrypting them would leave the data
# readable through the link or the file's other names.
# The file name stored inside an encrypted file is untrusted (files can come from anyone), so it is
# validated as a single plain Windows file name before use. Legacy AES-CFB files have no
# authentication, so a wrong password can still yield a valid-looking name: such a file is deleted
# only when the restored name matches its own name, and kept otherwise.
# Every failure carries a category from reasons.py with its plain sentence; the engine's or
# Windows' own text stays in the result's log message.

from __future__ import annotations

import ctypes
import os
import re
import shutil
import time
import unicodedata
from collections.abc import Iterable
from ctypes import wintypes
from secrets import token_hex

from gfglock.core import format_v2, native_bridge, py_cipher, reasons
from gfglock.core.format_v2 import ENGINE_STOPPED, FormatError, KeyRing
from gfglock.core.py_cipher import ProgressFn, StopToken
from gfglock.utils.console import safe_print
from gfglock.utils.helpers import generate_encrypted_name

OUTCOME_DONE = "done"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"

# Algorithm code -> encrypted file extension. CFB files can only be decrypted.
EXTENSIONS = {"gcm": ".gfglock", "chacha": ".gfgcha", "cfb": ".gfglck"}
ENCRYPT_ALGORITHMS = ("gcm", "chacha")
ALGORITHM_FOR_EXT = {ext: algo for algo, ext in EXTENSIONS.items()}
ENCRYPTED_EXTS = frozenset(EXTENSIONS.values())
# Algorithm code -> the name the command line and its JSON use.
ALGORITHM_LABELS = {"gcm": "aes-256-gcm", "chacha": "chacha20-poly1305", "cfb": "aes-256-cfb"}

TEMP_SUFFIX = ".gfgpart"
_TEMP_NAME = re.compile(r"\.[0-9a-f]{16}\.gfgpart", re.IGNORECASE)
# A name made by Hide file names: when it was encrypted and 8 random hex digits, maybe " (2)".
_HIDDEN_NAME = re.compile(r"\d{14}_[0-9a-f]{8}(?: \(\d+\))?", re.IGNORECASE)
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
# Left free on a drive beyond an output, for the file system's own bookkeeping.
SPACE_MARGIN = 16 * 1024 * 1024

# The reason of a file a stop token ended: it stays as it was, so a later run should process it.
STOPPED_REASON = reasons.text(reasons.STOPPED)

# Opening a file for DELETE fails at once when another program has it open without letting others
# delete it (Word, a video player), which is what would stop the original being removed later.
_DELETE = 0x00010000
_SHARE_ALL = 0x00000007  # read, write, and delete
_OPEN_EXISTING = 3
_FLAG_OPEN_REPARSE_POINT = 0x00200000
_INVALID_HANDLE = wintypes.HANDLE(-1).value
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateFileW = _kernel32.CreateFileW
_CreateFileW.restype = wintypes.HANDLE
_CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.restype = wintypes.BOOL
_CloseHandle.argtypes = [wintypes.HANDLE]


class _OperationError(Exception):
    """A failure in one of the categories of reasons.py; the message is the log's text for it."""

    def __init__(self, category: str, detail: str = "", sentence: str = "") -> None:
        super().__init__(detail or reasons.text(category))
        self.category = category
        self.sentence = sentence or reasons.text(category)


class _Stopped(Exception):
    """The run's stop token ended the file before it finished."""


class FileResult(tuple):
    """What happened to one file. Unpacks as (ok, message) for callers that only need that.

    `outcome` is "done", "skipped", or "failed"; `reason` says why in plain words for the file list
    (a "done" row can carry one too) and `category` is its kind from reasons.py; `output` is the file
    that was written ("" unless done). The message is the log's line, with the engine's own text.
    """

    outcome: str
    reason: str
    output: str
    category: str

    def __new__(cls, ok: bool, message: str, outcome: str, reason: str = "", output: str = "",
                category: str = "") -> "FileResult":
        result = super().__new__(cls, (ok, message))
        result.outcome = outcome
        result.reason = reason
        result.output = output
        result.category = category
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
    keep_original: bool = False,
    output_dir: str = "",
) -> FileResult:
    """Encrypt one file and delete the original once the result is safely on disk.

    The encrypted file keeps the full original name (report.docx -> report.docx.gfglock) so files that
    differ only by extension can't collide, and gets " (2)" etc. if the name is taken. It goes next
    to the original, or into output_dir; keep_original leaves the original in place.
    """
    if algorithm not in ENCRYPT_ALGORITHMS:
        return FileResult(False, f"Critical error while encrypting {path}: unknown algorithm {algorithm!r}",
                          OUTCOME_FAILED, f"Unknown encryption method {algorithm!r}", category=reasons.UNKNOWN)
    skipped = _skip_reason(path)
    if skipped:
        return skipped
    if is_encrypted_path(path):
        return _skip(f"{path} is already encrypted", reasons.ALREADY_ENCRYPTED)

    folder = output_folder(path, output_dir)
    name = os.path.basename(path)
    temp = None
    try:
        source = os.stat(path, follow_symlinks=False)
        if source.st_nlink > 1 and not keep_original:
            return _skip(f"{path} has other hard links", reasons.HARD_LINK)
        target = generate_encrypted_name(path, encrypt_name, EXTENSIONS[algorithm])
        _check_names(name, target, encrypt_name)
        if not keep_original:
            _check_removable(path)
        header, key = keys.new_header(algorithm)
        metadata = format_v2.pack_metadata(name, source.st_mtime_ns)
        expected = format_v2.encrypted_size(source.st_size, name, header.chunk_log2)
        temp = _create_temp(folder)
        _seal(path, temp, header, key, metadata, read_size, progress, stop, expected)
        if os.path.getsize(temp) != expected:
            if os.path.getsize(path) != source.st_size:
                raise _OperationError(reasons.CHANGED)
            _raise_short_write(folder, expected, "the encrypted file is incomplete")
        _flush_to_disk(temp)
        _copy_zone_mark(path, temp)  # so the restored file is marked as downloaded again
        final = _move_to_unique_name(temp, folder, target)
        temp = None
        _confirm_unchanged(path, source, final)
        if not keep_original:
            _remove_source(path, final)
        return _report(FileResult(True, f"Encrypted: {path} -> {final}", OUTCOME_DONE, output=final))
    except _Stopped:
        return _skip(f"Stopped: {path} was not changed", reasons.STOPPED)
    except (_OperationError, FormatError, OSError) as error:
        return _failed("encrypting", path, error)
    finally:
        _discard(temp)  # set to None once the output is in place


def decrypt_file(
    path: str,
    keys: KeyRing,
    read_size: int = 0,
    progress: ProgressFn = None,
    stop: StopToken | None = None,
    keep_original: bool = False,
    output_dir: str = "",
) -> FileResult:
    """Decrypt one file under its original name, then delete the encrypted file.

    The restored file goes next to the encrypted one, or into output_dir. An existing file with the
    original name is never overwritten; the restored copy gets a " (2)" style suffix instead.
    keep_original leaves the encrypted file in place.
    """
    skipped = _skip_reason(path)
    if skipped:
        return skipped

    folder = output_folder(path, output_dir)
    temp = None
    try:
        source = os.stat(path, follow_symlinks=False)
        prefix = _read_prefix(path)
        legacy = _legacy_algorithm(path, prefix)
        if legacy == "":
            return _skip(f"{path} is already decrypted", reasons.NOT_ENCRYPTED)
        if not keep_original:
            _check_removable(path)
        temp = _create_temp(folder)
        mtime_ns = None
        if legacy is None:
            name, mtime_ns, expected = _open_v2(prefix, path, temp, keys, source.st_size, read_size, progress, stop)
        else:
            name, expected = _open_v1(legacy, path, temp, keys.password, source.st_size, read_size, progress, stop)
        if os.path.getsize(temp) != expected:  # an engine fault must never cost the encrypted file
            _raise_short_write(folder, expected, "the decrypted file is incomplete")
        _flush_to_disk(temp)
        _copy_zone_mark(path, temp)  # before the time: writing a stream updates the modification time
        if mtime_ns is not None:
            _restore_mtime(temp, mtime_ns)
        final = _move_to_unique_name(temp, folder, name)
        temp = None
        if keep_original:
            return _report(FileResult(True, f"Decrypted: {path} -> {final}", OUTCOME_DONE, output=final))
        if legacy == "cfb" and not _is_own_name(path, name):
            message = f"Decrypted: {path} -> {final}; the encrypted file was kept (CFB can't confirm the password)"
            return _report(FileResult(True, message, OUTCOME_DONE, reasons.text(reasons.CFB_KEPT), final,
                                      reasons.CFB_KEPT))
        _confirm_unchanged(path, source, final)
        _remove_source(path, final)
        return _report(FileResult(True, f"Decrypted: {path} -> {final}", OUTCOME_DONE, output=final))
    except _Stopped:
        return _skip(f"Stopped: {path} was not changed", reasons.STOPPED)
    except (_OperationError, FormatError, OSError) as error:
        return _failed("decrypting", path, error)
    finally:
        _discard(temp)  # set to None once the output is in place


def verify_file(
    path: str,
    keys: KeyRing,
    read_size: int = 0,
    progress: ProgressFn = None,
    stop: StopToken | None = None,
) -> FileResult:
    """Check that the password opens a file and that its data is intact, without writing anything.

    AES-GCM and ChaCha20-Poly1305 authenticate every chunk, so reading the file through to the end
    proves both. The old CFB format has no authentication: only its stored name can be checked.
    """
    skipped = _skip_reason(path)
    if skipped:
        return skipped
    try:
        source = os.stat(path, follow_symlinks=False)
        prefix = _read_prefix(path)
        legacy = _legacy_algorithm(path, prefix)
        if legacy == "":
            return _skip(f"{path} is not encrypted", reasons.NOT_ENCRYPTED)
        if legacy is None:
            _open_v2(prefix, path, os.devnull, keys, source.st_size, read_size, progress, stop)
        else:
            _open_v1(legacy, path, os.devnull, keys.password, source.st_size, read_size, progress, stop)
        if legacy == "cfb":
            return _report(FileResult(True, f"Checked: {path} (CFB: its stored name only)", OUTCOME_DONE,
                                      "Its stored name looks right; the old .gfglck format can't confirm "
                                      "the password further", category=reasons.VERIFIED))
        return _report(FileResult(True, f"Checked: {path}", OUTCOME_DONE, reasons.text(reasons.VERIFIED),
                                  category=reasons.VERIFIED))
    except _Stopped:
        return _skip(f"Stopped: {path} was not checked to the end", reasons.STOPPED)
    except (_OperationError, FormatError, OSError) as error:
        return _failed("checking", path, error)


def describe_file(path: str) -> dict[str, object]:
    """What an encrypted file's plaintext header says, read without the password.

    Raises OSError when the file can't be read, and FormatError when it isn't a gfgLock file or
    comes from a newer version.
    """
    size = os.path.getsize(path)
    prefix = _read_prefix(path)
    legacy = _legacy_algorithm(path, prefix)
    if legacy == "":
        raise FormatError("not a gfgLock file")
    hidden = _HIDDEN_NAME.fullmatch(os.path.splitext(os.path.basename(path))[0]) is not None
    info: dict[str, object] = {"path": os.path.abspath(path), "size": size, "hidden_name": hidden}
    if legacy is not None:
        info.update(format=1, algorithm=ALGORITHM_LABELS[legacy], kdf="pbkdf2-sha256",
                    kdf_iterations=native_bridge.V1_ITERATIONS, authenticated=legacy != "cfb")
        return info
    header = format_v2.parse_header(prefix)
    info.update(format=format_v2.VERSION, algorithm=ALGORITHM_LABELS[header.algorithm], kdf="argon2id",
                kdf_memory_mib=header.kdf.memory_kib // 1024, kdf_iterations=header.kdf.iterations,
                kdf_lanes=header.kdf.lanes, chunk_size=header.chunk_size, authenticated=True)
    return info


def output_size(size: int, encrypting: bool) -> int:
    """About how many bytes one file's output takes on disk (an encrypted file adds its header and tags)."""
    return format_v2.encrypted_size(size, "x" * 64) if encrypting else size


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
    raise _OperationError(reasons.IO_ERROR, f"no free file name for {name}")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _skip(message: str, category: str) -> FileResult:
    """A file left as it was on purpose."""
    return FileResult(False, message, OUTCOME_SKIPPED, reasons.text(category), category=category)


def _failed(verb: str, path: str, error: BaseException) -> FileResult:
    """The result of a file that failed: its plain sentence, and the full text in the log line."""
    if isinstance(error, _OperationError):
        category, sentence = error.category, error.sentence
    else:
        category = reasons.categorize(error)
        sentence = reasons.text(category)
    return _report(FileResult(False, f"Critical error while {verb} {path}: {_describe(error)}", OUTCOME_FAILED,
                              sentence, category=category))


def _seal(path: str, temp: str, header: format_v2.Header, key: bytes, metadata: bytes,
          read_size: int, progress: ProgressFn, stop: StopToken | None, expected: int) -> None:
    """Seal path into temp with the native engine when it can take the paths, else the Python one."""
    seal = native_bridge.seal_file if _native_for(path, temp) else py_cipher.seal_stream
    _check_engine(*seal(header.algorithm, path, temp, header.pack(), key, header.nonce_prefix,
                        header.chunk_size, metadata, read_size, stop, progress),
                  folder=os.path.dirname(temp), expected=expected)


def _open_v2(prefix: bytes, path: str, temp: str, keys: KeyRing, size: int, read_size: int,
             progress: ProgressFn, stop: StopToken | None) -> tuple[str, int, int]:
    """Decrypt a v2 file of `size` bytes into temp; return its stored name (validated), modification
    time, and the size the decrypted data must have."""
    header = format_v2.parse_header(prefix)
    body = size - format_v2.HEADER_SIZE
    chunks = -(-body // (header.chunk_size + format_v2.TAG_SIZE))
    plaintext = body - chunks * format_v2.TAG_SIZE
    opener = native_bridge.open_file if _native_for(path, temp) else py_cipher.open_stream
    ok, error, metadata = opener(header.algorithm, path, temp, prefix, keys.file_key(header),
                                 header.nonce_prefix, header.chunk_size, read_size, stop, progress)
    _check_engine(ok, error, folder=os.path.dirname(temp), expected=plaintext)
    raw_name, mtime_ns = format_v2.unpack_metadata(metadata)
    name = safe_original_name(raw_name)
    if name is None:
        raise _OperationError(reasons.UNSAFE_NAME)
    return name, mtime_ns, plaintext - len(metadata)


def _open_v1(algorithm: str, path: str, temp: str, password: str, size: int, read_size: int,
             progress: ProgressFn, stop: StopToken | None) -> tuple[str, int]:
    """Decrypt a v1 file (gfgLock 3.1 and older) of `size` bytes into temp; return its stored name
    (validated) and the size the decrypted data must have."""
    opener = native_bridge.decrypt_file_v1 if _native_for(path, temp) else py_cipher.decrypt_stream_v1
    ok, error, raw_name = opener(algorithm, path, temp, password, read_size, stop, progress)
    _check_engine(ok, error, folder=os.path.dirname(temp), expected=size)
    name = safe_original_name(raw_name)
    if name is None:
        # CFB has no authentication, so an unreadable name almost always means a wrong
        # password; the decrypted bytes are garbage and must not replace the encrypted file.
        if algorithm == "cfb":
            raise _OperationError(reasons.WRONG_PASSWORD, "wrong password or the file is corrupted")
        raise _OperationError(reasons.UNSAFE_NAME)
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


def _check_engine(ok: bool, error: str, folder: str = "", expected: int = 0) -> None:
    """Raise for a failed engine call: a stop ends the file as skipped, anything else as failed.

    A write failure on a drive without room for the output is reported as the full drive it is,
    with the space still needed (the native engine can't tell the two apart itself).
    """
    if ok:
        return
    if error == ENGINE_STOPPED:
        raise _Stopped
    detail = error or "the encryption engine failed"
    category = reasons.categorize(detail)
    if category in (reasons.IO_ERROR, reasons.DISK_FULL) and folder:
        needed = _shortfall(folder, expected)
        if needed:
            raise _OperationError(reasons.DISK_FULL, detail, reasons.disk_full_text(needed))
    raise _OperationError(category, detail)


def _skip_reason(path: str) -> FileResult | None:
    """A failed or skipped result for paths that must not be processed, else None."""
    if os.path.islink(path):
        return _skip(f"{path} is a link", reasons.LINK)
    if not os.path.isfile(path):
        return FileResult(False, f"Critical error: {path} not found", OUTCOME_FAILED,
                          reasons.text(reasons.NOT_FOUND), category=reasons.NOT_FOUND)
    if path.lower().endswith(TEMP_SUFFIX):
        return _skip(f"{path} is a temporary file", reasons.TEMP_FILE)
    return None


def output_folder(path: str, output_dir: str) -> str:
    """Where a file's result goes: output_dir when given, else the file's own folder."""
    return os.path.abspath(output_dir) if output_dir else os.path.dirname(os.path.abspath(path))


def _read_prefix(path: str) -> bytes:
    """The first bytes of a file, enough for a v2 header."""
    with open(path, "rb") as fh:
        return fh.read(format_v2.HEADER_SIZE)


def _legacy_algorithm(path: str, prefix: bytes) -> str | None:
    """None for a v2 file, the v1 algorithm of a gfgLock 3.1 file, or "" for a file gfgLock didn't make."""
    if format_v2.has_magic(prefix):
        return None
    return ALGORITHM_FOR_EXT.get(os.path.splitext(path)[1].lower(), "")


def _check_names(name: str, target: str, hidden: bool) -> None:
    """Fail before any work when the name couldn't be restored on decrypt, or the encrypted name is too long."""
    if safe_original_name(name.encode("utf-8", "surrogatepass")) != name:
        raise _OperationError(reasons.NAME_NOT_RESTORABLE)
    if not hidden and _utf16_length(target) > _MAX_NAME_LENGTH:
        raise _OperationError(reasons.NAME_TOO_LONG)


def _utf16_length(name: str) -> int:
    """Length of a name in UTF-16 code units, the unit of the NTFS 255-character limit."""
    return len(name.encode("utf-16-le", "surrogatepass")) // 2


def _is_hidden_format(ch: str) -> bool:
    """True for an invisible format character that could disguise a name (such as U+202E)."""
    return unicodedata.category(ch) == "Cf" and ch not in _ALLOWED_FORMAT_CHARS


def _check_removable(path: str) -> None:
    """Fail before any work when the source can't be deleted afterwards: it is read-only, open in a
    program that doesn't let others delete it, or Windows denies deleting it."""
    if not os.access(path, os.W_OK):
        raise _OperationError(reasons.READ_ONLY)
    handle = _CreateFileW(path, _DELETE, _SHARE_ALL, None, _OPEN_EXISTING, _FLAG_OPEN_REPARSE_POINT, None)
    if handle in (None, 0, _INVALID_HANDLE):
        error = ctypes.WinError(ctypes.get_last_error())
        category = reasons.categorize(error)
        if category in (reasons.IN_USE, reasons.ACCESS_DENIED):
            raise _OperationError(category, f"the original can't be deleted: {error.strerror}")
        return  # anything else shows up, with its own reason, when the file is read
    _CloseHandle(handle)


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
        raise _OperationError(reasons.CHANGED)


def _remove_source(source: str, output: str) -> None:
    """Delete the source now that output is in place; if that fails, delete output instead."""
    try:
        os.remove(source)
    except OSError as error:
        _discard(output)
        category = reasons.categorize(error)
        sentence = (f"The original couldn't be removed ({reasons.label(category)}), so nothing was changed. "
                    "Close any program using it and try again")
        raise _OperationError(category, f"the original couldn't be removed ({_describe(error)})", sentence) from error


def _raise_short_write(folder: str, expected: int, detail: str) -> None:
    """Fail a file whose output came out short: the drive filled up, or the engine misbehaved."""
    needed = _shortfall(folder, expected)
    if needed:
        raise _OperationError(reasons.DISK_FULL, f"{detail} (disk full)", reasons.disk_full_text(needed))
    raise _OperationError(reasons.IO_ERROR, f"{detail} (disk full?)")


def _shortfall(folder: str, expected: int) -> int:
    """How much more free space the drive of folder needs for an output of `expected` bytes; 0 when
    it has room, or when its free space can't be read."""
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return 0
    return max(0, expected + SPACE_MARGIN - free)


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
    raise _OperationError(reasons.IO_ERROR, "could not create a temporary file")


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
    raise _OperationError(reasons.IO_ERROR, f"no free file name for {name}")


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


def _describe(error: BaseException) -> str:
    """The log's text for an error: the system's own description, or the message."""
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)


def _report(result: FileResult) -> FileResult:
    """Echo the result to the console log and return it."""
    safe_print(result[1])
    return result
