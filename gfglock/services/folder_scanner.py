"""Check and size the files and folders added to a list without blocking the GUI thread.

Folders are walked with os.scandir, whose directory entries already carry the file type, size and
attributes on Windows, so no extra call is made per file. Files added directly are checked here
too, so even a long Explorer selection never touches the disk on the GUI thread. Rows are handed
to the model in batches sized by time (not by count), so a folder with tens of thousands of files
fills the list smoothly while the window keeps repainting. Files and folders added while a scan
runs join it. In encrypt mode, system and app locations are left out (see protected_locations).
A scan can be cancelled at any time: Stop, clearing the list, or app shutdown.
"""

from __future__ import annotations

import itertools
import os
import stat
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gfglock.core.file_ops import TEMP_SUFFIX
from gfglock.utils.logging import write_log
from gfglock.utils.paths import app_folder, appdata_dir, data_dir

# Rows are flushed to the GUI at most this often, or sooner once this many are waiting.
FLUSH_INTERVAL_S = 0.1
MAX_BATCH = 2000
# Windows marks the Recycle Bin and System Volume Information both Hidden and System.
_HIDDEN_SYSTEM = stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM
_scan_ids = itertools.count(1)


@dataclass
class ScanReport:
    """What a scan left out or couldn't read, sent once when it ends."""

    folders: int = 0            # folders added to the list that were opened
    failed_roots: int = 0       # folders added to the list that couldn't be opened
    unreadable: int = 0         # folders inside those that couldn't be opened
    protected_folders: int = 0  # system or app folders left out (encrypt mode)
    protected_files: int = 0    # files marked System, or added from a system or app folder
    other_type: int = 0         # files added directly that belong on the other tab
    error: str = ""             # why the scan stopped early, if it did

    def add(self, other: ScanReport) -> None:
        """Count another scan of the same scanning session into this report."""
        self.folders += other.folders
        self.failed_roots += other.failed_roots
        self.unreadable += other.unreadable
        self.protected_folders += other.protected_folders
        self.protected_files += other.protected_files
        self.other_type += other.other_type
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
    """True when a folder added to the list is, or is inside, a location encrypting leaves alone."""
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


class FolderScanSignals(QObject):
    """Signals of one scan; each carries the scan's id so the receiver can tell scans apart."""

    batch_found = Signal(int, list)  # (scan id, list of (path, size))
    finished = Signal(int, object)   # (scan id, ScanReport)


class FolderScanWorker(QRunnable):
    """Check the files and walk the folders added to one list, reporting the rows in batches."""

    def __init__(
        self,
        roots: Iterable[str],
        encrypted_extensions: frozenset[str],
        include_encrypted: bool,
    ) -> None:
        super().__init__()
        # Left to auto-delete: with that off, PySide's pool keeps a reference to every scan it ran.
        self.scan_id = next(_scan_ids)
        self.encrypted_extensions = encrypted_extensions
        self.include_encrypted = include_encrypted
        self._roots = list(roots)
        self._lock = threading.Lock()
        self._closed = False
        self._cancel = threading.Event()
        self.signals = FolderScanSignals()

    def add_roots(self, roots: Iterable[str]) -> bool:
        """Queue more files and folders for this scan; False once it has ended or was cancelled."""
        with self._lock:
            if self._closed or self._cancel.is_set():
                return False
            self._roots.extend(roots)
            return True

    def cancel(self) -> None:
        """Stop at the next directory entry and send no more batches."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        """True once cancel() has been called."""
        return self._cancel.is_set()

    def _accept(self, name: str) -> bool:
        """Keep encrypted files in decrypt mode and everything else in encrypt mode."""
        if name.lower().endswith(TEMP_SUFFIX):
            return False  # a temp file of a job that is running or was interrupted
        is_encrypted = os.path.splitext(name)[1].lower() in self.encrypted_extensions
        return is_encrypted == self.include_encrypted

    @Slot()
    def run(self) -> None:
        """Scan the queued roots, including ones added meanwhile, then report once."""
        report = ScanReport()
        batch: list[tuple[str, int]] = []
        last_flush = time.monotonic()
        try:
            protected = None if self.include_encrypted else protected_locations()
            while not self._cancel.is_set():
                roots = self._take_roots()
                if not roots:
                    break
                for item in self._scan(roots, report, protected):
                    batch.append(item)
                    now = time.monotonic()
                    if len(batch) >= MAX_BATCH or now - last_flush >= FLUSH_INTERVAL_S:
                        self._flush(batch)
                        batch, last_flush = [], now
        except Exception as error:  # the scan must still end, or the list would stay "scanning"
            report.error = str(error)
            write_log(f"Folder scan stopped: {error}", "critical")
        finally:
            with self._lock:
                self._closed = True
            try:
                if batch:
                    self._flush(batch)
                self.signals.finished.emit(self.scan_id, report)
            except RuntimeError:
                pass  # the app is shutting down and the signal object is already gone

    def _take_roots(self) -> list[str]:
        """The roots queued so far. When none are left the scan closes, so later ones start a new scan."""
        with self._lock:
            roots, self._roots = self._roots, []
            self._closed = not roots
            return roots

    def _scan(self, roots: list[str], report: ScanReport,
              protected: frozenset[str] | None) -> Iterator[tuple[str, int]]:
        """Yield the rows for these files and folders, in the order they were added."""
        for root in roots:
            if self._cancel.is_set():
                return
            try:
                info = os.stat(root)
            except OSError:
                continue  # moved or deleted since it was added; there is nothing to list
            if stat.S_ISDIR(info.st_mode):
                yield from iter_files([root], self._accept, self._cancel.is_set, report, protected)
            else:
                row = self._check_file(root, info, report, protected)
                if row is not None:
                    yield row

    def _check_file(self, path: str, info: os.stat_result, report: ScanReport,
                    protected: frozenset[str] | None) -> tuple[str, int] | None:
        """The row for a file added directly, or None when it is left out (and counted)."""
        name = os.path.basename(path)
        if name.lower().endswith(TEMP_SUFFIX):
            return None
        if not self._accept(name):
            report.other_type += 1
            return None
        if protected is not None and (info.st_file_attributes & stat.FILE_ATTRIBUTE_SYSTEM
                                      or _inside(path, protected)):
            report.protected_files += 1
            return None
        return os.path.normpath(path), info.st_size

    def _flush(self, batch: list[tuple[str, int]]) -> None:
        """Send one batch, unless the scan was cancelled."""
        if not self._cancel.is_set():
            self.signals.batch_found.emit(self.scan_id, batch)
