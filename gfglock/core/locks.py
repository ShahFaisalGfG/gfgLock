# locks.py - named mutexes shared by gfgLock's window and its command line (stdlib only).
#
# The installers wait while gfgLockAppMutex exists (Inno Setup's AppMutex), so the window and a
# running gfglock command both hold it, and an install never replaces files that are in use.
# A run also claims every folder it writes temp files in. The sweep of the temp files an
# interrupted run left behind deletes only in folders no other run had claimed, in this process or
# any other gfgLock process of the session, so the window and the command line (or two commands)
# never delete each other's .gfgpart files. A claim is a named mutex that exists while some run
# holds a handle to it; Windows closes the handles of a process that crashed, which frees its
# folders for the next run's sweep.

from __future__ import annotations

import ctypes
import hashlib
import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from ctypes import wintypes
from typing import Any

from gfglock.utils.logging import write_log

# Inno Setup's AppMutex waits while either exists, so the installers never replace a running copy.
APP_MUTEXES = ("gfgLockAppMutex", "Global\\gfgLockAppMutex")
# One per claimed folder, in this logon session's namespace (the window and the commands a user runs).
FOLDER_CLAIM_PREFIX = "Local\\gfgLock-folder-"
# Everyone may open the installers' mutexes to wait on them (SYNCHRONIZE) and nothing more, so an
# installer running in another session or as another account still sees a running copy.
_APP_MUTEX_SDDL = "D:(A;;0x00100000;;;WD)"
_SDDL_REVISION_1 = 1
_SYNCHRONIZE = 0x00100000
_ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)


def _api(dll: ctypes.WinDLL, name: str, restype: Any, *argtypes: Any) -> Any:
    """A function of dll with its result and argument types declared."""
    function = getattr(dll, name)
    function.restype = restype
    function.argtypes = argtypes
    return function


class _SecurityAttributes(ctypes.Structure):
    """SECURITY_ATTRIBUTES for CreateMutexExW."""

    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", wintypes.LPVOID),
                ("bInheritHandle", wintypes.BOOL)]


_CloseHandle = _api(_kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
_LocalFree = _api(_kernel32, "LocalFree", wintypes.HLOCAL, wintypes.HLOCAL)
_CreateMutexW = _api(_kernel32, "CreateMutexW", wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_CreateMutexExW = _api(_kernel32, "CreateMutexExW", wintypes.HANDLE,
                       wintypes.LPVOID, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
_ConvertSddl = _api(_advapi32, "ConvertStringSecurityDescriptorToSecurityDescriptorW", wintypes.BOOL,
                    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.ULONG))

# Handles of APP_MUTEXES, open until the process exits or release_app_mutexes().
_app_mutexes: list[int] = []


def hold_app_mutexes() -> None:
    """Create the mutexes the installers check (AppMutex) and keep them until this process exits.

    Creating the Global one can be refused in some sessions; the installers then see the other one.
    """
    descriptor = wintypes.LPVOID()
    if not _ConvertSddl(_APP_MUTEX_SDDL, _SDDL_REVISION_1, ctypes.byref(descriptor), None):
        write_log(f"Could not build the installer mutex access rules: {ctypes.WinError(ctypes.get_last_error())}",
                  "critical")
    attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
    security = ctypes.cast(ctypes.pointer(attributes), wintypes.LPVOID) if descriptor else None
    try:
        for name in APP_MUTEXES:
            # Asking only for SYNCHRONIZE (all the access rules grant) also opens one that another
            # gfgLock window or session made; CreateMutexW would ask for full access and be refused.
            handle = _CreateMutexExW(security, name, 0, _SYNCHRONIZE)
            if handle:
                _app_mutexes.append(handle)
            else:
                write_log(f"Could not create the mutex {name}: {ctypes.WinError(ctypes.get_last_error())}", "critical")
    finally:
        if descriptor:
            _LocalFree(descriptor)


def release_app_mutexes() -> None:
    """Let go of the installer mutexes early: an update's installer waits for them as gfgLock exits."""
    while _app_mutexes:
        _CloseHandle(_app_mutexes.pop())


def folder_claim_name(folder: str) -> str:
    """The mutex name that claims a folder: the same for every spelling Windows treats as one path."""
    key = os.path.normcase(os.path.abspath(folder)).encode("utf-8", "surrogatepass")
    return FOLDER_CLAIM_PREFIX + hashlib.sha256(key).hexdigest()[:40]


@contextmanager
def claim_folders(folders: Iterable[str]) -> Iterator[list[str]]:
    """Claim the run's folders while it runs; yields those no other run had claimed, which are the
    ones safe to clear of leftover temp files. A folder whose claim can't be made is never cleared."""
    handles: list[int] = []
    free: list[str] = []
    try:
        for folder in dict.fromkeys(folders):
            name = folder_claim_name(folder)
            ctypes.set_last_error(0)
            handle = _CreateMutexW(None, False, name)
            error = ctypes.get_last_error()
            if not handle:
                write_log(f"Could not claim {folder} for this run: {ctypes.WinError(error)}", "critical")
                continue
            handles.append(handle)
            if error != _ERROR_ALREADY_EXISTS:
                free.append(folder)
        yield free
    finally:
        for handle in handles:
            _CloseHandle(handle)
