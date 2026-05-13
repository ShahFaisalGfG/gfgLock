# logging.py — log file management utilities

import os
import sys
from datetime import datetime

from gfglock.utils.settings import load_settings


def get_logs_dir() -> str:
    """Return the logs directory path, creating it if needed."""
    try:
        if getattr(sys, "frozen", False):
            appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
            logs_dir = os.path.join(appdata, "gfgLock", "logs")
            os.makedirs(logs_dir, exist_ok=True)
            return logs_dir
    except Exception:
        pass
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.dirname(os.path.dirname(utils_dir))  # project root
    logs_dir = os.path.join(pkg_dir, "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        pass
    return logs_dir


def get_critical_log_file() -> str:
    """Return the path to the critical log file."""
    return os.path.join(get_logs_dir(), "gfglock_critical.log")


def get_general_log_file() -> str:
    """Return the path to the full activity log file."""
    return os.path.join(get_logs_dir(), "gfglock_full_activity.log")


def write_critical_log(message: str) -> bool:
    """Append a timestamped critical log entry."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(get_critical_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        return True
    except Exception:
        return False


def write_general_log(message: str) -> bool:
    """Append a timestamped general log entry."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(get_general_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        return True
    except Exception:
        return False


def write_log(message: str, level: str = "general") -> bool:
    """Write a log entry to disk, respecting the enabled flag and log-level setting.

    level='critical' → always written to the critical log (when logging is on).
    level='general'  → written to the general log only when log_level is 'all'.
    """
    try:
        settings = load_settings()
        if not settings.get("advanced", {}).get("enable_logs", False):
            return False
        if level == "critical":
            return write_critical_log(message)
        log_level = settings.get("advanced", {}).get("log_level", "critical")
        if log_level == "all":
            return write_general_log(message)
        return False
    except Exception:
        return False


def write_session_separator() -> None:
    """Append a visual session separator line to both log files (no timestamp)."""
    try:
        settings = load_settings()
        if not settings.get("advanced", {}).get("enable_logs", False):
            return
        sep = "─" * 68
        for log_file in [get_critical_log_file(), get_general_log_file()]:
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"{sep}\n\n")
            except Exception:
                pass
    except Exception:
        pass


def clear_logs() -> bool:
    """Clear all log files. Returns True if both cleared successfully."""
    try:
        for log_file in [get_critical_log_file(), get_general_log_file()]:
            if os.path.exists(log_file):
                open(log_file, "w", encoding="utf-8").close()
        return True
    except Exception:
        return False
