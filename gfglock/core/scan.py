# scan.py - which files a run takes from the files and folders it was given (stdlib only).
#
# Folders are walked with os.scandir, whose directory entries already carry the file type, size and
# attributes on Windows, so no extra call is made per file. Encrypting leaves system and app
# locations alone (see protected_locations), and both directions leave links and temp files out.
# The window's folder scan (services/folder_scanner.py) and the command line share this code, so a
# folder gives the same files in both.

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, fields

from gfglock.core.file_ops import ENCRYPTED_EXTS, TEMP_SUFFIX
from gfglock.utils.paths import app_folder, appdata_dir, data_dir

# Windows marks the Recycle Bin and System Volume Information both Hidden and System.
_HIDDEN_SYSTEM = stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM


@dataclass
class ScanReport:
    """What a scan left out or couldn't read."""

    folders: int = 0            # folders given that were opened
    failed_roots: int = 0       # folders given that couldn't be opened
    unreadable: int = 0         # folders inside those that couldn't be opened
    protected_folders: int = 0  # system or app folders left out (encrypt mode)
    protected_files: int = 0    # files marked System, or given from a system or app folder
    other_type: int = 0         # files given directly that belong to the other direction
    missing: int = 0            # paths given that don't exist
    error: str = ""             # why the scan stopped early, if it did

    def add(self, other: ScanReport) -> None:
        """Count another scan of the same scanning session into this report."""
        for field in fields(self):
            if field.name != "error":
                setattr(self, field.name, getattr(self, field.name) + getattr(other, field.name))
        self.error = self.error or other.error


def protected_locations() -> frozenset[str]:
    """The folders encrypting must leave alone, normalized for comparison.

    Windows, the program folders, ProgramData, the profile's AppData, and gfgLock's own data
    folders and (in the built app) the folder of its own files.
    """
    folders = [os.environ.get(name, "") for name in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")]
    profile = os.environ.get("USERPROFILE", "")
    if profile:
        folders.append(os.path.join(profile, "AppData"))
    folders += [appdata_dir(), data_dir() or "", app_folder() or ""]
    return frozenset(_key(folder) for folder in folders if folder and os.path.isabs(folder))


def accepts(name: str, include_encrypted: bool, encrypted_extensions: frozenset[str] = ENCRYPTED_EXTS) -> bool:
    """Keep encrypted files when decrypting and everything else when encrypting; never a temp file."""
    if name.lower().endswith(TEMP_SUFFIX):
        return False  # a temp file of a job that is running or was interrupted
    is_encrypted = os.path.splitext(name)[1].lower() in encrypted_extensions
    return is_encrypted == include_encrypted


def scan_paths(
    roots: Iterable[str],
    include_encrypted: bool,
    report: ScanReport,
    protected: frozenset[str] | None = None,
    is_cancelled: Callable[[], bool] = lambda: False,
    encrypted_extensions: frozenset[str] = ENCRYPTED_EXTS,
) -> Iterator[tuple[str, int]]:
    """Yield (path, size) for the files given and the files in the folders given, in that order.

    Files given directly that belong to the other direction, or (with `protected`) that are
    system files or sit in a protected location, are counted in `report` and left out.
    """
    def accept(name: str) -> bool:
        return accepts(name, include_encrypted, encrypted_extensions)

    for root in roots:
        if is_cancelled():
            return
        try:
            info = os.stat(root)
        except OSError:
            report.missing += 1  # moved or deleted since it was given; there is nothing to list
            continue
        if stat.S_ISDIR(info.st_mode):
            yield from iter_files([root], accept, is_cancelled, report, protected)
            continue
        name = os.path.basename(root)
        if name.lower().endswith(TEMP_SUFFIX):
            continue
        if not accept(name):
            report.other_type += 1
        elif protected is not None and (info.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM or _inside(root, protected)):
            report.protected_files += 1
        else:
            yield os.path.normpath(root), info.st_size


def iter_files(
    roots: Iterable[str],
    accept: Callable[[str], bool],
    is_cancelled: Callable[[], bool] = lambda: False,
    report: ScanReport | None = None,
    protected: frozenset[str] | None = None,
) -> Iterator[tuple[str, int]]:
    """Yield (path, size_bytes) for every file under the folders `roots` whose name passes `accept`.

    Directories are walked depth-first in case-insensitive name order, so files arrive in the
    order Explorer lists them. Links are skipped: symlinked and junction directories (which can
    loop back on themselves) are not followed, and linked files are left out, since encrypting a
    link would leave the file it points to readable. Folders that can't be opened are counted in
    `report`. With `protected` (encrypt mode), the folders in it, folders marked Hidden and System
    (the Recycle Bin), and files marked System are left out and counted as well.
    """
    report = report if report is not None else ScanReport()
    stack = [(os.path.normpath(root), True) for root in reversed(list(roots))]
    while stack:
        if is_cancelled():
            return
        folder, is_root = stack.pop()
        if is_root and protected is not None and _protected_root(folder, protected):
            report.protected_folders += 1
            continue
        try:
            with os.scandir(folder) as entries:
                listing = sorted(entries, key=lambda e: e.name.casefold())
        except OSError:
            if is_root:
                report.failed_roots += 1
            else:
                report.unreadable += 1
            continue
        if is_root:
            report.folders += 1
        subfolders: list[str] = []
        for entry in listing:
            if is_cancelled():
                return
            try:
                if _is_link(entry):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if protected is not None and _protected_entry(entry, protected):
                        report.protected_folders += 1
                    else:
                        subfolders.append(entry.path)
                elif accept(entry.name) and entry.is_file(follow_symlinks=False):
                    info = entry.stat(follow_symlinks=False)
                    if protected is not None and info.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM:
                        report.protected_files += 1
                    else:
                        yield entry.path, info.st_size
            except OSError:
                continue  # the entry vanished while it was listed; there is nothing to add
        stack.extend((path, False) for path in reversed(subfolders))


def _key(path: str) -> str:
    """A path in the form used to compare it with others: normalized and case-folded the Windows way."""
    return os.path.normcase(os.path.normpath(path))


def _inside(path: str, folders: frozenset[str]) -> bool:
    """True when path is one of `folders` or anywhere inside one."""
    key = _key(path)
    while key not in folders:
        parent = os.path.dirname(key)
        if parent == key:
            return False
        key = parent
    return True


def _protected_root(folder: str, protected: frozenset[str]) -> bool:
    """True when a folder given is, or is inside, a location encrypting leaves alone."""
    if _inside(folder, protected):
        return True
    try:
        return os.stat(folder).st_file_attributes & _HIDDEN_SYSTEM == _HIDDEN_SYSTEM
    except OSError:
        return False  # opening it fails next and is reported then


def _protected_entry(entry: os.DirEntry, protected: frozenset[str]) -> bool:
    """True for a subfolder encrypting leaves alone. Its parent was not one, so only it can match."""
    if _key(entry.path) in protected:
        return True
    return entry.stat(follow_symlinks=False).st_file_attributes & _HIDDEN_SYSTEM == _HIDDEN_SYSTEM


def _is_link(entry: os.DirEntry) -> bool:
    """True for a symbolic link or an NTFS junction. Cloud placeholders (OneDrive) are not links."""
    return entry.is_symlink() or entry.is_junction()
