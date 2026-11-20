# install_choices.py - the connections the installer let the user turn off, applied to their settings
#
# The installers write their choices under HKLM (all users) or HKCU (one user) in
# Software\gfgLock\Install, each as 1 (on) or 0 (off). A choice turns its connection off when it is
# newly 0 since this user's settings last saw it: a silent in-app update keeps the earlier choices,
# so it never undoes what was changed in Preferences, and the installer never turns a connection
# back on.

from __future__ import annotations

import sys
from typing import Any

from gfglock.utils.logging import write_log
from gfglock.utils.paths import is_portable
from gfglock.utils.settings import load_settings, save_settings

if sys.platform == "win32":
    import winreg

CHOICES_KEY = r"Software\gfgLock\Install"
# Each registry value and the setting it turns off.
CHOICES = {
    "UpdateChecks": ("advanced", "auto_check_updates"),
}


def read_choices(key: str = CHOICES_KEY) -> dict[str, int]:
    """The installer's choices on this PC (a per-user install's first), or {} when there are none."""
    if sys.platform != "win32":
        return {}
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as handle:
                return {name: int(value) for name in CHOICES if (value := _value(handle, name)) is not None}
        except OSError:
            continue
    return {}


def _value(handle: Any, name: str) -> int | None:
    try:
        value, kind = winreg.QueryValueEx(handle, name)
    except OSError:
        return None
    return value if kind == winreg.REG_DWORD and value in (0, 1) else None


def apply_choices(settings: dict[str, Any], choices: dict[str, int]) -> bool:
    """Turn off each connection whose choice is newly off, and note the choices; True when anything changed."""
    seen = _parse(settings["install"]["connections"])
    changed = False
    for name, value in choices.items():
        if value == 0 and seen.get(name) != 0:
            section, key = CHOICES[name]
            settings[section][key] = False
            changed = True
    noted = ";".join(f"{name}={choices[name]}" for name in sorted(choices))
    if noted != settings["install"]["connections"]:
        settings["install"]["connections"] = noted
        changed = True
    return changed


def _parse(noted: str) -> dict[str, int]:
    """The choices as noted in the settings ("UpdateChecks=0")."""
    pairs = (part.split("=", 1) for part in noted.split(";") if "=" in part)
    return {name: int(value) for name, value in pairs if value in ("0", "1")}


def apply_install_choices() -> None:
    """At the start of an installed copy: apply the installer's connection choices to this user's settings."""
    if not getattr(sys, "frozen", False) or is_portable():
        return
    choices = read_choices()
    if not choices:
        return
    settings = load_settings()
    if apply_choices(settings, choices) and not save_settings(settings):
        write_log("The installer's connection choices couldn't be saved", "critical")
