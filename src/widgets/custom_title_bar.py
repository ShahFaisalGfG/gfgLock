import os
import sys
from typing import Optional, cast

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import Spacing, ButtonSizes, FontSizes, WindowSizes, LabelSizes, scale_value, IconSizes


class CustomTitleBar(QtWidgets.QWidget):
    """A lightweight, themeable in-app title bar with basic window controls.

    Features:
    - Move window by dragging the title bar
    - Double-click to toggle maximize/restore
    - Minimize / Maximize / Close buttons
    - Exposes object names used by theme_manager.css selectors
    """

    def __init__(self, window_title: str, parent=None, show_min_max: bool = True):
        super().__init__(parent)
        self.setObjectName("custom_title_bar")
        # DPI-scaled height from config
        self.setFixedHeight(scale_value(LabelSizes.TITLE_BAR_HEIGHT))

        layout = QtWidgets.QHBoxLayout(self)
        # DPI-scaled margins from config: base (7, 0, 7, 0) at 96 DPI (10% reduction)
        layout.setContentsMargins(scale_value(Spacing.TITLE_BAR_MARGINS), 0, scale_value(Spacing.TITLE_BAR_MARGINS), 0)
        # DPI-scaled spacing from config: base 5 at 96 DPI (10% reduction)
        layout.setSpacing(scale_value(Spacing.TITLE_BAR_SPACING))

        # App icon + title
        icon_lbl = QtWidgets.QLabel()
        icon_lbl.setObjectName("title_bar_icon")
        icon_size = scale_value(IconSizes.MEDIUM)
        icon_lbl.setFixedSize(icon_size, icon_size)
        # Try to obtain the window icon (if set), otherwise fall back to bundled icon
        try:
            win = parent if parent is not None else self.window()
            icon = None
            if win is not None:
                icon = win.windowIcon()
            if icon is None or icon.isNull():
                # fallback to bundled icon path: prefer PyInstaller extraction dir (sys._MEIPASS)
                base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
                bundled = os.path.join(base, "assets", "icons", "gfgLock.png")
                if os.path.exists(bundled):
                    icon = QtGui.QIcon(bundled)
            if icon and not icon.isNull():
                # Use 2x resolution for crisp display on high-DPI screens
                pix = icon.pixmap(icon_size, icon_size)
                if pix and not pix.isNull():
                    icon_lbl.setPixmap(pix)
        except Exception:
            pass
        layout.addWidget(icon_lbl)

        self.title_label = QtWidgets.QLabel(window_title)
        self.title_label.setObjectName("title_bar_text")
        # Use explicit AlignmentFlag to satisfy static type checkers
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.title_label)
        layout.addStretch()

        # Minimize (show only if show_min_max is True)
        self.btn_minimize = QtWidgets.QPushButton("—")
        self.btn_minimize.setObjectName("title_bar_button")
        # DPI-scaled size from config
        btn_size_w = scale_value(ButtonSizes.TITLE_BAR_WIDTH)
        btn_size_h = scale_value(ButtonSizes.TITLE_BAR_HEIGHT)
        self.btn_minimize.setFixedSize(btn_size_w, btn_size_h)
        self.btn_minimize.clicked.connect(self.on_minimize)
        if show_min_max:
            layout.addWidget(self.btn_minimize)
        else:
            self.btn_minimize.hide()

        # Maximize / Restore (show only if show_min_max is True)
        self.btn_maximize = QtWidgets.QPushButton("☐")
        self.btn_maximize.setObjectName("title_bar_button")
        # DPI-scaled size: base (36, 28) at 96 DPI
        self.btn_maximize.setFixedSize(btn_size_w, btn_size_h)
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        if show_min_max:
            layout.addWidget(self.btn_maximize)
        else:
            self.btn_maximize.hide()

        # Close
        self.btn_close = QtWidgets.QPushButton("✕")
        self.btn_close.setObjectName("title_bar_close_button")
        # DPI-scaled size: base (36, 28) at 96 DPI
        self.btn_close.setFixedSize(btn_size_w, btn_size_h)
        self.btn_close.clicked.connect(self.on_close)
        layout.addWidget(self.btn_close)

        # State
        self._start_pos: Optional[QtCore.QPoint] = None
        self._start_geom: Optional[QtCore.QRect] = None
        # install window resizer for full-edge resizing
        # Get the top-level window and install event filter on it
        parent_window = self.window()
        if parent_window and isinstance(parent_window, QtWidgets.QWidget):
            try:
                self._resizer = _WindowResizer(parent_window)
                parent_window.installEventFilter(self._resizer)
            except Exception:
                self._resizer = None
        else:
            self._resizer = None

    def on_minimize(self) -> None:
        w = self.window()
        if w:
            w.showMinimized()

    def toggle_maximize(self) -> None:
        w = self.window()
        if w:
            if w.isMaximized():
                w.showNormal()
            else:
                w.showMaximized()

    def on_close(self) -> None:
        w = self.window()
        if w:
            w.close()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        # Record starting position and geometry for move operations.
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.globalPosition().toPoint()
            w = self.window()
            if w is not None:
                self._start_geom = w.geometry()
            else:
                self._start_geom = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        # Only proceed if we have a start position and the left button is pressed.
        if self._start_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton) != 0:
            w = self.window()
            if w is None or self._start_geom is None:
                return
            dp = event.globalPosition().toPoint() - self._start_pos
            try:
                # If maximized, restore to normal and start moving
                if w.isMaximized():
                    w.showNormal()
                    # adjust offset after restore
                    self._start_pos = event.globalPosition().toPoint()
                    self._start_geom = w.geometry()
                new_geom = self._start_geom
                new_pos = new_geom.topLeft() + dp
                w.move(new_pos)
            except Exception:
                pass
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        # Stop any in-progress window move when the left button is released.
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = None
            self._start_geom = None
        super().mouseReleaseEvent(event)


