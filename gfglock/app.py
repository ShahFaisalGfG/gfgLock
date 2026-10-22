# app.py - application entry point: QApplication + QQmlApplicationEngine

import ctypes
import os
import re
import sys
import tempfile
from ctypes import wintypes
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
from gfglock.utils.single_instance import LaunchRequest, SingleInstance, hold_app_mutexes

_MODES = ("encrypt", "decrypt")
_SHUTDOWN_WAIT_MS = 2000
_SELF_TEST_FLAG = "--self-test"
_UNREADABLE_LIST = "The file list from Explorer couldn't be read."
# Images loaded outside QML; the self-test checks they are bundled.
SPLASH_LOGO = "gfglock/assets/icons/Square310x310Logo.scale-100.png"
WINDOW_ICONS = {size: f"gfglock/assets/icons/Square44x44Logo.targetsize-{size}.png" for size in (16, 32, 48, 256)}


class _Startup:
    """Owns the splash screen and boot thread, then builds the window."""

    def __init__(self, app: QApplication, instance: SingleInstance, launch: LaunchRequest) -> None:
        self._app = app
        self._instance = instance
        self._launch = launch
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
            # Already imported by the boot thread, off the GUI thread.
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
            prefs_ctrl.set_run_controllers([enc_ctrl, dec_ctrl])

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
            # Later launches (another Explorer right-click) hand their files to this window; the
            # ones that arrived while it loaded are delivered by attach(), after this launch's own.
            self._instance.filesReceived.connect(app_ctrl.openFiles)
            self._instance.activationRequested.connect(app_ctrl.activateRequested)
            self._instance.noticeReceived.connect(app_ctrl.notice)
            launch = self._launch
            if launch.mode and launch.paths:
                app_ctrl.openFiles(launch.mode, list(launch.paths))
            app_ctrl.show_notices(launch.notice)
            self._instance.attach()
            self._splash.close()
        except Exception as error:  # the start-up boundary: anything here would leave no window
            self._on_failed(f"The window couldn't be built: {error}")

    def _on_failed(self, message: str) -> None:
        """Log the failure, show it, and quit instead of hanging silently."""
        write_log(f"Startup failed: {message}", "critical", force=True)
        self._splash.close()  # it stays on top, so a dialog shown under it couldn't be seen
        QMessageBox.critical(None, "gfgLock", f"gfgLock couldn't start:\n\n{message}")
        self._app.exit(-1)

    def shutdown(self) -> None:
        """Stop background work, then release the QML scene before the controllers it referenced."""
        for controller in self._controllers:
            controller.shutdown()
        if self._prefs_ctrl is not None:
            self._prefs_ctrl.shutdown()
        if self._controllers:
            # Folder scans drain in each controller's own pool (its shutdown waits for them). A
            # stopped run and the speed test end within a block on the global pool; wait for them
            # so their threads don't outlive the objects they report to.
            QThreadPool.globalInstance().waitForDone(_SHUTDOWN_WAIT_MS)
        self._instance.close()
        self._engine = None
        self._app_ctrl = None
        self._controllers = []
        self._prefs_ctrl = None


def main() -> None:
    """Start gfgLock: hand the launch to an open window, or show the splash and boot in the background."""
    if getattr(sys, "frozen", False):
        _restore_argv()

    # Every QML control uses the Material style (as in CC-Gen-Ultimate), and the bundle carries only
    # that style, so the self-test loads the screens with it too. Fusion styles the splash screen.
    QQuickStyle.setStyle("Material")

    # `--self-test [REPORT_PATH]` verifies the build and exits 0 or 1 (used by the release workflow).
    if _SELF_TEST_FLAG in sys.argv:
        index = sys.argv.index(_SELF_TEST_FLAG)
        sys.exit(run_self_test(sys.argv[index + 1] if index + 1 < len(sys.argv) else None))

    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    # High-DPI: let Qt handle scaling automatically
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Explorer's "Encrypt/Decrypt with gfgLock" passes a mode and paths. When gfgLock is already
    # open, they go to that window and this launch ends.
    launch = parse_launch(sys.argv[1:])
    _leave_launch_folder()
    instance = SingleInstance()
    if instance.try_forward(launch):
        sys.exit(0)
    hold_app_mutexes()  # only a launch that opens a window; one that handed over its files has exited

    # Qt's automatic quit-on-last-window-closed can misfire the instant the
    # splash (a QWidget) closes while a QML window is the only one left open -
    # main.qml's root window quits explicitly on close instead (see main.qml).
    app.setQuitOnLastWindowClosed(False)

    startup = _Startup(app, instance, launch)
    code = app.exec()
    startup.shutdown()
    sys.exit(code)


