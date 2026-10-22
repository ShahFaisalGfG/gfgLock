"""Add bundled Qt DLL folders to Windows' native extension search path."""

from __future__ import annotations

import ctypes
import os
import sys


_DLL_SEARCH_HANDLES = []
_SYSTEM_ICU_DLL = None

_meipass = getattr(sys, "_MEIPASS", None)

if sys.platform == "win32" and _meipass:
    # QtCore imports the unversioned ICU ABI. Load Windows' ICU explicitly so
    # an unrelated ICU DLL earlier on PATH cannot satisfy Qt's dependency.
    _system_icu = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "System32", "icuuc.dll"
    )
    if os.path.isfile(_system_icu):
        try:
            _SYSTEM_ICU_DLL = ctypes.WinDLL(_system_icu)
        except OSError:
            _SYSTEM_ICU_DLL = None

    _dll_directories = [
        _meipass,
        os.path.join(_meipass, "PySide6"),
        os.path.join(_meipass, "shiboken6"),
    ]
    for _directory in _dll_directories:
        if os.path.isdir(_directory):
            _DLL_SEARCH_HANDLES.append(os.add_dll_directory(_directory))

    os.environ["PATH"] = os.pathsep.join(
        _dll_directories + [os.environ.get("PATH", "")]
    )
