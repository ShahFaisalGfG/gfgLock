# app.py - application entry point: QApplication + QQmlApplicationEngine

import ctypes
from ctypes import wintypes
import os
import sys
from multiprocessing import freeze_support
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMessageBox

from gfglock.ui.boot_thread import BootThread
from gfglock.ui.splash_screen import SplashScreen
from gfglock.utils.helpers import resource_path
from gfglock.utils.logging import write_log

_ENC_EXTS = (".gfglock", ".gfglck", ".gfgcha")


class _Startup:
    """Owns the splash screen and boot thread, then builds the window."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._engine: Optional[QQmlApplicationEngine] = None
        self._app_ctrl = None
        self._enc_ctrl = None
        self._prefs_ctrl = None

        logo = resource_path(
            "gfglock/assets/icons/Square310x310Logo.scale-100.png"
        )
        self._splash = SplashScreen(logo)
        self._splash.show()

        self._boot = BootThread()
        self._boot.stage_changed.connect(self._splash.set_stage)
        self._boot.boot_ready.connect(self._on_ready)
        self._boot.boot_failed.connect(self._on_failed)
        self._boot.start()

    def _on_ready(self) -> None:
        """Build controllers and load the QML UI once boot has finished."""
        try:
            from gfglock.controllers.app_ctrl import AppController
            from gfglock.controllers.encrypt_ctrl import EncryptController
            from gfglock.controllers.prefs_ctrl import PrefsController

            icon = QIcon()
            for size in (16, 32, 48, 256):
                name = f"Square44x44Logo.targetsize-{size}.png"
                path = resource_path(f"gfglock/assets/icons/{name}")
                if os.path.isfile(path):
                    icon.addFile(path, QSize(size, size))
            if not icon.isNull():
                self._app.setWindowIcon(icon)

            app_ctrl = AppController()
            enc_ctrl = EncryptController()
            prefs_ctrl = PrefsController()

            engine = QQmlApplicationEngine()
            ctx = engine.rootContext()
            ctx.setContextProperty("appController", app_ctrl)
            ctx.setContextProperty("encryptController", enc_ctrl)
            ctx.setContextProperty("prefsController", prefs_ctrl)

            qml_dir = resource_path("gfglock/qml")
            engine.addImportPath(qml_dir)

            cli_mode = _detect_mode(sys.argv[1:])
            ctx.setContextProperty("cliLaunchMode", cli_mode)

            engine.load(os.path.join(qml_dir, "main.qml"))
            if not engine.rootObjects():
                self._on_failed("The user interface failed to load.")
                return

            # Kept alive for the app's lifetime - QML's context properties hold
            # only a weak reference, so a garbage-collected controller here
            # would leave bound QML text empty.
            self._engine = engine
            self._app_ctrl = app_ctrl
            self._enc_ctrl = enc_ctrl
            self._prefs_ctrl = prefs_ctrl
            _handle_cli(enc_ctrl, sys.argv[1:], cli_mode)
            self._splash.close()
        except Exception as e:
            write_log(f"Failed to build interface: {e}", level="critical")
            self._on_failed(str(e))

    def _on_failed(self, message: str) -> None:
        """Show a real error dialog and quit instead of hanging silently."""
        write_log(f"Startup failed: {message}", level="critical")
        self._splash.set_error(message)
        QMessageBox.critical(None, "gfgLock", f"Failed to start:\n\n{message}")
        self._splash.close()
        self._app.exit(-1)

    def shutdown(self) -> None:
        """Release the QML scene before the controllers it referenced."""
        self._engine = None
        self._app_ctrl = None
        self._enc_ctrl = None
        self._prefs_ctrl = None


def main() -> None:
    """Initialise the Qt application, show the splash, and boot in the
    background.
    """

    # Must be called before QApplication in multiprocessing-frozen builds
    freeze_support()

    # ── PyInstaller: restore sys.argv (Explorer breaks long paths) ──
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        try:
            GetCommandLineW = ctypes.windll.kernel32.GetCommandLineW
            GetCommandLineW.argtypes = []
            GetCommandLineW.restype = wintypes.LPCWSTR
            CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
            CommandLineToArgvW.argtypes = [
                wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int),
            ]
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

    # Qt's automatic quit-on-last-window-closed can misfire the instant the
    # splash (a QWidget) closes while a QML window is the only one left open -
    # main.qml's root window quits explicitly on close instead (see main.qml).
    app.setQuitOnLastWindowClosed(False)

    startup = _Startup(app)
    code = app.exec()
    startup.shutdown()
    sys.exit(code)


def _detect_mode(args: list) -> str:
    """Return 'encrypt'/'decrypt' from CLI args, or '' if neither."""
    if not args:
        return ""
    if args[0].lower() in ("encrypt", "decrypt"):
        return args[0].lower()
    if any(os.path.exists(p) and p.lower().endswith(_ENC_EXTS) for p in args):
        return "decrypt"
    return ""


def _handle_cli(enc_ctrl, args: list, mode: str) -> None:
    """Pre-populate the file model from CLI arguments if any are present."""
    if not args or not mode:
        return

    path_args = args[1:] if args[0].lower() in ("encrypt", "decrypt") else args

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
            if mode == "encrypt" and not abs_p.lower().endswith(_ENC_EXTS):
                final_paths.append(abs_p)
            elif mode == "decrypt" and abs_p.lower().endswith(_ENC_EXTS):
                final_paths.append(abs_p)
        elif os.path.isdir(abs_p):
            for root, _, files in os.walk(abs_p):
                for f in files:
                    fp = os.path.join(root, f)
                    is_enc = fp.lower().endswith(_ENC_EXTS)
                    if mode == "encrypt" and not is_enc:
                        final_paths.append(fp)
                    elif mode == "decrypt" and is_enc:
                        final_paths.append(fp)

    # Deduplicate
    seen: set = set()
    unique = [
        p for p in final_paths
        if not (p in seen or seen.add(p))  # type: ignore[func-returns-value]
    ]

    enc_ctrl.setMode(mode)
    for p in unique:
        enc_ctrl.addPath(p)


def _parse_paths(path_args: list) -> list:
    """Reconstruct file paths from CLI argv, with @responsefile support."""
    if not path_args:
        return []
    if len(path_args) == 1 and path_args[0].startswith("@"):
        resp = path_args[0][1:].strip("\"'")
        try:
            with open(resp, encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except OSError:
            # Fall back to original args so the caller can surface an error
            return path_args
        try:
            os.remove(resp)
        except Exception:
            pass
        return lines
    # IExplorerCommand passes each path as a correctly split argv element
    if any(os.path.exists(p.strip("\"'")) for p in path_args):
        return path_args
    # Fallback: single path with spaces may have been split across elements
    combined = " ".join(path_args)
    if os.path.exists(combined):
        return [combined]
    return path_args


if __name__ == "__main__":
    main()
