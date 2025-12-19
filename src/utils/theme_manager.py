# theme_manager.py
# Theme management for gfgLock GUI

import sys
from typing import Optional
from PyQt5 import QtWidgets
from utils.gfg_helpers import load_settings


def get_system_theme() -> str:
    """Detect system theme preference (light/dark).
    
    Returns "dark" or "light" based on system settings.
    Currently returns "light" as a safe default for cross-platform compatibility.
    """
    try:
        # Windows 10+ dark mode detection
        if sys.platform == "win32":
            try:
                import winreg
                registry_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                registry_value = "AppsUseLightTheme"
                reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path)
                value, _ = winreg.QueryValueEx(reg_key, registry_value)
                return "light" if value == 1 else "dark"
            except Exception:
                pass
    except Exception:
        pass
    
    return "light"  # Safe default


def get_light_theme_stylesheet() -> str:
    """Get the light theme stylesheet."""
    return """
    QWidget {
        background-color: #ffffff;
        color: #000000;
    }
    
    QMainWindow {
        background-color: #ffffff;
    }
    
    QPushButton {
        background-color: #f0f0f0;
        color: #000000;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        padding: 5px;
        font-weight: 500;
    }
    
    QPushButton:hover {
        background-color: #e0e0e0;
        border: 1px solid #c0c0c0;
    }
    
    QPushButton:pressed {
        background-color: #d0d0d0;
    }
    
    QPushButton:disabled {
        color: #999999;
        background-color: #f5f5f5;
        border: 1px solid #e0e0e0;
    }
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        padding: 4px;
    }
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #0078d4;
    }
    
    QComboBox {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        padding: 4px;
    }
    
    QComboBox:focus {
        border: 2px solid #0078d4;
    }
    
    QComboBox:disabled {
        color: #999999;
        background-color: #f5f5f5;
        border: 1px solid #e0e0e0;
    }
        border: none;
    }
    
    QListWidget {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
    }
    
    QListWidget::item:selected {
        background-color: #0078d4;
        color: #ffffff;
    }
    
    QProgressBar {
        background-color: #f0f0f0;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        text-align: center;
        color: #000000;
    }
    
    QProgressBar::chunk {
        background-color: #0078d4;
        border-radius: 2px;
    }
    
    QCheckBox {
        color: #000000;
    }
    
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
    
    QCheckBox::indicator:unchecked {
        background-color: #ffffff;
        border: 1px solid #d0d0d0;
        border-radius: 3px;
    }
    
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border: 1px solid #0078d4;
        border-radius: 3px;
    }
    
    QLabel {
        color: #000000;
    }
    
    #title_label {
        color: #2b2b2b;
    }
    
    #subtitle_label {
        color: #666666;
    }
    
    #header_widget {
        background-color: #ffffff;
    }
    
    #custom_title_bar {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5f5f5, stop:1 #e8e8e8);
        border-bottom: 1px solid #c0c0c0;
    }
    
    #title_bar_text {
        color: #000000;
        font-weight: 500;
    }
    
    #title_bar_button {
        background-color: #f0f0f0;
        color: #000000;
        border: none;
        padding: 0px;
        margin: 0px;
        border-radius: 2px;
        font-size: 10pt;
    }
    
    #title_bar_button:hover {
        background-color: #e0e0e0;
    }
    
    #title_bar_button:pressed {
        background-color: #d0d0d0;
    }
    
    #title_bar_close_button:hover {
        background-color: #d32f2f;
        color: #ffffff;
    }
    
    #title_bar_close_button:pressed {
        background-color: #b71c1c;
    }
    
    QGroupBox {
        color: #000000;
        border: 1px solid #d0d0d0;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 3px;
    }
    
    QTabWidget::pane {
        border: 1px solid #d0d0d0;
    }
    
    QTabBar::tab {
        background-color: #f0f0f0;
        color: #000000;
        border: 1px solid #d0d0d0;
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        padding: 6px 12px;
    }
    
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #0078d4;
        font-weight: 500;
    }
    
    QTabBar::tab:hover {
        background-color: #e8e8e8;
    }
    
    QDialog {
        background-color: #ffffff;
    }
    
    QMessageBox {
        background-color: #ffffff;
    }
    """