class _WindowResizer(QtCore.QObject):
    """Event-filter helper that enables full-edge resizing for a window.

    Installs on the target window and handles mouse move/press/release events
    to allow resizing from any window edge or corner. This is a simple,
    cross-platform implementation sufficient for common use.
    """

    def __init__(self, window: QtWidgets.QWidget, margin: Optional[int] = None):
        super().__init__(window)
        self._w = window
        self._margin = margin if margin is not None else Spacing.WINDOW_RESIZE_MARGIN
        self._resizing = False
        self._resize_edges = 0
        self._start_rect: Optional[QtCore.QRect] = None
        self._start_pos: Optional[QtCore.QPoint] = None
        
        # Enable mouse tracking so we get mouseMoveEvents even when no button is pressed
        self._w.setMouseTracking(True)
        
        # Also enable mouse tracking on all child widgets to ensure events propagate
        for child in self._w.findChildren(QtWidgets.QWidget):
            child.setMouseTracking(True)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        try:
            # Only filter events from the target window itself or its child widgets
            # Check if obj is the window or a child of the window
            if isinstance(obj, QtWidgets.QWidget):
                if obj == self._w or self._w.isAncestorOf(obj):
                    et = event.type()
                    if et == QtCore.QEvent.Type.MouseMove:
                        return self._handle_move(event)
                    if et == QtCore.QEvent.Type.MouseButtonPress:
                        return self._handle_press(event)
                    if et == QtCore.QEvent.Type.MouseButtonRelease:
                        return self._handle_release(event)
                    if et == QtCore.QEvent.Type.Leave:
                        # Ensure any override cursor is cleared when mouse leaves window
                        self._clear_override_cursors()
            return False
        except Exception:
            return False

    def _edge_flags(self, pos: QtCore.QPoint) -> int:
        """Check if pos is near window edges. pos should be in local window coordinates."""
        r = self._w.rect()
        x, y = pos.x(), pos.y()
        left = x <= self._margin
        right = x >= r.width() - self._margin
        top = y <= self._margin
        bottom = y >= r.height() - self._margin
        flags = 0
        if left:
            flags |= 1
        if right:
            flags |= 2
        if top:
            flags |= 4
        if bottom:
            flags |= 8
        return flags

    def _cursor_for_edges(self, flags: int) -> QtCore.Qt.CursorShape:
        if flags & 1 and flags & 4:
            return Qt.CursorShape.SizeFDiagCursor
        if flags & 2 and flags & 8:
            return Qt.CursorShape.SizeFDiagCursor
        if flags & 1 and flags & 8:
            return Qt.CursorShape.SizeBDiagCursor
        if flags & 2 and flags & 4:
            return Qt.CursorShape.SizeBDiagCursor
        if flags & (1 | 2):
            return Qt.CursorShape.SizeHorCursor
        if flags & (4 | 8):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _clear_override_cursors(self) -> None:
        """Restore all QApplication override cursors to ensure cursor returns to normal.

        There can be multiple stacked override cursors; loop until none remain.
        """
        try:
            # Keep restoring until overrideCursor is None
            while QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()
        except Exception:
            try:
                QtWidgets.QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def _handle_move(self, event: QtCore.QEvent) -> bool:
        # event is QEvent; cast to QMouseEvent for mouse-specific APIs
        if self._w.isMaximized() or not self._w.isEnabled():
            return False
        me = cast(QtGui.QMouseEvent, event)
        # Convert global position to local window coordinates (handles events from child widgets)
        global_pos = me.globalPosition().toPoint()
        local_pos = self._w.mapFromGlobal(global_pos)
        
        if self._resizing and self._start_rect is not None and self._start_pos is not None:
            # perform resize using global coordinates
            delta = global_pos - self._start_pos
            rect = QtCore.QRect(self._start_rect)
            if self._resize_edges & 1:  # left
                rect.setLeft(rect.left() + delta.x())
            if self._resize_edges & 2:  # right
                rect.setRight(rect.right() + delta.x())
            if self._resize_edges & 4:  # top
                rect.setTop(rect.top() + delta.y())
            if self._resize_edges & 8:  # bottom
                rect.setBottom(rect.bottom() + delta.y())
            # enforce minimum size
            minw = self._w.minimumWidth() or 100
            minh = self._w.minimumHeight() or 100
            if rect.width() < minw:
                rect.setWidth(minw)
            if rect.height() < minh:
                rect.setHeight(minh)
            self._w.setGeometry(rect)
            return True

        # not resizing: update cursor based on local position
        flags = self._edge_flags(local_pos)
        cursor = self._cursor_for_edges(flags)
        if cursor != Qt.CursorShape.ArrowCursor:
            QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(cursor))
        else:
            QtWidgets.QApplication.restoreOverrideCursor()
        return False

    def _handle_press(self, event: QtCore.QEvent) -> bool:
        me = cast(QtGui.QMouseEvent, event)
        if me.button() != Qt.MouseButton.LeftButton:
            return False
        if self._w.isMaximized() or not self._w.isEnabled():
            return False
        # Convert global position to local window coordinates
        global_pos = me.globalPosition().toPoint()
        local_pos = self._w.mapFromGlobal(global_pos)
        flags = self._edge_flags(local_pos)
        if flags == 0:
            return False
        # start resizing
        self._resizing = True
        self._resize_edges = flags
        self._start_rect = self._w.geometry()
        self._start_pos = global_pos  # Store global position for resize delta calculation
        return True

    def _handle_release(self, event: QtCore.QEvent) -> bool:
        me = cast(QtGui.QMouseEvent, event)
        if me.button() != Qt.MouseButton.LeftButton:
            return False
        if self._resizing:
            self._resizing = False
            self._start_rect = None
            self._start_pos = None
            # Clear any override cursors to return cursor to arrow
            self._clear_override_cursors()
            return True
        return False


