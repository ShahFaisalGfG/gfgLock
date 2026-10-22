"""Collect only the QML modules gfgLock uses, plus the modules they depend on.

PyInstaller's own QtQml hook bundles every QML module PySide6 ships (Quick3D, Charts, WebEngine and
more) together with every Qt DLL their plugins load. This hook starts from the modules imported by
the app's QML files and follows each module's qmldir `import`/`depends` lines and the imports in
its own QML files. Style variants in `+<style>` folders are not followed: the app imports the one
style it uses (Material), which brings in what that style needs. Qt Design Studio `designer`
folders are neither followed nor bundled. A needed module that PySide6 does not ship stops the
build.

The QML debugger plugins (plugins/qmltooling) and the Qt Quick translations are left out: the app
never enables QML debugging and loads no Qt translations.
"""

import re
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

APP_QML_DIR = Path(__file__).resolve().parent.parent / "gfglock" / "qml"
BUILTIN_MODULES = frozenset({"QML"})  # provided by the QML engine itself, so it has no folder
SKIPPED_FOLDERS = frozenset({"designer"})

_QML_IMPORT = re.compile(r"^\s*import\s+([A-Za-z_][\w.]*)", re.MULTILINE)
_QMLDIR_IMPORT = re.compile(r"^\s*(?:default\s+)?(?:import|depends)\s+([A-Za-z_][\w.]*)", re.MULTILINE)


def _qml_imports(files) -> set[str]:
    """Return the module names imported by the given QML files."""
    return {name for path in files for name in _QML_IMPORT.findall(path.read_text(encoding="utf-8"))}


def _module_files(folder: Path) -> list[Path]:
    """Return the QML files of one module folder, without nested modules, variants, or design files."""
    files = []
    for path in folder.rglob("*.qml"):
        parts = path.relative_to(folder).parent.parts
        if any(part.startswith("+") or part in SKIPPED_FOLDERS for part in parts):
            continue
        if any((folder.joinpath(*parts[: depth + 1]) / "qmldir").is_file() for depth in range(len(parts))):
            continue
        files.append(path)
    return files


def _needed_modules(qml_root: Path) -> dict[str, Path]:
    """Map every QML module the app needs to its folder under qml_root; exit when one is missing."""
    found: dict[str, Path] = {}
    pending = sorted(_qml_imports(APP_QML_DIR.rglob("*.qml")))
    while pending:
        name = pending.pop()
        if name in found or name in BUILTIN_MODULES:
            continue
        folder = qml_root.joinpath(*name.split("."))
        qmldir = folder / "qmldir"
        if not qmldir.is_file():
            raise SystemExit(f"ERROR: the QML module {name} is needed, but PySide6 has no {qmldir}")
        found[name] = folder
        pending.extend(_QMLDIR_IMPORT.findall(qmldir.read_text(encoding="utf-8")))
        pending.extend(_qml_imports(_module_files(folder)))
    return found


def _keep_needed(entries, folders: set[Path]) -> list[tuple[str, str]]:
    """Keep the (source, destination) entries that sit directly in a needed module folder."""
    return [
        entry
        for entry in entries
        if Path(entry[0]).parent in folders and Path(entry[0]).name not in SKIPPED_FOLDERS
    ]


hiddenimports, _qmltooling_plugins, _translations = add_qt6_dependencies(__file__)
_qml_binaries, _qml_datas = pyside6_library_info.collect_qtqml_files()
_modules = _needed_modules(Path(pyside6_library_info.location["QmlImportsPath"]).resolve())
_folders = set(_modules.values())

binaries = _keep_needed(_qml_binaries, _folders)
datas = _keep_needed(_qml_datas, _folders)

_collected = {Path(source).parent for source, _dest in binaries + datas}
_missing = sorted(name for name, folder in _modules.items() if folder not in _collected)
if _missing:
    raise SystemExit("ERROR: PyInstaller collected no files for the QML modules " + ", ".join(_missing))
