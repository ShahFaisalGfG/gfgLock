"""App metadata from pyproject.toml: printed as JSON, or written as an exe's version details.

    python read_meta.py
        The metadata as JSON (scripts\\common.ps1 reads it).
    python read_meta.py --version-file OUT --exe NAME --description TEXT
        A PyInstaller version file for NAME.exe: the app's name as its product name and the
        pyproject version as its product and file version, as code signing requires of every exe.
"""
import argparse
import json
import pathlib
import re
import tomllib

_ROOT = pathlib.Path(__file__).parent.parent


def app_meta() -> dict[str, str]:
    """The metadata the build scripts use, from pyproject.toml."""
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    project = data["project"]
    app = data.get("tool", {}).get("gfglock", {})
    return {
        "Version":   project["version"],
        "AppName":   app.get("display_name", "gfgLock"),
        "Publisher": app.get("publisher", "gfgRoyal"),
        "Url":       app.get("url", ""),
        "ExeName":   app.get("exe_name", "gfgLock.exe"),
        "WingetId":  app.get("winget_id", ""),
    }


def copyright_line() -> str:
    """The licence's copyright line ("Copyright (c) 2025-2026 Shah Faisal")."""
    for line in (_ROOT / "LICENSE").read_text(encoding="utf-8").splitlines():
        if line.startswith("Copyright"):
            return line.strip()
    raise ValueError("LICENSE has no copyright line")


def version_info(meta: dict[str, str], exe: str, description: str, copyright_text: str) -> str:
    """A PyInstaller version file (a VSVersionInfo expression) for exe."""
    numbers = [int(part) for part in re.findall(r"\d+", meta["Version"])[:4]]
    numbers += [0] * (4 - len(numbers))
    strings = {
        "CompanyName": meta["Publisher"],
        "FileDescription": description,
        "FileVersion": meta["Version"],
        "InternalName": exe,
        "LegalCopyright": copyright_text,
        "OriginalFilename": f"{exe}.exe",
        "ProductName": meta["AppName"],
        "ProductVersion": meta["Version"],
    }
    entries = ",\n".join(f"          StringStruct({key!r}, {value!r})" for key, value in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(numbers)}, prodvers={tuple(numbers)}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
{entries}
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version-file", type=pathlib.Path, help="write a PyInstaller version file here")
    parser.add_argument("--exe", help="the exe's name without .exe")
    parser.add_argument("--description", help="what the exe is, for its file description")
    args = parser.parse_args(argv)
    meta = app_meta()
    if args.version_file is None:
        print(json.dumps(meta))
        return 0
    if not args.exe or not args.description:
        parser.error("--version-file needs --exe and --description")
    args.version_file.parent.mkdir(parents=True, exist_ok=True)
    args.version_file.write_text(version_info(meta, args.exe, args.description, copyright_line()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