def get_dark_theme_stylesheet() -> str:
    """Get the dark theme stylesheet."""
    return """
    QWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    
    QMainWindow {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    
    QMainWindow::title {
        background-color: #2d2d2d;
        color: #e0e0e0;
    }
    
    QPushButton {
        background-color: #3d3d3d;
        color: #e0e0e0;
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 5px;
        font-weight: 500;
    }
    
    QPushButton:hover {
        background-color: #454545;
        border: 1px solid #666666;
    }
    
    QPushButton:pressed {
        background-color: #2d2d2d;
    }
    
    /* Disabled state styling for dark theme */
    QPushButton:disabled {
        color: #8a8a8a;
        background-color: #2a2a2a;
        border: 1px solid #444444;
    }
    
    QLineEdit, QTextEdit, QPlainTextEdit {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 4px;
    }
    
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 2px solid #0078d4;
    }
    
    QComboBox {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #555555;
        border-radius: 4px;
        padding: 4px;
    }
    
    QComboBox:focus {
        border: 2px solid #0078d4;
    }
    QComboBox:disabled {
        color: #8a8a8a;
        background-color: #2a2a2a;
        border: 1px solid #444444;
    }
    
    QComboBox::drop-down {
        border: none;
    }
    
    QComboBox QAbstractItemView {
        background-color: #2d2d2d;
        color: #e0e0e0;
        selection-background-color: #0078d4;
        border: 1px solid #555555;
    }
    
    QListWidget {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #555555;
        border-radius: 4px;
    }
    
    QListWidget::item:selected {
        background-color: #0078d4;
        color: #ffffff;
    }
    
    QProgressBar {
        background-color: #3d3d3d;
        border: 1px solid #555555;
        border-radius: 4px;
        text-align: center;
        color: #e0e0e0;
    }
    
    QProgressBar::chunk {
        background-color: #0078d4;
        border-radius: 2px;
    }
    
    QCheckBox {
        color: #e0e0e0;
    }
    
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
    
    QCheckBox::indicator:unchecked {
        background-color: #2d2d2d;
        border: 1px solid #555555;
        border-radius: 3px;
    }
    
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border: 1px solid #0078d4;
        border-radius: 3px;
    }
    
    QLabel {
        color: #e0e0e0;
    }
    
    #title_label {
        color: #e0e0e0;
    }
    
    #subtitle_label {
        color: #b0b0b0;
    }
    
    #header_widget {
        background-color: #1e1e1e;
    }
    
    #custom_title_bar {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #323232, stop:1 #272727);
        border-bottom: 1px solid #1a1a1a;
    }
    
    #title_bar_text {
        color: #e0e0e0;
        font-weight: 500;
    }
    
    #title_bar_button {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: none;
        padding: 0px;
        margin: 0px;
        border-radius: 2px;
        font-size: 10pt;
    }
    
    #title_bar_button:hover {
        background-color: #3d3d3d;
    }
    
    #title_bar_button:pressed {
        background-color: #454545;
    }
    
    #title_bar_close_button:hover {
        background-color: #d32f2f;
        color: #ffffff;
    }
    
    #title_bar_close_button:pressed {
        background-color: #b71c1c;
    }
    
    QGroupBox {
        color: #e0e0e0;
        border: 1px solid #555555;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 3px;
    }
    
    QTabWidget::pane {
        border: 1px solid #555555;
    }
    
    QTabBar::tab {
        background-color: #3d3d3d;
        color: #e0e0e0;
        border: 1px solid #555555;
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        padding: 6px 12px;
    }
    
    QTabBar::tab:selected {
        background-color: #2d2d2d;
        color: #0078d4;
        font-weight: 500;
    }
    
    QTabBar::tab:hover {
        background-color: #454545;
    }
    
    QDialog {
        background-color: #1e1e1e;
    }
    
    QMessageBox {
        background-color: #1e1e1e;
    }
    
    QScrollBar:vertical {
        background-color: #3d3d3d;
        border: 1px solid #555555;
    }
    
    QScrollBar::handle:vertical {
        background-color: #555555;
        border-radius: 4px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: #666666;
    }
    
    QScrollBar:horizontal {
        background-color: #3d3d3d;
        border: 1px solid #555555;
    }
    
    QScrollBar::handle:horizontal {
        background-color: #555555;
        border-radius: 4px;
    }
    
    QScrollBar::handle:horizontal:hover {
        background-color: #666666;
    }
    """


def apply_theme(app: Optional[QtWidgets.QApplication] = None, theme: Optional[str] = None) -> None:
    """Apply theme to the application.
    
    Args:
        app: QApplication instance (can be None, will use instance())
        theme: "system", "light", or "dark". If None, loads from settings.
    """
    if app is None:
        app_instance = QtWidgets.QApplication.instance()
        if app_instance is None or not isinstance(app_instance, QtWidgets.QApplication):
            return
        app = app_instance
    
    if theme is None:
        settings = load_settings()
        theme = settings.get("theme", "system")
    
    # Resolve system theme
    if theme == "system":
        theme = get_system_theme()
    
    # Apply stylesheet
    if theme == "dark":
        stylesheet = get_dark_theme_stylesheet()
    else:
        stylesheet = get_light_theme_stylesheet()
    
    app.setStyleSheet(stylesheet)
