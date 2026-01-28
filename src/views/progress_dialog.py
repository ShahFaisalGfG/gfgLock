from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import WindowSizes, ButtonSizes, Spacing, StyleSheets, LabelSizes, scale_size, scale_value
from utils import resource_path, format_bytes, format_time, choose_scale
from widgets import CustomTitleBar
import time

REM_TIME_UPDATE_INTERVAL = 1.0  # Update remaining time display at most every 1 seconds

class ProgressDialog(QtWidgets.QDialog):
    # Time display update interval to avoid excessive calculations during encryption/decryption
    
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
        self._scale, self._unit, self._scaled_total = choose_scale(self.total_bytes)
        
        # Timing tracking
        self.start_time = time.time()
        self._last_speed_update_time = self.start_time
        self._last_speed_update_bytes = 0.0
        self._current_speed = 0.0  # bytes per second
        
        # Adaptive correction factor (learns from actual vs estimated time)
        self._correction_factor = 1.0  # Start with 1.0 (no correction)
        self._correction_measurements = []  # Store (actual_time, estimated_time) pairs
        self._min_elapsed_for_correction = 5.0  # Wait 5 seconds before calculating correction
        self._correction_locked = False  # Lock after collecting enough data
        
        # Time display update interval to avoid excessive calculations during encryption/decryption
        self._last_time_display_update = self.start_time

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

        # Combined progress label showing files and bytes on one row with time on the right
        total_formatted = format_bytes(total)
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))
        
        self.detail = QtWidgets.QLabel(f"Files: 0/{self.total_files} (0 B / {total_formatted})")
        self.detail.setStyleSheet(StyleSheets.DETAIL_LABEL)
        bottom_row.addWidget(self.detail)
        
        # Time label showing elapsed / estimated remaining time
        self.time_label = QtWidgets.QLabel("Time: 00:00:00 / calculating")
        self.time_label.setStyleSheet(StyleSheets.DETAIL_LABEL)
        # Align to the right
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]
        bottom_row.addWidget(self.time_label)
        layout.addLayout(bottom_row)

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
        
        # Update time display only at specified interval to avoid excessive calculations
        self._update_time_display(done_bytes, total_bytes)
    
    def _update_time_display(self, done_bytes: float, total_bytes: float) -> None:
        """Update the elapsed and estimated remaining time display.
        
        Uses adaptive correction factor to improve accuracy over time.
        Updates at most every REM_TIME_UPDATE_INTERVAL seconds to avoid
        slowing down encryption/decryption operations.
        
        Args:
            done_bytes: Number of bytes processed
            total_bytes: Total bytes to process
        """
        try:
            current_time = time.time()
            
            # Skip update if not enough time has passed since last update
            # This prevents excessive calculations during fast progress updates
            if current_time - self._last_time_display_update < REM_TIME_UPDATE_INTERVAL:
                return
            
            self._last_time_display_update = current_time
            elapsed = current_time - self.start_time
            
            # Calculate current speed (bytes per second) using a smoothed average
            # Update speed calculation every second or after significant progress
            time_since_last_update = current_time - self._last_speed_update_time
            bytes_since_last_update = done_bytes - self._last_speed_update_bytes
            
            if time_since_last_update >= 1.0 and bytes_since_last_update > 0:
                # Update speed every second
                self._current_speed = bytes_since_last_update / time_since_last_update
                self._last_speed_update_time = current_time
                self._last_speed_update_bytes = done_bytes
            
            # Calculate estimated time remaining
            remaining_bytes = max(0, total_bytes - done_bytes)
            if self._current_speed > 0 and remaining_bytes > 0:
                estimated_remaining = remaining_bytes / self._current_speed
                
                # Apply adaptive correction factor if available
                estimated_remaining *= self._correction_factor
                
                remaining_str = format_time(estimated_remaining)
            else:
                remaining_str = "--:--:--"
            
            elapsed_str = format_time(elapsed)
            self.time_label.setText(f"Time: {elapsed_str} / {remaining_str}")
            
            # Update correction factor based on actual vs predicted time
            # (Only during the first 10 seconds to capture initial performance patterns)
            if not self._correction_locked and elapsed > self._min_elapsed_for_correction:
                self._update_correction_factor(done_bytes, total_bytes, elapsed)
        except Exception:
            # Silently fail and keep previous time display
            pass
    
    def _update_correction_factor(self, done_bytes: float, total_bytes: float, elapsed: float) -> None:
        """
        Update the adaptive correction factor based on actual vs predicted time.
        
        This learns from the first 10 seconds of operation to adapt to system performance.
        """
        try:
            if done_bytes <= 0 or elapsed < self._min_elapsed_for_correction:
                return
            
            # Calculate actual throughput
            actual_speed = done_bytes / elapsed
            
            # Calculate what speed we initially predicted (total_bytes / estimated_total_time)
            # We use our current speed estimate to back-calculate our error
            if self._current_speed > 0:
                # Ratio of actual speed to estimated speed
                speed_ratio = actual_speed / self._current_speed
                
                # Store this measurement (we use speed ratio as a proxy for time correction)
                self._correction_measurements.append(speed_ratio)
                
                # After collecting 3+ measurements over 10+ seconds, lock in correction
                if len(self._correction_measurements) >= 3 and elapsed > 10.0:
                    # Calculate mean correction factor from measurements
                    import statistics
                    avg_ratio = statistics.mean(self._correction_measurements)
                    
                    # Apply the correction (inverse of speed ratio = time correction)
                    self._correction_factor = 1.0 / avg_ratio if avg_ratio > 0 else 1.0
                    
                    # Clamp between 0.5 and 2.0 to avoid extreme corrections
                    self._correction_factor = max(0.5, min(2.0, self._correction_factor))
                    
                    self._correction_locked = True
        except Exception:
            # Silently fail, keep default correction factor
            pass

