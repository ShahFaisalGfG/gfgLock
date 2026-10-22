# logging.py - log file management utilities

import os
import threading
from datetime import datetime
from types import TracebackType
from typing import IO

from gfglock.utils.console import safe_print
from gfglock.utils.paths import data_dir
from gfglock.utils.settings import load_settings

# A log that grows past this size moves to its backup (name + BACKUP_SUFFIX, replacing the older
# one) and starts over, so the logs never take more than about twice this much space each.
ROTATE_BYTES = 5 * 1024 * 1024
BACKUP_SUFFIX = ".1"
_SEPARATOR = "─" * 68 + "\n\n"


def get_logs_dir() -> str:
    """Return the logs directory path (in the app's data folder, or the project when run from source)."""
    folder = data_dir()
    if folder:
        logs_dir = os.path.join(folder, "logs")
    else:
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(utils_dir)), "logs")  # project root
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except OSError:
        pass  # the write that needs the folder fails next and reports it
    return logs_dir


def get_critical_log_file() -> str:
    """Return the path to the critical log file."""
    return os.path.join(get_logs_dir(), "gfglock_critical.log")


def get_general_log_file() -> str:
    """Return the path to the full activity log file."""
    return os.path.join(get_logs_dir(), "gfglock_full_activity.log")


def write_critical_log(message: str) -> bool:
    """Append a timestamped critical log entry."""
    return _append(get_critical_log_file(), _line(message))


def write_general_log(message: str) -> bool:
    """Append a timestamped general log entry."""
    return _append(get_general_log_file(), _line(message))


def write_log(message: str, level: str = "general", force: bool = False) -> bool:
    """Write one log line as the logging preferences allow; True when it was written.

    level="critical" goes to the critical log whenever logging is on; level="general" goes to the
    activity log when the level is "Everything". force=True writes the critical log even with
    logging off, for failures that happen before the preferences can be trusted (startup).
    """
    if force:
        return write_critical_log(message)
    critical_on, general_on = _enabled_logs()
    if level == "critical":
        return critical_on and write_critical_log(message)
    return general_on and write_general_log(message)


def write_session_separator() -> None:
    """Append a visual separator to log files, respecting the log-level setting."""
    critical_on, general_on = _enabled_logs()
    if critical_on:
        _append(get_critical_log_file(), _SEPARATOR)
    if general_on:
        _append(get_general_log_file(), _SEPARATOR)


def clear_logs() -> bool:
    """Empty both logs and delete their backups. Returns True if all of it worked."""
    ok = True
    for log_file in (get_critical_log_file(), get_general_log_file()):
        try:
            if os.path.exists(log_file):
                open(log_file, "w", encoding="utf-8").close()
            if os.path.exists(log_file + BACKUP_SUFFIX):
                os.remove(log_file + BACKUP_SUFFIX)
        except OSError as error:
            safe_print(f"Could not clear {log_file}: {error}")
            ok = False
    return ok


class RunLog:
    """One run's log lines, written from the worker through handles opened once per run.

    The logging preferences are read once, when the run log is created. Every line is flushed as
    it is written, so a crash keeps the lines before it. Safe to use from several threads.
    """

    def __init__(self) -> None:
        critical_on, general_on = _enabled_logs()
        self._lock = threading.Lock()
        self._critical = _LogFile(get_critical_log_file()) if critical_on else None
        self._general = _LogFile(get_general_log_file()) if general_on else None

    def write(self, message: str, critical: bool = False) -> None:
        """Log one line in the activity log, and in the critical log too when critical."""
        if self._general is None and (self._critical is None or not critical):
            return
        line = _line(message)
        with self._lock:
            if self._general is not None:
                self._general.write(line)
            if critical and self._critical is not None:
                self._critical.write(line)

    def close(self) -> None:
        """Close the run's log files."""
        with self._lock:
            for log_file in (self._general, self._critical):
                if log_file is not None:
                    log_file.close()

    def __enter__(self) -> "RunLog":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        self.close()


class _LogFile:
    """An append handle to one log, opened on the first line and rotated when the log fills up."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._handle: IO[str] | None = None
        self._broken = False

    def write(self, line: str) -> None:
        """Append and flush one line; after a write error the rest of the run's lines are dropped."""
        if self._broken:
            return
        try:
            if self._handle is None:
                _rotate_if_full(self._path)
                self._handle = _open(self._path)
            self._handle.write(line)
            self._handle.flush()
            if self._handle.tell() >= ROTATE_BYTES:
                self.close()  # the next line rotates the full log and opens a new one
        except OSError as error:
            safe_print(f"Could not write to {self._path}: {error}")
            self._broken = True
            self.close()

    def close(self) -> None:
        """Close the handle, if open."""
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            handle.close()
        except OSError as error:
            safe_print(f"Could not close {self._path}: {error}")


def _enabled_logs() -> tuple[bool, bool]:
    """(critical log on, activity log on) as the logging preferences say; both off if unreadable."""
    try:
        advanced = load_settings().get("advanced", {})
    except Exception as error:  # logging runs inside error handlers, so it must never raise
        safe_print(f"Could not read the logging preferences: {error}")
        return False, False
    enabled = bool(advanced.get("enable_logs", False))
    return enabled, enabled and advanced.get("log_level", "critical") == "all"


def _line(message: str) -> str:
    """One timestamped log line."""
    return f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n"


def _open(path: str) -> IO[str]:
    """Open a log for appending; odd characters in file names are escaped, never an error."""
    return open(path, "a", encoding="utf-8", errors="backslashreplace")


def _append(path: str, text: str) -> bool:
    """Append text to the log at path, rotating the log first when it is full."""
    try:
        _rotate_if_full(path)
        with _open(path) as handle:
            handle.write(text)
        return True
    except OSError as error:
        safe_print(f"Could not write to {path}: {error}")
        return False


def _rotate_if_full(path: str) -> None:
    """Move a log past ROTATE_BYTES to its backup so it starts over."""
    try:
        if os.path.getsize(path) < ROTATE_BYTES:
            return
        os.replace(path, path + BACKUP_SUFFIX)
    except FileNotFoundError:
        return
    except OSError as error:  # held open by a run in the other tab; a later write rotates it
        safe_print(f"Could not rotate {path}: {error}")
