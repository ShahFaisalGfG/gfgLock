# Edge-Resize Bug Fix Summary

## Issue

Edge-resize functionality (dragging window edges to resize) was not working, even though drag-to-move on the title bar was functioning correctly.

## Root Causes

1. **Event Filter Installation Bug**: The code was checking `if parent is not None` but then trying to install the filter on `parent_window` (which was never checked). This caused the event filter to not be installed at all.

2. **Coordinate System Mismatch**: Mouse events from child widgets had coordinates relative to that widget, not the window. Using `me.pos()` directly was incorrect - needed to convert to global coordinates and then map back to local window coordinates.

3. **Event Filter Object Check Too Strict**: The event filter was only accepting events where `obj is self._w`, which excluded events from child widgets like the title bar.

4. **Mouse Tracking Disabled**: Without mouse tracking enabled on the window and its children, `MouseMove` events weren't being generated when the mouse moved but no button was pressed.

## Fixes Applied

### 1. Fixed Installation Target (Line 65-72)

```python
# BEFORE:
parent_window = self.window()
if parent is not None and isinstance(parent, QtWidgets.QWidget):
    self._resizer = _WindowResizer(parent)
    parent.installEventFilter(self._resizer)

# AFTER:
parent_window = self.window()
if parent_window and isinstance(parent_window, QtWidgets.QWidget):
    self._resizer = _WindowResizer(parent_window)
    parent_window.installEventFilter(self._resizer)
```

### 2. Enabled Mouse Tracking (Line 147-153)

```python
# Added in _WindowResizer.__init__:
self._w.setMouseTracking(True)
for child in self._w.findChildren(QtWidgets.QWidget):
    child.setMouseTracking(True)
```

### 3. Fixed Event Filter Object Check (Line 160-168)

```python
# BEFORE: if obj is not self._w: return False
# AFTER:
if isinstance(obj, QtWidgets.QWidget):
    if obj == self._w or self._w.isAncestorOf(obj):
        # Process event...
```

### 4. Fixed Coordinate System (Line 203-208, 253-255)

```python
# BEFORE: pos = me.pos()
# AFTER:
global_pos = me.globalPos()
local_pos = self._w.mapFromGlobal(global_pos)
# Use local_pos for edge detection, global_pos for resize delta
```

## Testing

The fixes enable:

- Dragging window edges to resize (left, right, top, bottom edges)
- Dragging window corners to resize diagonally
- Proper cursor shape indication (resize cursors appear at edges)
- Minimum size enforcement during resize
- Works across frameless windows (MainWindow, dialogs, etc.)

## Files Modified

- [src/custom_title_bar.py](src/custom_title_bar.py): Fixed `CustomTitleBar.__init__`, `_WindowResizer.__init__`, `_WindowResizer.eventFilter()`, `_WindowResizer._handle_move()`, and `_WindowResizer._handle_press()`
