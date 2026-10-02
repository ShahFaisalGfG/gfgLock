# settings.py - settings file load, save, and merge utilities

import copy
import json
import os
import sys
import threading
from typing import Any, Dict

from gfglock.config.defaults import get_default_settings as _get_defaults


def get_settings_file() -> str:
    """Return the path to settings.json, creating the directory if needed."""
    try:
        if getattr(sys, "frozen", False):
            appdata  = os.environ.get("APPDATA") or os.path.expanduser("~")
            data_dir = os.path.join(appdata, "gfgLock")
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "settings.json")
    except Exception:
        pass
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(utils_dir, "settings.json")


def get_default_settings() -> Dict[str, Any]:
    """Return the complete default settings dictionary."""
    return _get_defaults()


# Parsed settings keyed by the file's (path, mtime, size). write_log() asks for settings on every
# log line, which during a batch of thousands of files meant thousands of JSON reads.
_cache_lock = threading.Lock()
_cache: tuple[tuple[str, int, int], Dict[str, Any]] | None = None


def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json, merging with defaults for any missing keys.

    Returns a fresh copy each time; the parsed file is reused until it changes on disk.
    """
    global _cache
    path = get_settings_file()
    try:
        stat = os.stat(path)
    except OSError:
        return get_default_settings()
    key = (path, stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if _cache is not None and _cache[0] == key:
            return copy.deepcopy(_cache[1])
    try:
        with open(path, "r", encoding="utf-8") as f:
            settings = merge_settings(get_default_settings(), json.load(f))
    except Exception:
        return get_default_settings()
    with _cache_lock:
        _cache = (key, settings)
    return copy.deepcopy(settings)


def save_settings(settings: Dict[str, Any]) -> bool:
    """Persist settings to settings.json atomically. Returns True on success.

    Writes a temp file next to it and swaps it in, so a crash mid-write can't leave a
    truncated settings.json behind.
    """
    global _cache
    path = get_settings_file()
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        os.replace(tmp_path, path)
        # File times can be coarser than two quick saves, so don't rely on mtime alone here.
        with _cache_lock:
            _cache = None
        return True
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


def merge_settings(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge overrides onto defaults, recursively preserving nested structure."""
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    return result
