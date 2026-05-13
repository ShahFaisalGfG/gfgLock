# app.py — application entry point: QApplication + QQmlApplicationEngine

import ctypes
from ctypes import wintypes
import os
import shlex
import sys
from multiprocessing import freeze_support

from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from gfglock.controllers.app_ctrl import AppController
from gfglock.controllers.encrypt_ctrl import EncryptController
from gfglock.controllers.prefs_ctrl import PrefsController
from gfglock.utils.helpers import resource_path


def main() -> None:
    """Initialise the Qt application and launch the QML engine."""

    # Must be called before QApplication in multiprocessing-frozen builds
    freeze_support()

    # ── PyInstaller: restore real sys.argv (Windows shell breaks long paths) ──
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        try:
            GetCommandLineW = ctypes.windll.kernel32.GetCommandLineW
            GetCommandLineW.argtypes = []
            GetCommandLineW.restype = wintypes.LPCWSTR
            CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
            CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
            CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
            cmd = GetCommandLineW()
            argc = ctypes.c_int()
            argv = CommandLineToArgvW(cmd, ctypes.byref(argc))
            sys.argv = [argv[i] for i in range(argc.value)]
            if sys.argv:
                sys.argv[0] = sys.executable
        except Exception:
            pass

    os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    # High-DPI: let Qt handle scaling automatically
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(resource_path("gfglock/assets/icons/gfgLock.png")))

    # ── Create controllers ────────────────────────────────────────────────────
    app_ctrl = AppController()
    enc_ctrl = EncryptController()
    prefs_ctrl = PrefsController()

    # ── QML engine ────────────────────────────────────────────────────────────
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("appController", app_ctrl)
    ctx.setContextProperty("encryptController", enc_ctrl)
    ctx.setContextProperty("prefsController", prefs_ctrl)

    # Add qml/ directory to the import path so TitleBar, FileList etc. resolve
    qml_dir = resource_path("gfglock/qml")
    engine.addImportPath(qml_dir)

    main_qml = os.path.join(qml_dir, "main.qml")
    engine.load(main_qml)

    if not engine.rootObjects():
        sys.exit(-1)

    # ── CLI argument handling ─────────────────────────────────────────────────
    _handle_cli(enc_ctrl, sys.argv[1:])

    sys.exit(app.exec())


def _handle_cli(enc_ctrl, args: list) -> None:
    """Pre-populate the file model from CLI arguments if any are present."""
    if not args:
        return

    enc_exts = (".gfglock", ".gfglck", ".gfgcha")

    # Detect explicit mode or auto-detect from file extensions
    mode = None
    path_args = args
    if args and args[0].lower() in ("encrypt", "decrypt"):
        mode = args[0].lower()
        path_args = args[1:]
    else:
        has_enc = any(
            os.path.exists(p) and p.lower().endswith(enc_exts) for p in args
        )
        if has_enc:
            mode = "decrypt"

    if not mode:
        return

    # Reconstruct paths (Windows Explorer can break paths with spaces)
    raw_paths = _parse_paths(path_args)

    # Walk and filter paths by mode
    final_paths = []
    for p in raw_paths:
        p = p.strip("\"'")
        abs_p = os.path.abspath(p)
        if not os.path.exists(abs_p):
            final_paths.append(abs_p)
            continue
        if os.path.isfile(abs_p):
            if mode == "encrypt" and not abs_p.lower().endswith(enc_exts):
                final_paths.append(abs_p)
            elif mode == "decrypt" and abs_p.lower().endswith(enc_exts):
                final_paths.append(abs_p)
        elif os.path.isdir(abs_p):
            for root, _, files in os.walk(abs_p):
                for f in files:
                    fp = os.path.join(root, f)
                    if mode == "encrypt" and not fp.lower().endswith(enc_exts):
                        final_paths.append(fp)
                    elif mode == "decrypt" and fp.lower().endswith(enc_exts):
                        final_paths.append(fp)

    # Deduplicate
    seen: set = set()
    unique = [p for p in final_paths if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]

    for p in unique:
        enc_ctrl.addPath(p)


def _parse_paths(path_args: list) -> list:
    """Reconstruct file paths that Windows may have split across argv."""
    if not path_args:
        return []
    combined = " ".join(path_args)
    if os.path.exists(combined):
        return [combined]
    try:
        parsed = shlex.split(combined)
        if any(os.path.exists(p.strip("\"'")) for p in parsed):
            return parsed
    except Exception:
        pass
    return path_args


if __name__ == "__main__":
    main()
