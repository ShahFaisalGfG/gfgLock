from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import WindowSizes, scale_size, scale_value
from utils import load_settings, write_general_log, write_critical_log, write_log, resource_path
from widgets import CustomTitleBar


class ProgressDialog(QtWidgets.QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)  # type: ignore[attr-defined]
        self.setWindowTitle("Progress")
        # Set minimum size and initial size - allow user to resize larger
        # DPI-scaled sizes from config
        min_w, min_h = scale_size(WindowSizes.PROGRESS_DIALOG_WIDTH, WindowSizes.PROGRESS_DIALOG_MIN_HEIGHT)
        resize_w, resize_h = scale_size(WindowSizes.PROGRESS_DIALOG_WIDTH, WindowSizes.PROGRESS_DIALOG_HEIGHT)
        self.setMinimumSize(min_w, min_h)
        self.resize(resize_w, resize_h)
        self.setSizeGripEnabled(False)  # We use QSizeGrip manually, prevent auto-resize
        self.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        # custom title bar
        try:
            self.custom_title_bar = CustomTitleBar("Progress", self, show_min_max=False)
            layout.insertWidget(0, self.custom_title_bar)
        except Exception:
            pass

        self.label_current = QtWidgets.QLabel("Current file:")
        # Prevent this label from forcing the dialog to grow for long filenames.
        try:
            self.label_current.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            self.label_current.setWordWrap(False)
            self.label_current.setMinimumWidth(0)
            # DPI-scaled height: base 18 at 96 DPI (10% reduction)
            self.label_current.setFixedHeight(scale_value(18))
        except Exception:
            pass
        layout.addWidget(self.label_current)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, max(1, total))
        layout.addWidget(self.progress_bar)

        self.detail = QtWidgets.QLabel(f"0/{total}")
        layout.addWidget(self.detail)

        self.logs = QtWidgets.QPlainTextEdit()
        self.logs.setReadOnly(True)
        # Prefer horizontal scrolling for long lines, but constrain width
        try:
            self.logs.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            self.logs.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Prevent the logs widget from growing the dialog based on content length.
        # Ignore content-based size adjustments and allow the widget to expand
        # only when the user resizes the dialog.
        try:
            self.logs.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
            self.logs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
            # DPI-scaled minimum height: base 90 at 96 DPI (10% reduction)
            self.logs.setMinimumHeight(scale_value(90))
        except Exception:
            pass
        layout.addWidget(self.logs, 1)  # Stretch factor of 1 to fill available space

        # Resize grip row (above the bottom button row) to match EncryptDialog layout
        try:
            grip_h = QtWidgets.QHBoxLayout()
            grip_h.addStretch()
            grip = QtWidgets.QSizeGrip(self)
            grip_h.addWidget(grip)
            layout.addLayout(grip_h)
        except Exception:
            pass

        # Bottom row: place Cancel aligned to the right (same position as Start in EncryptDialog)
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        footer_h = QtWidgets.QHBoxLayout()
        footer_h.addStretch()
        footer_h.addWidget(self.btn_cancel)
        layout.addLayout(footer_h)

    def showEvent(self, a0):
        """Prevent automatic resizing when dialog is shown."""
        super().showEvent(a0)
        # Reset to minimum size after showing to prevent layout-driven expansion
        # DPI-scaled size from config
        resize_w, resize_h = scale_size(WindowSizes.PROGRESS_DIALOG_WIDTH, WindowSizes.PROGRESS_DIALOG_HEIGHT)
        self.resize(resize_w, resize_h)

