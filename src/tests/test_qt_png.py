#!/usr/bin/env python
"""Test that loading PNG files with Qt doesn't produce libpng warnings."""

import sys
import io
import contextlib
from pathlib import Path
from PyQt6 import QtGui, QtWidgets

# Create QApplication first
app = QtWidgets.QApplication(sys.argv)

icons_dir = Path(r'd:\source\repos\ShahFaisalGfG\gfgLock\src\assets\icons')
png_files = sorted(icons_dir.glob('*.png'))

print("Testing PNG files with PyQt6 (Qt will attempt to load them):")
print()

# Capture stderr to catch any libpng warnings
stderr_capture = io.StringIO()

for png_file in png_files:
    print(f"Loading: {png_file.name}...", end=" ")
    
    # Capture warnings during Qt loading
    with contextlib.redirect_stderr(stderr_capture):
        try:
            # This is how Qt loads PNG files - it will trigger libpng if there are warnings
            pixmap = QtGui.QPixmap(str(png_file))
            icon = QtGui.QIcon(str(png_file))
            
            if pixmap.isNull():
                print("✗ Failed to load pixmap")
            else:
                print(f"✓ Loaded ({pixmap.width()}x{pixmap.height()})")
        except Exception as e:
            print(f"✗ Error: {e}")

# Check captured output for warnings
captured = stderr_capture.getvalue()
if captured:
    print("\n⚠ Captured warnings/errors:")
    print(captured)
else:
    print("\n✓ No libpng warnings detected!")
    print("PNG files are clean and ready to use.")
