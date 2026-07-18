# splash_screen.py - modern startup splash showing live dependency-loading
# progress

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from gfglock.config.defaults import AppInfo
from gfglock.utils.logging import write_log

_FRAME_STYLE = (
    "#container { background: #16181d; border-radius: 18px;"
    " border: 1px solid #2a2d34; }"
)
_BAR_STYLE = (
    "QProgressBar { background: rgba(255,255,255,0.08); border: none;"
    " border-radius: 3px; }"
    "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    " stop:0 #0078d4, stop:1 #00b4d8); border-radius: 3px; }"
)


class SplashScreen(QWidget):
    """Frameless startup splash with a status label and progress bar."""

    def __init__(self, logo_path: str) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(440, 260)
        self._build_ui(logo_path)
        self._center_on_screen()

    def _build_ui(self, logo_path: str) -> None:
        """Assemble the logo, title, status text, and progress bar."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame(self)
        container.setObjectName("container")
        container.setStyleSheet(_FRAME_STYLE)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(6)

        logo = QLabel(container)
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            mode = Qt.TransformationMode.SmoothTransformation
            logo.setPixmap(pixmap.scaledToHeight(64, mode))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(logo)
        layout.addSpacing(14)

        title = QLabel(AppInfo.APP_NAME, container)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(
            "color: #f2f2f2; font-size: 17px; font-weight: 600;"
        )
        layout.addWidget(title)
        layout.addStretch()

        self._status = QLabel("Starting up...", container)
        self._status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status.setStyleSheet("color: #9aa0a6; font-size: 12px;")
        layout.addWidget(self._status)

        bar_row = QVBoxLayout()
        bar_row.setSpacing(4)

        self._bar = QProgressBar(container)
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(_BAR_STYLE)
        bar_row.addWidget(self._bar)

        self._percent = QLabel("0%", container)
        self._percent.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._percent.setStyleSheet("color: #6b7280; font-size: 10px;")
        bar_row.addWidget(self._percent)

        layout.addLayout(bar_row)

    def _center_on_screen(self) -> None:
        """Center the splash on the primary screen."""
        try:
            screen = self.screen()
            if screen is not None:
                geo = screen.geometry()
                x = geo.center().x() - self.width() // 2
                y = geo.center().y() - self.height() // 2
                self.move(x, y)
        except Exception as e:
            write_log(f"Splash center failed: {e}", level="critical")

    def set_stage(self, text: str, percent: int) -> None:
        """Update the status text and animate the bar to a new percent."""
        try:
            self._status.setText(text)
            self._percent.setText(f"{percent}%")
            anim = QPropertyAnimation(self._bar, b"value", self)
            anim.setDuration(280)
            anim.setStartValue(self._bar.value())
            anim.setEndValue(percent)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
        except Exception as e:
            write_log(f"Splash progress update failed: {e}", level="critical")

    def set_error(self, message: str) -> None:
        """Switch the status text into an error state."""
        try:
            self._status.setText(message)
            self._status.setStyleSheet("color: #f85149; font-size: 12px;")
        except Exception as e:
            write_log(f"Splash error display failed: {e}", level="critical")
