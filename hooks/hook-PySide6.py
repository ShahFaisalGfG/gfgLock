"""Collect the PySide6 package without Qt's software OpenGL renderer.

opengl32sw.dll (about 20 MB) stands in for a missing OpenGL driver. Qt Quick on Windows draws with
Direct3D 11, which Windows backs with its own software renderer (WARP) when no GPU driver is
present, so gfgLock never loads it. The rest matches PyInstaller's own PySide6 hook.
"""

from pathlib import Path

from PyInstaller.utils.hooks.qt import ensure_single_qt_bindings_package, pyside6_library_info

ensure_single_qt_bindings_package("PySide6")

hiddenimports = ["shiboken6", "inspect", "PySide6.support.deprecated"]
binaries = [
    entry
    for entry in pyside6_library_info.collect_extra_binaries()
    if Path(entry[0]).name.casefold() != "opengl32sw.dll"
]
