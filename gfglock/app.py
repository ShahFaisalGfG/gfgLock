# app.py - application entry point: QApplication + QQmlApplicationEngine

import ctypes
from ctypes import wintypes
import os
import re
import sys
import tempfile
from multiprocessing import freeze_support
from typing import Optional

from PySide6.QtCore import QSize, QThreadPool
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from gfglock.ui.boot_thread import BootThread
from gfglock.ui.splash_screen import SplashScreen
from gfglock.utils.helpers import resource_path
from gfglock.utils.logging import write_log
from gfglock.utils.self_test import run_self_test
from gfglock.utils.single_instance import SingleInstance

_ENC_EXTS = (".gfglock", ".gfglck", ".gfgcha")
_SHUTDOWN_WAIT_MS = 2000
_SELF_TEST_FLAG = "--self-test"
# Images loaded outside QML; the self-test checks they are bundled.
SPLASH_LOGO = "gfglock/assets/icons/Square310x310Logo.scale-100.png"
WINDOW_ICONS = {size: f"gfglock/assets/icons/Square44x44Logo.targetsize-{size}.png" for size in (16, 32, 48, 256)}


class _Startup:
    """Owns the splash screen and boot thread, then builds the window."""

    def __init__(self, app: QApplication, instance: SingleInstance, mode: str, paths: list[str]) -> None:
        self._app = app
        self._instance = instance
        self._launch = (mode, paths)
        self._engine: Optional[QQmlApplicationEngine] = None
        self._app_ctrl = None
        self._controllers: list = []
        self._prefs_ctrl = None

        self._splash = SplashScreen(resource_path(SPLASH_LOGO))
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
            for size, relative in WINDOW_ICONS.items():
                path = resource_path(relative)
                if os.path.isfile(path):
                    icon.addFile(path, QSize(size, size))
            if not icon.isNull():
                self._app.setWindowIcon(icon)

            app_ctrl = AppController()
            enc_ctrl = EncryptController("encrypt")
            dec_ctrl = EncryptController("decrypt")
            prefs_ctrl = PrefsController()

            engine = QQmlApplicationEngine()
            ctx = engine.rootContext()
            ctx.setContextProperty("appController", app_ctrl)
            ctx.setContextProperty("encryptController", enc_ctrl)
            ctx.setContextProperty("decryptController", dec_ctrl)
            ctx.setContextProperty("prefsController", prefs_ctrl)

            qml_dir = resource_path("gfglock/qml")
            engine.addImportPath(qml_dir)
            engine.load(os.path.join(qml_dir, "main.qml"))
            if not engine.rootObjects():
                self._on_failed("The user interface failed to load.")
                return

            # Kept alive for the app's lifetime - QML's context properties hold
            # only a weak reference, so a garbage-collected controller here
            # would leave bound QML text empty.
            self._engine = engine
            self._app_ctrl = app_ctrl
            self._controllers = [enc_ctrl, dec_ctrl]
            self._prefs_ctrl = prefs_ctrl
            # Later launches (another Explorer right-click) hand their files to this window.
            self._instance.filesReceived.connect(app_ctrl.openFiles)
            self._instance.activationRequested.connect(app_ctrl.activateRequested)
            mode, paths = self._launch
            if mode and paths:
                app_ctrl.openFiles(mode, paths)
            self._splash.close()
        except Exception as e:
            write_log(f"Failed to build interface: {e}", level="critical")
            self._on_failed(str(e))

    def _on_failed(self, message: str) -> None:
        """Show an error dialog and quit instead of hanging silently."""
        write_log(f"Startup failed: {message}", level="critical")
        self._splash.set_error(message)
        QMessageBox.critical(None, "gfgLock", f"Failed to start:\n\n{message}")
        self._splash.close()
        self._app.exit(-1)

    def shutdown(self) -> None:
        """Stop background work, then release the QML scene before the controllers it referenced."""
        for controller in self._controllers:
            controller.shutdown()
        if self._prefs_ctrl is not None:
            self._prefs_ctrl.shutdown()
        if self._controllers:
            # A cancelled folder scan exits within milliseconds and a read size test after its
            # current step; wait for them so their threads don't outlive the objects they report to.
            QThreadPool.globalInstance().waitForDone(_SHUTDOWN_WAIT_MS)
        self._instance.close()
        self._engine = None
        self._app_ctrl = None
        self._controllers = []
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

    # `--self-test [REPORT_PATH]` verifies the build and exits 0 or 1 (used by the release workflow).
    if _SELF_TEST_FLAG in sys.argv:
        index = sys.argv.index(_SELF_TEST_FLAG)
        sys.exit(run_self_test(sys.argv[index + 1] if index + 1 < len(sys.argv) else None))

    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    # High-DPI: let Qt handle scaling automatically
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    # Every QML control uses the Material style (as in CC-Gen-Ultimate); Fusion styles the
    # splash screen, which is a widget.
    QQuickStyle.setStyle("Material")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Explorer's "Encrypt/Decrypt with gfgLock" passes a mode and paths. When gfgLock is already
    # open, they go to that window and this launch ends.
    mode, paths = _launch_request(sys.argv[1:])
    instance = SingleInstance()
    if instance.tryForward(mode, paths):
        sys.exit(0)

    # Qt's automatic quit-on-last-window-closed can misfire the instant the
    # splash (a QWidget) closes while a QML window is the only one left open -
    # main.qml's root window quits explicitly on close instead (see main.qml).
    app.setQuitOnLastWindowClosed(False)

    startup = _Startup(app, instance, mode, paths)
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


def _launch_request(args: list) -> tuple[str, list[str]]:
    """The mode ("encrypt"/"decrypt" or "") and absolute paths given on the command line."""
    mode = _detect_mode(args)
    if not mode:
        return "", []
    path_args = args[1:] if args[0].lower() in ("encrypt", "decrypt") else args
    # Reconstruct paths (Windows Explorer can break paths with spaces)
    return mode, [os.path.abspath(p.strip("\"'")) for p in _parse_paths(path_args)]


def _is_shell_list_file(path: str) -> bool:
    """True for a file list the Explorer extension wrote: gfg<hex>.tmp in the temp folder."""
    folder, name = os.path.split(os.path.abspath(path))
    return (os.path.normcase(folder) == os.path.normcase(os.path.abspath(tempfile.gettempdir()))
            and re.fullmatch(r"gfg[0-9a-f]{1,4}\.tmp", name, re.IGNORECASE) is not None)


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
        # Only the shell extension's own list file (%TEMP%\gfgXXXX.tmp) is deleted after reading;
        # "@" with any other file just reads it.
        if _is_shell_list_file(resp):
            try:
                os.remove(resp)
            except OSError as error:
                write_log(f"Could not remove the file list {resp}: {error}", "critical")
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
