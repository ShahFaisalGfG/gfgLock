"""Output app metadata from pyproject.toml as JSON on stdout."""
import tomllib
import json
import pathlib

_toml = pathlib.Path(__file__).parent.parent / "pyproject.toml"

with _toml.open("rb") as _fh:
    _data = tomllib.load(_fh)

_project = _data["project"]
_gfglock = _data.get("tool", {}).get("gfglock", {})

print(json.dumps({
    "Version":   _project["version"],
    "AppName":   _gfglock.get("display_name", "gfgLock"),
    "Publisher": _gfglock.get("publisher", "gfgRoyal"),
    "Url":       _gfglock.get("url", ""),
    "ExeName":   _gfglock.get("exe_name", "gfgLock.exe"),
    "WingetId":  _gfglock.get("winget_id", ""),
}))
