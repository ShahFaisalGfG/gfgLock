# settings.py — settings file load, save, and merge utilities

import json
import os
import sys
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


def load_settings() -> Dict[str, Any]:
    """Load settings from settings.json, merging with defaults for any missing keys."""
    path = get_settings_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
            return merge_settings(get_default_settings(), user_settings)
        except Exception:
            pass
    return get_default_settings()


def save_settings(settings: Dict[str, Any]) -> bool:
    """Persist settings to settings.json. Returns True on success."""
    try:
        with open(get_settings_file(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception:
        return False


def merge_settings(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge overrides onto defaults, preserving nested structure."""
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result
