from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import WindowSizes, ButtonSizes, FontSizes, Spacing, StyleSheets, LabelSizes, scale_size, scale_value
from utils import load_settings, write_general_log, write_critical_log, write_log, resource_path
from widgets import CustomTitleBar


def format_bytes(bytes_val: float) -> str:
    """Convert bytes to human-readable format (B, KB, MB, GB)."""
    bytes_val = float(bytes_val)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val = bytes_val / 1024
    return f"{bytes_val:.1f} TB"


def _choose_scale(total_bytes: float) -> tuple:
    """Choose a scale (power of 1024) so the scaled total fits in a 32-bit int.

    Returns (scale, unit, scaled_total)
    """
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    scaled = float(total_bytes)
    idx = 0
    # Reduce until it fits into signed 32-bit range
    MAX_INT32 = 2_147_483_647
    while scaled > MAX_INT32 and idx < len(units) - 1:
        # ceil division to retain progress granularity
        scaled = (scaled + 1023) / 1024
        idx += 1

    scale = 1024 ** idx
    unit = units[idx]
    return scale, unit, int(scaled)

class ProgressDialog(QtWidgets.QDialog):
    def __init__(self, total, parent=None, total_files=0):
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

        # Store total bytes for progress display (total is now in bytes, not file count)
        self.total_bytes = float(total)
        # Store total files for file count display
        self.total_files = int(total_files)
        # Track current done bytes for combined display
        self._current_done_bytes = 0.0
        # Choose scale so the progress bar range fits in 32-bit signed int
        self._scale, self._unit, self._scaled_total = _choose_scale(self.total_bytes)

        layout = QtWidgets.QVBoxLayout(self)
        # Set compact margins and spacing
        layout.setContentsMargins(scale_value(Spacing.COMPACT_DIALOG_PADDING), scale_value(Spacing.COMPACT_DIALOG_PADDING), scale_value(Spacing.COMPACT_DIALOG_PADDING), scale_value(Spacing.COMPACT_DIALOG_PADDING))
        layout.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))

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
            # DPI-scaled height from config
            self.label_current.setFixedHeight(scale_value(LabelSizes.CURRENT_FILE_HEIGHT))
        except Exception:
            pass
        layout.addWidget(self.label_current)

        self.progress_bar = QtWidgets.QProgressBar()
        # Use the scaled total for the progress bar range to avoid overflow
        self.progress_bar.setRange(0, max(1, self._scaled_total))
        layout.addWidget(self.progress_bar)

        # Combined progress label showing files and bytes on one row (e.g., "Files: 0/5 (0 B / 2.0 GB)")
        total_formatted = format_bytes(total)
        self.detail = QtWidgets.QLabel(f"Files: 0/{self.total_files} (0 B / {total_formatted})")
        self.detail.setStyleSheet(StyleSheets.DETAIL_LABEL)
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
            # DPI-scaled minimum height from config
            self.logs.setMinimumHeight(scale_value(LabelSizes.LOGS_MIN_HEIGHT))
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
        # Apply bold styling to cancel button with compact style
        self.btn_cancel.setStyleSheet(ButtonSizes.DIALOG_BUTTON_STYLE + ButtonSizes.BUTTON_BOLD_WEIGHT)
        self.btn_cancel.setMinimumHeight(scale_value(ButtonSizes.DIALOG_BUTTON_HEIGHT))
        footer_h = QtWidgets.QHBoxLayout()
        footer_h.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))
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

    def update_progress(self, done_bytes: float, total_bytes: float, done_files: int = 0) -> None:
        """Update progress bar with byte counts and human-readable display.
        
        Args:
            done_bytes: Number of bytes processed so far
            total_bytes: Total bytes to process (should match self.total_bytes)
            done_files: Number of files completed (optional, defaults to 0)
        """
        # Store current done bytes for combined display updates
        self._current_done_bytes = float(done_bytes)
        
        # Ensure progress reaches 100% when done
        if done_bytes >= total_bytes:
            done_scaled = self._scaled_total
        else:
            try:
                # Use float division for proper rounding instead of truncation
                done_scaled = min(int(float(done_bytes) / self._scale), self._scaled_total)
            except Exception:
                done_scaled = 0
        
        self.progress_bar.setValue(done_scaled)
        done_formatted = format_bytes(done_bytes)
        total_formatted = format_bytes(total_bytes)
        # Combine files and bytes in one label
        self.detail.setText(f"Files: {done_files}/{self.total_files} ({done_formatted} / {total_formatted})")

