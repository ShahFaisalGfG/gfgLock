# notifier.py - desktop notifications shown from gfgLock's own tray icon, in-process

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from gfglock.config.defaults import AppInfo
from gfglock.utils.logging import write_log

# How long Windows is asked to show a message, and how long the tray icon stays after it when
# gfgLock is in front. When it isn't, the icon stays until the user comes back, because Windows
# drops an icon's messages from the notification center once the icon is removed.
SHOW_MS = 10_000
HIDE_AFTER_MS = 30_000

_toaster: "_Toaster | None" = None


class _Toaster(QObject):
    """The tray icon that carries notifications, shown only while a message may still be unread."""

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._icon = QSystemTrayIcon(self)
        self._icon.setToolTip(AppInfo.APP_NAME)
        self._icon.messageClicked.connect(self._open_window)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(HIDE_AFTER_MS)
        self._hide_timer.timeout.connect(self._icon.hide)
        app.applicationStateChanged.connect(self._on_state)

    def show(self, title: str, body: str) -> None:
        """Show the tray icon with one message; it goes once the user is back in gfgLock."""
        icon = QApplication.windowIcon()
        self._icon.setIcon(icon)
        self._icon.show()
        self._icon.showMessage(title, body, icon, SHOW_MS)
        if _in_front():
            self._hide_timer.start()
        else:
            self._hide_timer.stop()

    def _on_state(self, state: Qt.ApplicationState) -> None:
        """The user is back in gfgLock: the message has done its job."""
        if state == Qt.ApplicationState.ApplicationActive and self._icon.isVisible() and not self._hide_timer.isActive():
            self._hide_timer.start()

    def _open_window(self) -> None:
        """Bring gfgLock's main window to the front when the message is clicked."""
        self._icon.hide()
        windows = [w for w in QGuiApplication.topLevelWindows() if w.isVisible() and w.transientParent() is None]
        if not windows:
            return
        window = windows[0]
        if window.visibility() == QWindow.Visibility.Minimized:
            window.showNormal()
        window.raise_()
        window.requestActivate()


def _in_front() -> bool:
    """True while one of gfgLock's windows is the active one."""
    return QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive


def notify(title: str, body: str) -> None:
    """Show a desktop notification from gfgLock's tray icon. Failures are logged, never raised."""
    global _toaster
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        write_log("Could not show a notification: the app has no window system", "critical")
        return
    if not QSystemTrayIcon.isSystemTrayAvailable() or not QSystemTrayIcon.supportsMessages():
        write_log("Could not show a notification: the notification area is not available", "critical")
        return
    if QApplication.windowIcon().isNull():
        write_log("Could not show a notification: the app icon is missing", "critical")
        return
    try:
        if _toaster is None:
            _toaster = _Toaster(app)
        _toaster.show(title, body)
    except RuntimeError as error:  # the tray icon was deleted with the app; a new one is made next time
        _toaster = None
        write_log(f"Could not show a notification: {error}", "critical")
