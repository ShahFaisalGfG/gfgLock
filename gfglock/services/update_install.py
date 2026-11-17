# update_install.py - downloads a verified update and installs it (stdlib and Windows API only)
#
# Shared by gfgLock, gfgShield, and CC-Gen-Ultimate: keep the copies identical apart from the
# package name in the imports. An installed copy hands the downloaded installer to Inno Setup,
# which runs silently once the app has exited (installer/update_support.iss waits for it). The
# portable exe swaps itself: a running exe can be renamed but not overwritten, so it moves aside
# and the new exe takes its name, which keeps shortcuts and scheduled tasks working.

from __future__ import annotations

import configparser
import ctypes
import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
from typing import Any

from gfglock.services.update_feed import FeedError, UpdateFile, UpdatePackage, UpdateSource, is_newer, open_url

SYSTEM = "system"
USER = "user"
PORTABLE_EXE = "portable-exe"
PORTABLE_FOLDER = "portable-folder"
SOURCE = "source"
SELF_UPDATING = frozenset({SYSTEM, USER, PORTABLE_EXE})
# Written by the installers (installer/update_support.iss): which installer put this copy here.
INSTALL_INFO = "install.ini"
STATE_FILE = "updates.json"
DOWNLOAD_TIMEOUT_S = 30
_CHUNK = 1024 * 1024
_ERROR_CANCELLED = 1223  # the user said no to the administrator prompt

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32")
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x1
_FILE_SHARE_DELETE = 0x4
_OPEN_EXISTING = 3
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_INVALID_HANDLE = wintypes.HANDLE(-1).value
_THREAD_MODE_BACKGROUND_BEGIN = 0x00010000
_THREAD_MODE_BACKGROUND_END = 0x00020000
_COST_FIXED, _COST_VARIABLE = 2, 3


def _api(dll: ctypes.WinDLL, name: str, restype: Any, *argtypes: Any) -> Any:
    function = getattr(dll, name)
    function.restype = restype
    function.argtypes = list(argtypes)
    return function


