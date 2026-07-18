# boot_thread.py - loads the encryption engine off the GUI thread and
# reports staged progress to the startup splash screen.
#
# The imports inside run() below are a deliberate, narrow exception to the
# project's top-of-file import rule: Python fully resolves a file's
# top-level imports before running any other code in it, so live
# per-dependency progress on screen is only possible if the heavy imports
# happen after the splash is already visible, i.e. inside a function body.

from PySide6.QtCore import QThread, Signal

from gfglock.utils.logging import write_log


class BootThread(QThread):
    """Imports the encryption engine stack, staged for splash progress."""

    stage_changed = Signal(str, int)
    boot_ready = Signal()
    boot_failed = Signal(str)

    def run(self) -> None:
        """Load the native bridge and cipher backends, then controllers."""
        try:
            self.stage_changed.emit("Loading encryption engine...", 40)
            import gfglock.core.native_bridge  # noqa: F401
            import gfglock.core.aes256_gcm_cfb  # noqa: F401
            import gfglock.core.chacha20_poly1305  # noqa: F401

            self.stage_changed.emit("Preparing interface...", 85)
            import gfglock.controllers.app_ctrl  # noqa: F401
            import gfglock.controllers.encrypt_ctrl  # noqa: F401
            import gfglock.controllers.prefs_ctrl  # noqa: F401

            self.boot_ready.emit()
        except Exception as e:
            write_log(f"Startup failed: {e}", level="critical")
            self.boot_failed.emit(str(e))
