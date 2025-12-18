#!/usr/bin/env python3
"""Quick test script to verify edge-resize functionality."""

import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from src.custom_title_bar import CustomTitleBar

class TestWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: #f0f0f0;")
        self.setWindowTitle("Edge Resize Test")
        self.setGeometry(100, 100, 600, 400)
        self.setMinimumSize(300, 200)
        
        # Create layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Add custom title bar
        title_bar = CustomTitleBar("Edge Resize Test", self)
        layout.addWidget(title_bar)
        
        # Add content
        content = QtWidgets.QLabel("Try dragging the window edges to resize.\nYou should see resize cursors at the edges.")
        content.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(content)
        
        self.show()

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    sys.exit(app.exec_())