_CreateFileW = _api(_kernel32, "CreateFileW", wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_ReadFile = _api(_kernel32, "ReadFile", wintypes.BOOL, wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                 ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID)
_CloseHandle = _api(_kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
_GetCurrentThread = _api(_kernel32, "GetCurrentThread", wintypes.HANDLE)
_SetThreadPriority = _api(_kernel32, "SetThreadPriority", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int)
_IsUserAnAdmin = _api(_shell32, "IsUserAnAdmin", wintypes.BOOL)


class InstallError(Exception):
    """A download or install step failed; the message suits the user and the log."""


class FileMismatch(InstallError):
    """A downloaded file no longer matches its published checksum; it must be downloaded again."""


class UpdateCancelled(Exception):
    """The download was stopped."""


class _ConnectivityHint(ctypes.Structure):
    _fields_ = [("level", ctypes.c_int), ("cost", ctypes.c_int), ("approaching_limit", ctypes.c_ubyte),
                ("over_limit", ctypes.c_ubyte), ("roaming", ctypes.c_ubyte)]


# ── Where this copy came from ────────────────────────────────────────────────


def exe_path() -> str:
    return os.path.abspath(sys.executable)


def detect_install_kind() -> str:
    """How this copy runs: system or user (an installer), portable-exe, portable-folder, or source."""
    bundle = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or bundle is None:
        return SOURCE
    exe_dir = os.path.dirname(exe_path())
    if os.path.normcase(os.path.dirname(os.path.abspath(bundle))) != os.path.normcase(exe_dir):
        return PORTABLE_EXE  # the one-file exe unpacks to a temp folder at each start
    parser = configparser.ConfigParser()
    try:
        parser.read(os.path.join(exe_dir, INSTALL_INFO), encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return PORTABLE_FOLDER
    kind = parser.get("install", "kind", fallback="")
    return kind if kind in (SYSTEM, USER) else PORTABLE_FOLDER


def is_elevated() -> bool:
    """True when this process runs as administrator."""
    return bool(_IsUserAnAdmin())


def needs_approval(kind: str) -> bool:
    """A copy installed for all users updates through an administrator prompt, unless already elevated."""
    return kind == SYSTEM and not is_elevated()


def is_metered() -> bool:
    """True on a metered or roaming connection (Windows 10 2004 and later report this), else False."""
    try:
        hint_api = _api(ctypes.WinDLL("iphlpapi"), "GetNetworkConnectivityHint", wintypes.DWORD,
                        ctypes.POINTER(_ConnectivityHint))
    except (OSError, AttributeError):
        return False
    hint = _ConnectivityHint()
    if hint_api(ctypes.byref(hint)) != 0:
        return False
    return hint.cost in (_COST_FIXED, _COST_VARIABLE) or bool(hint.over_limit or hint.roaming)


@contextmanager
def background_priority() -> Iterator[None]:
    """Run the block at background CPU, disk, and memory priority, so a download never slows the PC."""
    thread = _GetCurrentThread()
    lowered = bool(_SetThreadPriority(thread, _THREAD_MODE_BACKGROUND_BEGIN))
    try:
        yield
    finally:
        if lowered:
            _SetThreadPriority(thread, _THREAD_MODE_BACKGROUND_END)


# ── Download ─────────────────────────────────────────────────────────────────


class DownloadCancel:
    """Stops a download: the flag ends the read loop, and closing the response ends a blocked read."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response: Any = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except (OSError, ValueError):
                pass  # already closed by the reader

    def watch(self, response: Any) -> None:
        with self._lock:
            self._response = response
        if self._event.is_set():
            self.cancel()


def download_package(source: UpdateSource, tag: str, package: UpdatePackage, folder: str,
                     progress: Callable[[int, int], None], cancel: DownloadCancel,
                     opener: Callable[..., Any] = open_url, target_names: Sequence[str] = ()) -> list[str]:
    """Download every file of `package` into `folder` and check each one; returns their paths.

    A partly downloaded file (.part) resumes where it stopped. A file already complete and correct
    isn't fetched again. `target_names` renames the files (the portable exe's "<exe>.new").
    """
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as error:
        raise InstallError(f"Couldn't create {folder}: {error.strerror or error}") from error
    names = list(target_names) or [item.name for item in package.files]
    total = package.size
    finished = 0
    paths = []
    for item, name in zip(package.files, names):
        target = os.path.join(folder, name)
        _download_file(source, source.file_url(tag, item.name), target, item,
                       lambda done, base=finished: progress(base + done, total), cancel, opener)
        finished += item.size
        paths.append(target)
    return paths


def _download_file(source: UpdateSource, url: str, target: str, expected: UpdateFile,
                   progress: Callable[[int], None], cancel: DownloadCancel, opener: Callable[..., Any]) -> None:
    if _matches(target, expected):
        progress(expected.size)
        return
    part = f"{target}.part"
    start = _resume_offset(part, expected.size)
    digest = hashlib.sha256()
    if start:
        _hash_into(digest, part, start)
    headers = {"Range": f"bytes={start}-"} if start else {}
    try:
        with opener(source, url, DOWNLOAD_TIMEOUT_S, headers) as response:
            cancel.watch(response)
            if start and getattr(response, "status", 200) != 206:
                start, digest = 0, hashlib.sha256()  # the server sent the whole file instead
            written = _copy(response, part, start, expected, digest, progress, cancel)
    except UpdateCancelled:
        raise
    except FeedError as error:
        raise InstallError(str(error)) from error
    except (OSError, ValueError) as error:  # URLError and HTTPError are OSErrors
        if cancel.cancelled:
            raise UpdateCancelled() from error
        raise InstallError(f"The download of {expected.name} stopped: {getattr(error, 'reason', error)}") from error
    finally:
        cancel.watch(None)
    if written != expected.size:
        raise InstallError(f"The download of {expected.name} ended early; it resumes next time.")
    if digest.hexdigest() != expected.sha256:
        _remove(part)
        raise InstallError(f"{expected.name} didn't match its published checksum, so it was deleted.")
    try:
        os.replace(part, target)
    except OSError as error:
        raise InstallError(f"Couldn't save {expected.name}: {error.strerror or error}") from error


def _copy(response: Any, part: str, start: int, expected: UpdateFile, digest: Any,
          progress: Callable[[int], None], cancel: DownloadCancel) -> int:
    """Append the response body to `part` from `start`, hashing as it goes; returns the file's size."""
    written = start
    progress(written)
    with open(part, "r+b" if start else "wb") as fh:
        fh.seek(start)
        fh.truncate()
        while True:
            if cancel.cancelled:
                raise UpdateCancelled()
            block = response.read(_CHUNK)
            if not block:
                break
            written += len(block)
            if written > expected.size:
                raise InstallError(f"{expected.name} is larger than published, so the download stopped.")
            digest.update(block)
            fh.write(block)
            progress(written)
    return written


def _resume_offset(part: str, size: int) -> int:
    """How much of `part` can be kept: all of it while it is smaller than the whole file."""
    try:
        have = os.path.getsize(part)
    except OSError:
        return 0
    if have < size:
        return have
    _remove(part)
    return 0


def _hash_into(digest: Any, path: str, length: int) -> None:
    with open(path, "rb") as fh:
        remaining = length
        while remaining:
            block = fh.read(min(_CHUNK, remaining))
            if not block:
                break
            digest.update(block)
            remaining -= len(block)


def _matches(path: str, expected: UpdateFile) -> bool:
    """True when `path` exists with the expected size and SHA-256."""
    try:
        if os.path.getsize(path) != expected.size:
            return False
        digest = hashlib.sha256()
        _hash_into(digest, path, expected.size)
    except OSError:
        return False
    return digest.hexdigest() == expected.sha256


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass  # in use; it is replaced or cleaned up next time


# ── Locked verification ──────────────────────────────────────────────────────


class LockedFile:
    """A file opened so no other program can change it while it is checked and started.

    Other programs may still read it (the installer reads itself). allow_rename also lets this
    process move it (the portable exe's swap), which a plain lock would block.
    """

    def __init__(self, path: str, allow_rename: bool = False) -> None:
        share = _FILE_SHARE_READ | (_FILE_SHARE_DELETE if allow_rename else 0)
        handle = _CreateFileW(path, _GENERIC_READ, share, None, _OPEN_EXISTING, _FILE_FLAG_SEQUENTIAL_SCAN, None)
        if handle in (None, _INVALID_HANDLE):
            error = ctypes.WinError(ctypes.get_last_error())
            raise InstallError(f"Couldn't open {os.path.basename(path)}: {error.strerror}")
        self.path = path
        self._handle = handle

    def sha256(self) -> str:
        digest = hashlib.sha256()
        buffer = ctypes.create_string_buffer(_CHUNK)
        read = wintypes.DWORD()
        while True:
            if not _ReadFile(self._handle, buffer, _CHUNK, ctypes.byref(read), None):
                error = ctypes.WinError(ctypes.get_last_error())
                raise InstallError(f"Couldn't read {os.path.basename(self.path)}: {error.strerror}")
            if read.value == 0:
                return digest.hexdigest()
            digest.update(buffer.raw[:read.value])

    def close(self) -> None:
        if self._handle is not None:
            _CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> LockedFile:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def lock_verified(paths: Sequence[str], files: Sequence[UpdateFile], allow_rename: bool = False) -> list[LockedFile]:
    """Lock every file and check its SHA-256 through the lock; raises InstallError on any mismatch.

    `files` come from a manifest whose signature was just checked, never from saved state.
    """
    if len(paths) != len(files):
        raise InstallError("The downloaded update doesn't match its published file list.")
    locks: list[LockedFile] = []
    try:
        for path, expected in zip(paths, files):
            lock = LockedFile(path, allow_rename)
            locks.append(lock)
            if lock.sha256() != expected.sha256:
                raise FileMismatch(f"{expected.name} changed after it was downloaded, so it wasn't installed.")
    except BaseException:
        for lock in locks:
            lock.close()
        raise
    return locks


# ── Install ──────────────────────────────────────────────────────────────────


def installer_arguments(relaunch: bool, log_path: str, extra: Sequence[str] = ()) -> str:
    """Inno Setup's silent-update command line; update_support.iss reads /updatepid and /relaunch."""
    args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/updatepid={os.getpid()}",
            f"/relaunch={1 if relaunch else 0}", f'/LOG="{log_path}"', *extra]
    return " ".join(args)


def launch_installer(installer: str, arguments: str) -> None:
    """Start the installer through the shell (never a program by bare name).

    Setup asks for administrator rights itself when it needs them; it starts after this app exits.
    """
    try:
        os.startfile(installer, "open", arguments)  # type: ignore[attr-defined]
    except OSError as error:
        if getattr(error, "winerror", None) == _ERROR_CANCELLED:
            raise InstallError("The update was not installed: the administrator prompt was declined.") from error
        raise InstallError(f"Couldn't start the installer: {error.strerror or error}") from error


def swap_portable_exe(new_exe: str, exe: str) -> None:
    """Put `new_exe` in place of the running `exe`, which moves aside as "<exe>.old"; undone on failure."""
    old = f"{exe}.old"
    _remove(old)
    try:
        os.replace(exe, old)
    except OSError as error:
        raise InstallError(f"Couldn't replace {os.path.basename(exe)}: {error.strerror or error}") from error
    try:
        os.replace(new_exe, exe)
    except OSError as error:
        try:
            os.replace(old, exe)
        except OSError:
            pass  # the original stays as "<exe>.old"; the error below says the update failed
        raise InstallError(f"Couldn't replace {os.path.basename(exe)}: {error.strerror or error}") from error


def start_program(path: str) -> None:
    """Start the updated app through the shell."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except OSError as error:
        raise InstallError(f"Couldn't start {os.path.basename(path)}: {error.strerror or error}") from error


def remove_leftovers(exe: str) -> None:
    """Delete the exe a portable update moved aside; it can go once the new one is running."""
    _remove(f"{exe}.old")


def remove_files(paths: Sequence[str]) -> None:
    """Delete downloaded update files (and their .part files), then their folder when it is empty."""
    folders = set()
    for path in paths:
        _remove(path)
        _remove(f"{path}.part")
        folders.add(os.path.dirname(path))
    for folder in folders:
        try:
            os.rmdir(folder)
        except OSError:
            pass  # not empty or in use: another download's files stay


# ── Saved state ──────────────────────────────────────────────────────────────


@dataclass
class UpdateState:
    """What the updater remembers between starts (updates.json in the data folder)."""

    last_check: float = 0.0          # time.time() of the last check that reached the server
    skipped: str = ""                # a version the user chose to skip
    pending_version: str = ""        # a downloaded update waiting to be installed
    pending_kind: str = ""           # the package kind it was downloaded for
    pending_files: list[str] = field(default_factory=list)  # its files, removed once installed
    attempted: str = ""              # the version whose install started when the app last closed
    failed: str = ""                 # a version whose install started but didn't take

    def check_due(self, interval_s: float, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return not (0 <= now - self.last_check < interval_s)

    def clear_pending(self) -> None:
        self.pending_version, self.pending_kind, self.pending_files = "", "", []


def load_state(path: str) -> UpdateState:
    """The saved state, or a fresh one when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return UpdateState()
    state = UpdateState()
    if not isinstance(raw, dict):
        return state
    for name, default in asdict(state).items():
        value = raw.get(name, default)
        if isinstance(default, float) and isinstance(value, (int, float)) and not isinstance(value, bool):
            setattr(state, name, float(value))
        elif isinstance(default, list) and isinstance(value, list) and all(isinstance(v, str) for v in value):
            setattr(state, name, list(value))
        elif isinstance(default, str) and isinstance(value, str):
            setattr(state, name, value)
    return state


def save_state(path: str, state: UpdateState) -> bool:
    """Write the state atomically; False when it couldn't be saved."""
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(state), fh, indent=2)
        os.replace(tmp, path)
    except OSError:
        _remove(tmp)
        return False
    return True


def settle_pending(state: UpdateState, current_version: str) -> bool:
    """Forget an update that is now installed, or note one whose install didn't take; True if changed."""
    changed = False
    if state.pending_version and not is_newer(state.pending_version, current_version):
        remove_files(state.pending_files)
        state.clear_pending()
        changed = True
    if state.attempted:
        if is_newer(state.attempted, current_version):
            state.failed = state.attempted
        state.attempted = ""
        changed = True
    if state.failed and not is_newer(state.failed, current_version):
        state.failed = ""
        changed = True
    return changed
