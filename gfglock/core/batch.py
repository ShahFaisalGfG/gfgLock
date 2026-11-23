# batch.py - one encrypt, decrypt, or check run over a list of files (stdlib only, plus the engine).
#
# The window (services/worker.py wraps a run in a QRunnable) and the command line share this run
# loop, the options it takes from the saved settings, and the summary it ends with, so both do the
# same thing to the same files. A run works on `threads` files at a time, lowers the read size when
# the threads' buffers wouldn't fit in a share of the free memory, clears the temp files an
# interrupted run left in folders no other run is using (core/locks.py), and stops by itself with
# one message when a drive fills up.

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from gfglock.config.defaults import (
    AlgorithmDefaults,
    DecryptionDefaults,
    EncryptionDefaults,
    PerformanceDefaults,
    ReadSizeDefaults,
    thread_limit,
)
from gfglock.core import file_ops, reasons
from gfglock.core.file_ops import OUTCOME_DONE, OUTCOME_FAILED, OUTCOME_SKIPPED, FileResult
from gfglock.core.format_v2 import KeyRing
from gfglock.core.locks import claim_folders
from gfglock.utils.helpers import format_bytes
from gfglock.utils.logging import RunLog, write_log

MODE_ENCRYPT = "encrypt"
MODE_DECRYPT = "decrypt"
MODE_VERIFY = "verify"
MODES = (MODE_ENCRYPT, MODE_DECRYPT, MODE_VERIFY)
# What a finished file was, by mode: "3 of 4 files encrypted".
DONE_WORDS = {MODE_ENCRYPT: "encrypted", MODE_DECRYPT: "decrypted", MODE_VERIFY: "checked"}
# The settings section that holds each mode's files at a time, read size, and where results go.
# Checking reads files the way decrypting does, so it uses the decrypting choices.
_SECTIONS = {MODE_ENCRYPT: ("encryption", EncryptionDefaults), MODE_DECRYPT: ("decryption", DecryptionDefaults),
             MODE_VERIFY: ("decryption", DecryptionDefaults)}

# Each thread holds about this many read-size buffers at once (the engines keep 4 blocks in flight,
# each with an input and an output buffer). The read size is lowered so that every thread's buffers
# together stay within 1/MEMORY_SHARE of the free physical memory.
BLOCKS_PER_THREAD = 8
MEMORY_SHARE = 4
MIN_READ_SIZE = 1024 * 1024
# The run's byte progress is sent at most this often; a run of many small files would otherwise
# report once per file to a bar that redraws ten times a second.
PROGRESS_INTERVAL_S = 0.05
# Time remaining is guessed once the run has gone this long, so the first burst of cached reads
# doesn't promise too much.
ETA_AFTER_S = 2.0


@dataclass(frozen=True)
class RunOptions:
    """How a run treats its files."""

    mode: str = MODE_ENCRYPT
    algorithm: str = "gcm"         # the engine's cipher code, used when encrypting
    hide_names: bool = False       # encrypted files get a random name; the original one is restored on decrypt
    threads: int = 1               # files worked on at once
    read_size: int = 0             # bytes read at a time; 0 lets the engine choose
    keep_originals: bool = False   # leave the files that were read in place
    output_dir: str = ""           # where results go; "" puts each next to its source

    @property
    def replaces(self) -> bool:
        """True when each source is deleted once its result is safely written."""
        return self.mode != MODE_VERIFY and not self.keep_originals


def cipher_choice(choice: str) -> tuple[str, str]:
    """The settings code and engine cipher to encrypt with. Anything else, including the
    decrypt-only CFB, means the default algorithm."""
    cipher = AlgorithmDefaults.CIPHERS.get(choice, "")
    if cipher not in file_ops.ENCRYPT_ALGORITHMS:
        choice = AlgorithmDefaults.DEFAULT_ALGORITHM
        cipher = AlgorithmDefaults.CIPHERS[choice]
    return choice, cipher


def clamp_threads(threads: int, settings: dict[str, Any]) -> int:
    """Limit threads to the CPU, keeping one free when the preference asks for it."""
    clamp = settings.get("advanced", {}).get("clamp_cpu_threads", PerformanceDefaults.CLAMP_CPU_THREADS)
    return max(1, min(int(threads), thread_limit(clamp)))


