import inspect
import time
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from gfglock.controllers import encrypt_ctrl
from gfglock.models import file_model
from gfglock.services import folder_scanner, notifier, worker
from gfglock.utils import logging as log_mod


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Share one QApplication with the rest of the suite."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tray(monkeypatch, qt_app):
    """A stand-in for QSystemTrayIcon (offscreen Qt has no notification area) and an app icon."""
    fake = MagicMock()
    fake.isSystemTrayAvailable.return_value = True
    fake.supportsMessages.return_value = True
    monkeypatch.setattr(notifier, "QSystemTrayIcon", fake)
    monkeypatch.setattr(notifier, "_toaster", None)
    pixmap = QPixmap(16, 16)
    pixmap.fill()
    previous = QApplication.windowIcon()
    QApplication.setWindowIcon(QIcon(pixmap))
    yield fake
    QApplication.setWindowIcon(previous)


@pytest.fixture
def logged(monkeypatch):
    """The notifier's write_log, recorded."""
    log = MagicMock()
    monkeypatch.setattr(notifier, "write_log", log)
    return log


def _wait_for(condition, timeout=2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return condition()


class TestNotify:
    """notify shows an in-process tray message under gfgLock's own icon and name (A3, A15)."""

    def test_shows_one_message_with_the_app_icon(self, tray):
        notifier.notify("Encryption complete", "All 3 files encrypted in 2.0 s.")
        icon = tray.return_value
        icon.show.assert_called_once()
        title, body, shown_icon, msecs = icon.showMessage.call_args[0]
        assert (title, body, msecs) == ("Encryption complete", "All 3 files encrypted in 2.0 s.", notifier.SHOW_MS)
        assert not shown_icon.isNull()
        icon.setToolTip.assert_called_once_with("gfgLock")

    def test_the_tray_icon_is_made_once_and_reused(self, tray):
        notifier.notify("A", "first")
        notifier.notify("B", "second")
        assert tray.call_count == 1
        assert tray.return_value.showMessage.call_count == 2

    def test_in_front_the_tray_icon_hides_after_the_message(self, tray, monkeypatch):
        monkeypatch.setattr(notifier, "HIDE_AFTER_MS", 20)
        monkeypatch.setattr(notifier, "_in_front", lambda: True)
        notifier.notify("Decryption complete", "Done.")
        icon = tray.return_value
        assert _wait_for(lambda: icon.hide.called)

    def test_away_the_tray_icon_stays_until_the_user_is_back(self, tray, monkeypatch):
        """Windows removes an icon's messages from the notification center along with the icon."""
        monkeypatch.setattr(notifier, "HIDE_AFTER_MS", 20)
        monkeypatch.setattr(notifier, "_in_front", lambda: False)
        notifier.notify("Encryption complete", "Done.")
        icon = tray.return_value
        assert not _wait_for(lambda: icon.hide.called, timeout=0.2)
        assert notifier._toaster is not None
        notifier._toaster._on_state(Qt.ApplicationState.ApplicationActive)
        assert _wait_for(lambda: icon.hide.called)

    def test_clicking_the_message_hides_the_icon(self, tray, monkeypatch):
        monkeypatch.setattr(notifier, "_in_front", lambda: False)
        notifier.notify("Encryption complete", "Done.")
        assert notifier._toaster is not None
        notifier._toaster._open_window()
        tray.return_value.hide.assert_called_once()

    def test_no_notification_area_logs_instead_of_raising(self, tray, logged):
        tray.isSystemTrayAvailable.return_value = False
        assert notifier.notify("Title", "Body") is None
        tray.assert_not_called()
        assert "not available" in logged.call_args[0][0]

    def test_missing_app_icon_logs_instead_of_raising(self, tray, logged):
        QApplication.setWindowIcon(QIcon())
        notifier.notify("Title", "Body")
        tray.assert_not_called()
        assert "icon" in logged.call_args[0][0]

    def test_a_deleted_tray_icon_is_logged_and_replaced_next_time(self, tray, logged):
        tray.return_value.show.side_effect = RuntimeError("Internal C++ object already deleted")
        notifier.notify("Title", "Body")
        assert notifier._toaster is None
        assert "already deleted" in logged.call_args[0][0]


class TestNoBareProgramNames:
    """Nothing in the run pipeline starts a program by a bare name, which Windows would look up in
    the app's own folder and the current folder first (A3)."""

    @pytest.mark.parametrize("module", [notifier, encrypt_ctrl, worker, folder_scanner, file_model, log_mod])
    def test_no_subprocess(self, module):
        source = inspect.getsource(module)
        assert "subprocess" not in source and "Popen" not in source and "os.system" not in source