def parse_launch(args: list[str]) -> LaunchRequest:
    """The request in the command-line arguments: an optional mode, then paths or one "@list" file.

    Paths are kept exactly as given (a folder may end in an apostrophe) and made absolute; the
    ones that don't exist are left out and counted in the notice.
    """
    if not args:
        return LaunchRequest()
    has_mode = args[0].lower() in _MODES
    # Without a mode (files dropped on the exe, Open with) the mode is encrypt; the window still
    # sends encrypted files to the Decrypt tab.
    mode = args[0].lower() if has_mode else _MODES[0]
    items = args[1:] if has_mode else args
    if len(items) == 1 and items[0].startswith("@"):
        listed = _read_list_file(items[0][1:])
        if listed is None:
            return LaunchRequest(mode, (), _UNREADABLE_LIST)
        items = listed
    else:
        items = _rejoin_split_path(items)
    paths = [os.path.abspath(item) for item in items]
    found = tuple(path for path in paths if os.path.exists(path))
    missing = len(paths) - len(found)
    notice = f"{missing} {'item' if missing == 1 else 'items'} couldn't be found." if missing else ""
    return LaunchRequest(mode, found, notice)


def _restore_argv() -> None:
    """Rebuild sys.argv from the Unicode command line; the frozen exe's own split can break long paths."""
    get_command_line = ctypes.windll.kernel32.GetCommandLineW
    get_command_line.argtypes = []
    get_command_line.restype = wintypes.LPCWSTR
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    split.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int()
    argv = split(get_command_line(), ctypes.byref(count))
    if not argv:
        write_log(f"Could not read the command line: {ctypes.WinError()}", "critical", force=True)
        return
    try:
        sys.argv = [sys.executable] + [argv[i] for i in range(1, count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def _leave_launch_folder() -> None:
    """Make the exe's folder current, so nothing resolves against the folder gfgLock was started in.

    Explorer starts gfgLock in the folder being viewed, where a program started by bare name (or a
    DLL) could otherwise be picked up. Running from source keeps the current folder.
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    except OSError as error:
        write_log(f"Could not change the current folder: {error}", "critical", force=True)


def _is_shell_list_file(path: str) -> bool:
    """True for a file list the Explorer extension wrote: gfg<hex>.tmp in the temp folder."""
    folder, name = os.path.split(os.path.abspath(path))
    return (os.path.normcase(folder) == os.path.normcase(os.path.abspath(tempfile.gettempdir()))
            and re.fullmatch(r"gfg[0-9a-f]{1,4}\.tmp", name, re.IGNORECASE) is not None)


def _read_list_file(path: str) -> Optional[list[str]]:
    """The paths in an "@list" file (UTF-8, one per line), or None when it can't be read.

    Only the line ending is removed from each line. The Explorer extension's own list file
    (%TEMP%\\gfgXXXX.tmp) is deleted afterwards; "@" with any other file just reads it.
    """
    try:
        with open(path, encoding="utf-8-sig") as fh:
            lines = [line.rstrip("\r\n") for line in fh]
    except (OSError, ValueError) as error:  # UnicodeDecodeError is a ValueError
        write_log(f"Could not read the file list {path}: {error}", "critical")
        return None
    finally:
        if _is_shell_list_file(path) and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as error:
                write_log(f"Could not remove the file list {path}: {error}", "critical")
    return [line for line in lines if line]


def _rejoin_split_path(items: list[str]) -> list[str]:
    """The arguments as given, or one path when an unquoted path was split at its spaces."""
    if len(items) < 2 or any(os.path.exists(item) for item in items):
        return items
    combined = " ".join(items)
    return [combined] if os.path.exists(combined) else items


if __name__ == "__main__":
    main()