def options_from_settings(mode: str, settings: dict[str, Any], *, algorithm: str = "",
                          hide_names: bool | None = None, threads: int | None = None,
                          keep_originals: bool | None = None, output_dir: str | None = None) -> RunOptions:
    """The run's options from the saved settings, with each value given here in place of the saved one."""
    section_name, defaults = _SECTIONS[mode]
    section = settings.get(section_name, {})
    chosen_threads = threads if threads is not None else int(section.get("cpu_threads", defaults.DEFAULT_THREADS))
    _, cipher = cipher_choice(algorithm or settings.get("advanced", {}).get("encryption_mode", ""))
    return RunOptions(
        mode=mode,
        algorithm=cipher,
        hide_names=(bool(settings.get("encryption", {}).get("encrypt_filenames", False))
                    if hide_names is None else hide_names) and mode == MODE_ENCRYPT,
        threads=clamp_threads(chosen_threads, settings),
        read_size=max(0, int(section.get("read_size", ReadSizeDefaults.DEFAULT) or 0)),
        keep_originals=bool(section.get("keep_originals", False)) if keep_originals is None else keep_originals,
        output_dir=(str(section.get("output_dir", "")) if output_dir is None else output_dir)
        if mode != MODE_VERIFY else "",
    )


# ── Memory and disk space ─────────────────────────────────────────────────────

class _MemoryStatus(ctypes.Structure):
    """MEMORYSTATUSEX, as GlobalMemoryStatusEx fills it in."""

    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def available_memory() -> int | None:
    """Free physical memory in bytes, or None when Windows can't report it."""
    if sys.platform != "win32":
        return None
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys)


