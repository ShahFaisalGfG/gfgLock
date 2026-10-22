# boot_thread.py - loads the encryption engine off the GUI thread and
# reports staged progress to the startup splash screen.
#
# The imports inside run() below are a deliberate, narrow exception to the
# project's top-of-file import rule: Python fully resolves a file's
# top-level imports before running any other code in it, so live
# per-dependency progress on screen is only possible if the heavy imports
# happen after the splash is already visible, i.e. inside a function body.
# Nothing imported before the splash loads the engine (gfglock.core imports
# nothing by itself), so its cost is paid here, off the GUI thread.

from PySide6.QtCore import QThread, Signal


class BootThread(QThread):
    """Imports the encryption engine stack, staged for splash progress."""

    stage_changed = Signal(str, int)
    boot_ready = Signal()
    boot_failed = Signal(str)

    def run(self) -> None:
        """Load the native engine (and its OpenSSL DLL), the file operations, then the controllers."""
        try:
            self.stage_changed.emit("Loading encryption engine...", 40)
            import gfglock.core.native_bridge  # noqa: F401
            import gfglock.core.file_ops  # noqa: F401

            self.stage_changed.emit("Preparing interface...", 85)
            import gfglock.controllers.app_ctrl  # noqa: F401
            import gfglock.controllers.encrypt_ctrl  # noqa: F401
            import gfglock.controllers.prefs_ctrl  # noqa: F401

            self.boot_ready.emit()
        except Exception as error:  # reported (and logged) by the window's start-up, which quits
            self.boot_failed.emit(f"{type(error).__name__}: {error}")
