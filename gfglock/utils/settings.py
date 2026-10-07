# settings.py - settings file load, save, and merge utilities

import copy
import json
import os
import threading
from typing import Any, Dict

from gfglock.config.defaults import ReadSizeDefaults
from gfglock.config.defaults import get_default_settings as _get_defaults
from gfglock.utils.console import safe_print
from gfglock.utils.paths import data_dir


def get_settings_file() -> str:
    """Return the path to settings.json: in the app's data folder, or next to this module from source."""
    folder = data_dir()
    if folder:
        return os.path.join(folder, "settings.json")
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
            defaults = get_default_settings()
            settings = merge_settings(defaults, drop_unknown_keys(migrate_settings(json.load(f)), defaults))
    except FileNotFoundError:
        return get_default_settings()
    except (OSError, ValueError, TypeError) as error:  # unreadable or not valid JSON
        safe_print(f"settings.json could not be read ({error}); using the defaults")
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


# Versions before 3.1.0 stored the read size as "chunk_size", defaulting to these values.
_OLD_CHUNK_DEFAULTS = {"encryption": 16 * 1024 * 1024, "decryption": 32 * 1024 * 1024}


def migrate_settings(settings: Any) -> Any:
    """Carry a read size chosen in an older version over to "read_size".

    A value that differs from the old default was picked by the user, so it is kept, moved to the
    nearest size offered now (128 MB becomes 64 MB). The old defaults and "Off" become the default,
    and so does a saved 4 MB, which the list now offers only as the default.
    """
    if not isinstance(settings, dict):
        return settings
    for section, old_default in _OLD_CHUNK_DEFAULTS.items():
        values = settings.get(section)
        if not isinstance(values, dict):
            continue
        if values.get("read_size") == ReadSizeDefaults.DEFAULT_BYTES:
            values["read_size"] = ReadSizeDefaults.DEFAULT
        if "chunk_size" not in values or "read_size" in values:
            continue
        old = values["chunk_size"]
        if isinstance(old, int) and not isinstance(old, bool) and old > 0 and old != old_default:
            nearest = min(ReadSizeDefaults.TEST_SIZES, key=lambda size: abs(size - old))
            if nearest != ReadSizeDefaults.DEFAULT_BYTES:
                values["read_size"] = nearest
    return settings


def drop_unknown_keys(settings: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Return `settings` without the keys the defaults no longer define, or with the wrong type.

    Files written by older versions keep options that were since removed (such as the old
    activity log's text wrap); dropping them keeps stale values out of the UI. A value whose type
    differs from its default (a hand-edited "cpu_threads": "abc", say) is dropped as well, so the
    default applies instead of the value breaking the app later.
    """
    if not isinstance(settings, dict):
        raise TypeError("settings must be a JSON object")
    result: Dict[str, Any] = {}
    for key, value in settings.items():
        if key not in defaults:
            continue
        if isinstance(defaults[key], dict):
            if isinstance(value, dict):
                result[key] = drop_unknown_keys(value, defaults[key])
        elif _same_type(value, defaults[key]):
            result[key] = value
    return result


def _same_type(value: Any, default: Any) -> bool:
    """True when value can stand in for default; bool and int are told apart."""
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(value, bool) and isinstance(default, bool)
    return isinstance(value, type(default))


def merge_settings(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge overrides onto defaults, recursively preserving nested structure."""
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    return result