def show_message(parent: Optional[QtWidgets.QWidget], title: str, text: str, *,
                 icon: str = "info", buttons: str = "ok"):
    """Show a simple modal message dialog using `CustomTitleBar`.

    icon: 'info'|'warning'|'error'|'question'
    buttons: 'ok' or 'yesno'
    Returns True for Yes in 'yesno', False for No, None otherwise.
    """
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)  # type: ignore[attr-defined]
    dlg.setModal(True)
    dlg.setWindowTitle(title)
    # Ensure message dialogs have the app icon so CustomTitleBar shows it
    try:
        # prefer parent's window icon if available
        if parent is not None and isinstance(parent, QtWidgets.QWidget):
            win_icon = parent.windowIcon()
            if win_icon and not win_icon.isNull():
                dlg.setWindowIcon(win_icon)
            else:
                bundled = os.path.join(os.path.dirname(__file__), "assets", "icons", "gfgLock.png")
                if os.path.exists(bundled):
                    dlg.setWindowIcon(QtGui.QIcon(bundled))
        else:
            bundled = os.path.join(os.path.dirname(__file__), "assets", "icons", "gfgLock.png")
            if os.path.exists(bundled):
                dlg.setWindowIcon(QtGui.QIcon(bundled))
    except Exception:
        pass
    # Make the message dialog a bit larger and give it comfortable padding
    try:
        # DPI-scaled size from config
        dlg_w, dlg_h = scale_value(WindowSizes.MESSAGE_DIALOG_WIDTH), scale_value(WindowSizes.MESSAGE_DIALOG_HEIGHT)
        dlg.setMinimumSize(dlg_w, dlg_h)
        dlg.resize(dlg_w, dlg_h)
    except Exception:
        pass
    try:
        tb = CustomTitleBar(title, dlg, show_min_max=False)
        layout = QtWidgets.QVBoxLayout(dlg)
        # DPI-scaled compact padding from config
        margin = scale_value(Spacing.COMPACT_DIALOG_PADDING)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))
        layout.insertWidget(0, tb)
    except Exception:
        layout = QtWidgets.QVBoxLayout(dlg)

    # Body
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"font-size:{FontSizes.COMPACT_BODY}pt;")
    layout.addWidget(lbl)

    # Buttons
    if buttons == "yesno":
        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))
        btns.addStretch()
        yes = QtWidgets.QPushButton("Yes")
        no = QtWidgets.QPushButton("No")
        # Apply bold styling to confirmation buttons with compact style
        bold_style = ButtonSizes.DIALOG_BUTTON_STYLE + ButtonSizes.BUTTON_BOLD_WEIGHT
        yes.setStyleSheet(bold_style)
        no.setStyleSheet(bold_style)
        yes.setMinimumHeight(scale_value(ButtonSizes.DIALOG_BUTTON_HEIGHT))
        no.setMinimumHeight(scale_value(ButtonSizes.DIALOG_BUTTON_HEIGHT))
        btns.addWidget(yes)
        btns.addWidget(no)
        layout.addLayout(btns)

        def _yes():
            dlg.done(1)

        def _no():
            dlg.done(0)

        yes.clicked.connect(_yes)
        no.clicked.connect(_no)
        res = dlg.exec()
        return True if res == 1 else False
    else:
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        # Apply bold styling to OK button with compact style
        ok_button = btns.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setStyleSheet(ButtonSizes.DIALOG_BUTTON_STYLE + ButtonSizes.BUTTON_BOLD_WEIGHT)
            ok_button.setMinimumHeight(scale_value(ButtonSizes.DIALOG_BUTTON_HEIGHT))
        # place the ok button in a right-aligned footer for consistency
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(scale_value(Spacing.COMPACT_DIALOG_SPACING))
        footer.addStretch()
        footer.addWidget(btns)
        layout.addLayout(footer)
        dlg.exec()
        return None