def capped_read_size(read_size: int, threads: int, available: int | None) -> int:
    """The read size to run with: the chosen one (0 = the default), lowered when the threads'
    blocks would take more than their share of the free memory, but never below 1 MiB."""
    if available is None:
        return read_size
    limit = available // MEMORY_SHARE // (max(1, threads) * BLOCKS_PER_THREAD)
    limit = max(MIN_READ_SIZE, limit // MIN_READ_SIZE * MIN_READ_SIZE)
    return read_size if (read_size or ReadSizeDefaults.DEFAULT_BYTES) <= limit else limit


@dataclass(frozen=True)
class Shortage:
    """A drive without room for a run's results."""

    drive: str
    needed: int
    free: int

    def text(self) -> str:
        """'Drive D: needs 3.2 GB free for this run but has 1.1 GB. Free up 2.1 GB and try again.'"""
        return (f"Drive {self.drive} needs {format_bytes(self.needed, strip_zeros=True)} free for this run but has "
                f"{format_bytes(self.free, strip_zeros=True)}. Free up "
                f"{format_bytes(self.needed - self.free, strip_zeros=True)} and try again.")


def space_shortages(files: Iterable[tuple[str, int]], options: RunOptions) -> list[Shortage]:
    """The drives that lack the room a run's results take, checked before it starts.

    A result whose source is deleted right after it frees that space again, so a drive needs room
    for the largest results being written at once; results kept beside their sources, or written
    to another drive, add up.
    """
    if options.mode == MODE_VERIFY:
        return []
    encrypting = options.mode == MODE_ENCRYPT
    kept: Counter[str] = Counter()
    passing: dict[str, list[int]] = {}
    places: dict[str, str] = {}
    for path, size in files:
        folder = file_ops.output_folder(path, options.output_dir)
        drive = _drive(folder)
        places.setdefault(drive, folder)
        output = file_ops.output_size(size, encrypting)
        if options.keep_originals or drive != _drive(path):
            kept[drive] += output
        else:
            passing.setdefault(drive, []).append(output)
    shortages = []
    for drive, folder in places.items():
        largest = sorted(passing.get(drive, []), reverse=True)[:max(1, options.threads)]
        needed = kept[drive] + sum(largest) + file_ops.SPACE_MARGIN
        free = _free_space(folder)
        if free is not None and free < needed:
            shortages.append(Shortage(drive, needed, free))
    return shortages


def _drive(path: str) -> str:
    """The drive or network share of a path: 'D:' or '\\\\server\\share'."""
    return os.path.splitdrive(os.path.abspath(path))[0].upper() or os.path.abspath(path)


def _free_space(folder: str) -> int | None:
    """Free bytes on the drive of folder, or of its nearest existing parent; None when unreadable."""
    while True:
        try:
            return shutil.disk_usage(folder).free
        except OSError:
            parent = os.path.dirname(folder)
            if parent == folder:
                return None
            folder = parent


# ── The run ───────────────────────────────────────────────────────────────────

class RunListener:
    """What a run reports, from its own threads; each method does nothing until overridden."""

    def progress(self, done: int, total: int, eta: float) -> None:
        """Bytes read so far of the run's total, and seconds left (-1 while unknown)."""

    def file_started(self, path: str) -> None:
        """A file begins."""

    def file_progress(self, path: str, fraction: float) -> None:
        """A file is under way: 0-1, at most once per whole percent."""

    def file_result(self, path: str, result: FileResult) -> None:
        """A file ended, once per file."""

    def temps_removed(self, count: int) -> None:
        """Temp files an interrupted run left were deleted at the start."""

    def error(self, message: str) -> None:
        """The run stopped early for a reason outside the files' own jobs."""


@dataclass
class RunResult:
    """How a run ended."""

    mode: str
    total: int
    elapsed: float = 0.0
    done: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: int = 0                # files a stop ended unchanged; they run again next time
    cancelled: bool = False         # stopped before every file ended
    halt: str = ""                  # why the run stopped by itself ("" unless a drive filled up)
    error: str = ""                 # a failure outside the files' own jobs
    failures: Counter[str] = field(default_factory=Counter)  # failure categories and how many
    outputs: list[str] = field(default_factory=list)          # files written

    @property
    def ok(self) -> bool:
        """True when every file was done or skipped on purpose and the run wasn't stopped."""
        return not (self.failed or self.cancelled or self.error)


class BatchRun:
    """Encrypt, decrypt, or check a list of files on `threads` threads, reporting to a listener."""

    def __init__(self, paths: Iterable[str], keys: KeyRing, options: RunOptions,
                 listener: RunListener | None = None) -> None:
        self.paths = list(paths)
        self.keys = keys
        self.options = options
        self.listener = listener or RunListener()
        self._cancelled = False
        self._stop = file_ops.new_stop_token()
        self._sizes: dict[str, int] = {}
        self._read: dict[str, int] = {}
        self.total_bytes = 1
        self._done_bytes = 0
        self._progress_sent = 0.0
        self._started = 0.0
        self._lock = threading.Lock()
        self._result = RunResult(options.mode, len(self.paths))

    @property
    def cancelled(self) -> bool:
        """True once cancel() was called or the run stopped by itself."""
        return self._cancelled

    def cancel(self) -> None:
        """Stop the run: no new files start, and the files in progress stop and stay unchanged."""
        self._cancelled = True
        self._stop.cancel()

    def run(self) -> RunResult:
        """Process every file and return how the run ended."""
        start = time.monotonic()
        result = self._result
        try:
            with RunLog() as log, claim_folders(self._temp_folders()) as free_folders:
                self._sweep(free_folders, log)
                read_size = self._prepare(log)
                self._process(read_size, log)
        except Exception as error:  # a failure outside the files' own jobs must still end the run
            write_log(f"Operation stopped unexpectedly: {error}", "critical")
            result.error = f"The run stopped unexpectedly: {error}"
            self.listener.error(result.error)
        result.elapsed = time.monotonic() - start
        result.cancelled = self._cancelled and result.done + result.failed + result.skipped < result.total
        return result

    def _temp_folders(self) -> list[str]:
        """The folders the run writes temp files in; checking writes none."""
        if self.options.mode == MODE_VERIFY:
            return []
        if self.options.output_dir:
            return [os.path.abspath(self.options.output_dir)]
        return sorted({os.path.dirname(os.path.abspath(path)) for path in self.paths})

    def _sweep(self, folders: list[str], log: RunLog) -> None:
        """Clear the given folders of temp files an interrupted run left behind. It runs first, so a
        run that starts meanwhile, sees the folders claimed, and leaves them alone has written nothing."""
        removed = file_ops.remove_stale_temps(folders)
        if removed:
            log.write(f"Removed {removed} temporary {'file' if removed == 1 else 'files'} left by an earlier run")
            self.listener.temps_removed(removed)

    def _prepare(self, log: RunLog) -> int:
        """Size the files and pick the read size. Returns the read size."""
        for path in self.paths:
            if self._cancelled:  # sizing thousands of files on a network share takes a while
                break
            try:
                self._sizes[path] = os.path.getsize(path)
            except OSError:
                self._sizes[path] = 0  # missing or unreadable: the file's own result says why
        self.total_bytes = max(sum(self._sizes.values()), 1)
        read_size = capped_read_size(self.options.read_size, self.options.threads, available_memory())
        if read_size != self.options.read_size:
            log.write(f"Read size lowered to {read_size // MIN_READ_SIZE} MB to fit in the free memory")
        return read_size

    def _process(self, read_size: int, log: RunLog) -> None:
        """Run the files on `threads` threads. Each thread takes the next file as soon as it is free,
        so a run of many small files never waits on a hand-off between threads."""
        queue = iter(self.paths)
        queue_lock = threading.Lock()
        self._started = time.monotonic()

        def next_path() -> str | None:
            with queue_lock:
                return None if self._cancelled else next(queue, None)

        def work() -> None:
            while (path := next_path()) is not None:
                self.listener.file_started(path)
                self._process_file(path, read_size, log)

        threads = max(1, self.options.threads)
        with ThreadPoolExecutor(max_workers=threads) as executor:
            runners = [executor.submit(work) for _ in range(min(threads, len(self.paths)))]
        for runner in runners:
            runner.result()  # re-raises an error outside the files' own jobs, which ends the run
        with self._lock:
            done_bytes = self._done_bytes
        self.listener.progress(done_bytes, self.total_bytes, 0.0)

    def _process_file(self, path: str, read_size: int, log: RunLog) -> None:
        """Encrypt, decrypt, or check one file, then log and report its result."""
        try:
            result = self._build_job(path, read_size)()
        except Exception as error:  # a crash in one file must not stop the others
            result = FileResult(False, f"Critical error while processing {path}: {error}", OUTCOME_FAILED,
                                reasons.text(reasons.UNKNOWN), category=reasons.UNKNOWN)
        self._count(path, result)
        log.write(self._log_message(result), critical=result.outcome == OUTCOME_FAILED)
        self._add_progress(path, self._sizes.get(path, 0))
        self.listener.file_result(path, result)

    def _count(self, path: str, result: FileResult) -> None:
        """Add a file's result to the run's counts; a full drive stops the rest of the run."""
        tally = self._result
        with self._lock:
            if result.outcome == OUTCOME_DONE:
                tally.done += 1
                if result.output:
                    tally.outputs.append(result.output)
            elif result.outcome == OUTCOME_SKIPPED and result.category == reasons.STOPPED:
                tally.stopped += 1
            elif result.outcome == OUTCOME_SKIPPED:
                tally.skipped += 1
            else:
                tally.failed += 1
                tally.failures[result.category or reasons.UNKNOWN] += 1
            full = result.category == reasons.DISK_FULL and not tally.halt
            if full:
                tally.halt = f"the drive {_drive(file_ops.output_folder(path, self.options.output_dir))} is full"
        if full:
            self.cancel()  # every later file would fail the same way

    def _log_message(self, result: FileResult) -> str:
        """The result's log line. With hidden names, an encrypted file is logged by its new name only,
        so the log never pairs the hidden name with the original one."""
        if self.options.hide_names and self.options.mode == MODE_ENCRYPT and result.outcome == OUTCOME_DONE:
            return f"Encrypted: {result.output}"
        return result[1]

    def _add_progress(self, path: str, read: int) -> None:
        """Record that `read` bytes of path have been read in all, and report the run's progress
        unless it was reported less than PROGRESS_INTERVAL_S ago."""
        with self._lock:
            read = min(read, self._sizes.get(path, 0))
            previous = self._read.get(path, 0)
            if read <= previous:
                return
            self._read[path] = read
            self._done_bytes += read - previous
            now = time.monotonic()
            if now - self._progress_sent < PROGRESS_INTERVAL_S:
                return
            self._progress_sent = now
            done = self._done_bytes
        self.listener.progress(done, self.total_bytes, time_left(done, self.total_bytes, now - self._started))

    def _make_progress_callback(self, path: str) -> Callable[[float], None]:
        """A callback for the engine's progress (bytes read since its last call) that also reports
        the file's own percent, at most once per whole percent. 0% is shown when the file starts and
        100% when its result arrives, so neither is sent from here."""
        size = self._sizes.get(path, 0)
        state = {"read": 0, "percent": 0}

        def callback(amount: float) -> None:
            state["read"] += int(amount)
            self._add_progress(path, state["read"])
            percent = min(100, state["read"] * 100 // size) if size else 100
            if percent != state["percent"] and percent < 100:
                state["percent"] = percent
                self.listener.file_progress(path, percent / 100.0)
        return callback

    def _build_job(self, path: str, read_size: int) -> Callable[[], FileResult]:
        """Return the callable that processes one file."""
        options = self.options
        progress = self._make_progress_callback(path)
        if options.mode == MODE_ENCRYPT:
            return partial(file_ops.encrypt_file, path, self.keys, options.algorithm, encrypt_name=options.hide_names,
                           read_size=read_size, progress=progress, stop=self._stop,
                           keep_original=options.keep_originals, output_dir=options.output_dir)
        if options.mode == MODE_DECRYPT:
            return partial(file_ops.decrypt_file, path, self.keys, read_size=read_size, progress=progress,
                           stop=self._stop, keep_original=options.keep_originals, output_dir=options.output_dir)
        return partial(file_ops.verify_file, path, self.keys, read_size=read_size, progress=progress, stop=self._stop)


# ── Words for the result ──────────────────────────────────────────────────────

def time_left(done: int, total: int, elapsed: float) -> float:
    """Seconds left at the run's average speed so far, or -1 while it is too early to tell."""
    if elapsed < ETA_AFTER_S or done <= 0 or total <= done:
        return -1.0
    return (total - done) * elapsed / done


def format_duration(seconds: float) -> str:
    """'under 0.1 s', '2.1 s', '3 min 5 s', or '1 h 2 min'."""
    if seconds < 0.1:
        return "under 0.1 s"
    if round(seconds, 1) < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min" + (f" {secs} s" if secs else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h" + (f" {minutes} min" if minutes else "")


def format_time_left(seconds: float) -> str:
    """'about 40 s left', 'about 3 min left', 'about 1 h 5 min left', or '' while unknown."""
    if seconds < 0:
        return ""
    if seconds < 60:
        return f"about {max(5, round(seconds / 5) * 5)} s left"
    if seconds < 3600:
        return f"about {round(seconds / 60)} min left"
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"about {hours} h" + (f" {minutes} min" if minutes else "") + " left"


def plural(count: int, noun: str) -> str:
    """'1 file', '3 files'."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def grouped_failures(failures: Counter[str]) -> str:
    """'6 wrong password, 3 in use': the failures by reason, most common first."""
    return ", ".join(f"{count} {reasons.label(category)}" for category, count in failures.most_common())


def wrong_password_only(result: RunResult) -> bool:
    """True when nothing was opened and every failure was the password (or a damaged file)."""
    return (result.mode != MODE_ENCRYPT and result.failed > 0 and result.done == 0
            and set(result.failures) == {reasons.WRONG_PASSWORD})


def summarize(result: RunResult, again: str) -> str:
    """One or two sentences on how the run went. `again` says how to run it once more, such as
    'press Encrypt' or 'run the command'.

    'All 4 files encrypted in 2.1 s.', '3 of 12 files decrypted. 9 failed: 6 wrong password, 3 in use.'
    """
    verb = DONE_WORDS[result.mode]
    total = plural(result.total, "file")
    if result.halt:
        return (f"Stopped because {result.halt}: {result.done} of {total} {verb}, and the rest were not "
                f"changed. Free up space, then {again} again.")
    if result.error:
        return f"{result.error}. {result.done} of {total} {verb}."
    if wrong_password_only(result):
        return "Wrong password. Nothing was changed." if result.mode == MODE_DECRYPT else "Wrong password."
    skipped = f", {result.skipped} skipped" if result.skipped else ""
    failed = f" {result.failed} failed: {grouped_failures(result.failures)}." if result.failed else ""
    if result.cancelled:
        return f"Stopped: {result.done} of {total} {verb}{skipped}.{failed} The rest were not changed."
    if result.failed:
        return f"{result.done} of {total} {verb}{skipped}.{failed}"
    timing = format_duration(result.elapsed)
    if result.done == result.total:
        files = f"All {total}" if result.total > 1 else total
        if result.mode == MODE_VERIFY:
            intact = "they're" if result.total > 1 else "it's"
            return f"{files} checked in {timing}: the password is right and {intact} intact."
        return f"{files} {verb} in {timing}."
    return f"{result.done} of {total} {verb} in {timing}{skipped}."


def run_folders(outputs: Sequence[str]) -> list[str]:
    """The folders a run wrote into, in the order it first wrote to each."""
    return list(dict.fromkeys(os.path.dirname(path) for path in outputs))
