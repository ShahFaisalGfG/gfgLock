# preferences.py
# Preferences/Settings window for gfgLock

import os
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt
from utils.gfg_helpers import load_settings, save_settings, get_cpu_thread_count, clear_logs, get_logs_dir, get_general_log_file, get_critical_log_file
from widgets.custom_title_bar import CustomTitleBar
import subprocess
from datetime import datetime


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


class PreferencesWindow(QtWidgets.QDialog):
    """Preferences window for gfgLock settings."""
    
    settings_changed = QtCore.pyqtSignal(dict)  # Emitted when settings are saved
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = load_settings()
        self.init_ui()
        self.load_settings_to_ui()
    
    def init_ui(self):
        """Initialize the UI."""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  # type: ignore[attr-defined]
        self.setWindowTitle("Preferences")
        self.setWindowIcon(QtGui.QIcon(resource_path("../assets/icons/gfgLock.png")))
        self.setModal(True)
        self.resize(600, 700)
        
        # Main layout with tab widget
        main_layout = QtWidgets.QVBoxLayout(self)

        # Insert custom title bar
        try:
            self.custom_title_bar = CustomTitleBar("Preferences", self)
            main_layout.insertWidget(0, self.custom_title_bar)
        except Exception:
            pass
        
        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.tab_widget.addTab(self.create_appearance_tab(), "Appearance")
        self.tab_widget.addTab(self.create_encryption_tab(), "Encryption")
        self.tab_widget.addTab(self.create_decryption_tab(), "Decryption")
        self.tab_widget.addTab(self.create_advanced_tab(), "Advanced")

        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        self.btn_reset = QtWidgets.QPushButton("Reset to Defaults")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_apply = QtWidgets.QPushButton("Apply")
        self.btn_save = QtWidgets.QPushButton("Save")
        
        button_layout.addWidget(self.btn_reset)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_apply)
        button_layout.addWidget(self.btn_save)
        
        main_layout.addLayout(button_layout)
        # add resize grip so user can resize the frameless dialog
        try:
            grip = QtWidgets.QSizeGrip(self)
            # use explicit AlignmentFlag to satisfy static type checkers
            main_layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight)
        except Exception:
            pass
        
        # Connect signals
        self.btn_reset.clicked.connect(self.reset_to_defaults)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self.apply_settings)
        self.btn_save.clicked.connect(self.save_and_close)
    
    def create_appearance_tab(self):
        """Create appearance settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Theme selection
        theme_group = QtWidgets.QGroupBox("Theme")
        theme_layout = QtWidgets.QVBoxLayout()
        
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItem("System (Default)", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        
        theme_layout.addWidget(QtWidgets.QLabel("Select Theme:"))
        theme_layout.addWidget(self.theme_combo)
        theme_group.setLayout(theme_layout)
        
        layout.addWidget(theme_group)
        layout.addStretch()
        
        return widget
    
    def create_encryption_tab(self) -> QtWidgets.QWidget:
        """Create encryption settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        group = QtWidgets.QGroupBox("Encryption Settings")
        group_layout = QtWidgets.QFormLayout()
        
        # CPU Threads
        total_threads = get_cpu_thread_count()
        max_safe = max(total_threads - 1, 1)
        
        self.enc_threads_combo = QtWidgets.QComboBox()
        for i in range(1, max_safe + 1):
            self.enc_threads_combo.addItem(str(i), i)
        
        group_layout.addRow("CPU Threads:", self.enc_threads_combo)
        
        # Chunk Size
        self.enc_chunk_combo = QtWidgets.QComboBox()
        chunks = [
            ("1 MB", 1 * 1024 * 1024),
            ("8 MB (default)", 8 * 1024 * 1024),
            ("16 MB (fast)", 16 * 1024 * 1024),
            ("32 MB", 32 * 1024 * 1024),
        ]
        for label, value in chunks:
            self.enc_chunk_combo.addItem(label, value)
        
        group_layout.addRow("Chunk Size:", self.enc_chunk_combo)
        
        # Encrypt Filenames
        self.enc_filenames_cb = QtWidgets.QCheckBox("Encrypt Filenames by Default")
        group_layout.addRow(self.enc_filenames_cb)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        layout.addStretch()
        
        return widget
    
    def create_decryption_tab(self) -> QtWidgets.QWidget:
        """Create decryption settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        group = QtWidgets.QGroupBox("Decryption Settings")
        group_layout = QtWidgets.QFormLayout()
        
        # CPU Threads
        total_threads = get_cpu_thread_count()
        max_safe = max(total_threads - 1, 1)
        
        self.dec_threads_combo = QtWidgets.QComboBox()
        for i in range(1, max_safe + 1):
            self.dec_threads_combo.addItem(str(i), i)
        
        group_layout.addRow("CPU Threads:", self.dec_threads_combo)
        
        # Chunk Size
        self.dec_chunk_combo = QtWidgets.QComboBox()
        chunks = [
            ("1 MB", 1 * 1024 * 1024),
            ("8 MB (default)", 8 * 1024 * 1024),
            ("16 MB (fast)", 16 * 1024 * 1024),
            ("32 MB", 32 * 1024 * 1024),
        ]
        for label, value in chunks:
            self.dec_chunk_combo.addItem(label, value)
        
        group_layout.addRow("Chunk Size:", self.dec_chunk_combo)
        
        # Encrypt Filenames (for display purposes)
        self.dec_filenames_label = QtWidgets.QLabel("N/A (Determined by file header)")
        group_layout.addRow("Encrypted Filenames:", self.dec_filenames_label)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        layout.addStretch()
        
        return widget
    
    def create_advanced_tab(self):
        """Create advanced settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        
        # Encryption Mode
        enc_mode_group = QtWidgets.QGroupBox("Encryption Mode")
        enc_mode_layout = QtWidgets.QVBoxLayout()
        
        self.enc_mode_combo = QtWidgets.QComboBox()
        self.enc_mode_combo.addItem("AES-256 GCM (Recommended - AEAD)", "aes256_gcm")
        self.enc_mode_combo.addItem("AES-256 CFB (Fast - No AEAD)", "aes256_cfb")
        self.enc_mode_combo.addItem("ChaCha20-Poly1305 (AEAD)", "chacha20_poly1305")
        
        enc_mode_layout.addWidget(QtWidgets.QLabel("Default Encryption Algorithm:"))
        enc_mode_layout.addWidget(self.enc_mode_combo)
        enc_mode_info = QtWidgets.QLabel(
            "<span style='font-size:8pt;'><b>Note:</b> GCM and ChaCha20 provide authentication (AEAD).<br>"
            "CFB is faster but without authentication.</span>"
        )
        enc_mode_info.setWordWrap(True)
        enc_mode_layout.addWidget(enc_mode_info)
        enc_mode_group.setLayout(enc_mode_layout)
        layout.addWidget(enc_mode_group)
        
        # Logging
        log_group = QtWidgets.QGroupBox("Logging")
        log_layout = QtWidgets.QVBoxLayout()
        
        # Enable logs checkbox
        self.enable_logs_cb = QtWidgets.QCheckBox("Enable Logs")
        self.enable_logs_cb.stateChanged.connect(self.on_logs_toggled)
        log_layout.addWidget(self.enable_logs_cb)
        
        # Log level dropdown
        log_level_layout = QtWidgets.QHBoxLayout()
        log_level_layout.addWidget(QtWidgets.QLabel("Log Level:"))
        self.log_level_combo = QtWidgets.QComboBox()
        self.log_level_combo.addItem("Critical Only", "critical")
        self.log_level_combo.addItem("All/General", "all")
        log_level_layout.addWidget(self.log_level_combo)
        # Persist log level change immediately so writes use new level without Save
        try:
            self.log_level_combo.currentIndexChanged.connect(lambda _: self._persist_log_level())
        except Exception:
            pass
        log_level_layout.addStretch()
        log_layout.addLayout(log_level_layout)
        
        # Info text
        log_info = QtWidgets.QLabel(
            "<span style='font-size:8pt;'><b>Critical:</b> Only critical errors<br>"
            "<b>All/General:</b> All operations (includes critical)<br>"
            "Logs are saved in the <code>/logs</code> directory.</span>"
        )
        log_info.setWordWrap(True)
        log_layout.addWidget(log_info)
        
        # Clear logs button (red text to indicate destructive action)
        self.btn_clear_logs = QtWidgets.QPushButton("Clear All Logs")
        self.btn_clear_logs.setStyleSheet("color: #c62828;")
        self.btn_clear_logs.clicked.connect(self.clear_all_logs)
        # Open logs folder button
        self.btn_open_logs = QtWidgets.QPushButton("Open Logs Folder")
        self.btn_open_logs.setToolTip("Open the logs directory in the file explorer")
        self.btn_open_logs.clicked.connect(self.open_logs_folder)
        # Place the two buttons together
        btn_h = QtWidgets.QHBoxLayout()
        # push buttons to the right corner
        btn_h.addStretch()
        btn_h.addWidget(self.btn_clear_logs)
        btn_h.addWidget(self.btn_open_logs)
        log_layout.addLayout(btn_h)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        layout.addStretch()
        
        return widget
    
    def on_logs_toggled(self) -> None:
        """Handle logs checkbox toggle."""
        enabled = self.enable_logs_cb.isChecked()
        self.log_level_combo.setEnabled(enabled)
        self.btn_clear_logs.setEnabled(enabled)
        # ensure Open Logs Folder is always available (or honor enabled if you prefer)
        try:
            self.btn_open_logs.setEnabled(True)
        except Exception:
            pass
        # Apply visual disabled styling to the combo when logs are disabled
        if enabled:
            try:
                # restore default look
                self.log_level_combo.setStyleSheet("")
            except Exception:
                pass
            # persist the change immediately so logging functions use it
            try:
                self.settings.setdefault("advanced", {})["enable_logs"] = True
                save_settings(self.settings)
            except Exception:
                pass
            # ensure logs folder exists
            try:
                get_logs_dir()
            except Exception:
                pass
        else:
            try:
                self.log_level_combo.setStyleSheet("")
            except Exception:
                pass
            # persist the change immediately so logging functions use it
            try:
                self.settings.setdefault("advanced", {})["enable_logs"] = False
                save_settings(self.settings)
            except Exception:
                pass
    
    def load_settings_to_ui(self) -> None:
        """Load settings from dict to UI controls."""
        # Theme
        theme = self.settings.get("theme", "system")
        index = self.theme_combo.findData(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        # Encryption
        enc_settings = self.settings.get("encryption", {})
        self.enc_threads_combo.setCurrentText(str(enc_settings.get("cpu_threads", 1)))
        chunk_size = enc_settings.get("chunk_size", 8 * 1024 * 1024)
        self.set_combo_by_value(self.enc_chunk_combo, chunk_size)
        self.enc_filenames_cb.setChecked(enc_settings.get("encrypt_filenames", False))
        
        # Decryption
        dec_settings = self.settings.get("decryption", {})
        self.dec_threads_combo.setCurrentText(str(dec_settings.get("cpu_threads", 1)))
        chunk_size = dec_settings.get("chunk_size", 8 * 1024 * 1024)
        self.set_combo_by_value(self.dec_chunk_combo, chunk_size)
        
        # Advanced
        adv_settings = self.settings.get("advanced", {})
        enc_mode = adv_settings.get("encryption_mode", "aes256_gcm")
        index = self.enc_mode_combo.findData(enc_mode)
        if index >= 0:
            self.enc_mode_combo.setCurrentIndex(index)
        
        enable_logs = adv_settings.get("enable_logs", False)
        self.enable_logs_cb.setChecked(enable_logs)
        
        log_level = adv_settings.get("log_level", "critical")
        index = self.log_level_combo.findData(log_level)
        if index >= 0:
            self.log_level_combo.setCurrentIndex(index)
        
        self.on_logs_toggled()
    
    def set_combo_by_value(self, combo: QtWidgets.QComboBox, value: int) -> None:
        """Set combo box selection by data value."""
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)
            combo.setCurrentIndex(0)
    
    def apply_settings(self) -> None:
        """Apply settings without closing the dialog."""
        self.settings["theme"] = self.theme_combo.currentData()
        
        self.settings["encryption"]["cpu_threads"] = int(self.enc_threads_combo.currentText())
        self.settings["encryption"]["chunk_size"] = self.enc_chunk_combo.currentData()
        self.settings["encryption"]["encrypt_filenames"] = self.enc_filenames_cb.isChecked()
        
        self.settings["decryption"]["cpu_threads"] = int(self.dec_threads_combo.currentText())
        self.settings["decryption"]["chunk_size"] = self.dec_chunk_combo.currentData()
        
        self.settings["advanced"]["encryption_mode"] = self.enc_mode_combo.currentData()
        self.settings["advanced"]["enable_logs"] = self.enable_logs_cb.isChecked()
        self.settings["advanced"]["log_level"] = self.log_level_combo.currentData()
        
        if save_settings(self.settings):
            self.settings_changed.emit(self.settings)
        else:
            from widgets.custom_title_bar import show_message
            show_message(self, "Error", "Failed to save settings.", icon="warning")
    
    def save_and_close(self) -> None:
        """Apply settings and close the dialog."""
        self.apply_settings()
        self.accept()
    
    def reset_to_defaults(self) -> None:
        """Reset settings to defaults."""
        from widgets.custom_title_bar import show_message
        reply = show_message(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            buttons="yesno"
        )
        
        if reply:
            from utils.gfg_helpers import get_default_settings
            self.settings = get_default_settings()
            self.load_settings_to_ui()
    
    def clear_all_logs(self) -> None:
        """Clear all log files."""
        from widgets.custom_title_bar import show_message
        reply = show_message(
            self, "Clear Logs",
            "Are you sure you want to delete all log files?",
            buttons="yesno"
        )
        
        if reply:
            if clear_logs():
                show_message(self, "Success", "All log files have been cleared.", icon="info")
            else:
                show_message(self, "Error", "Failed to clear log files.", icon="warning")

    def _persist_log_level(self) -> None:
        """Persist current log level selection immediately."""
        try:
            lvl = self.log_level_combo.currentData()
            self.settings.setdefault("advanced", {})["log_level"] = lvl
            save_settings(self.settings)
            # If switched to 'all' write current logs panel content into general log (replace file)
            if lvl == 'all':
                try:
                    # find main window logs panel
                    main_win = None
                    p = self.parent()
                    while p is not None:
                        if hasattr(p, 'logs_text'):
                            main_win = p
                            break
                        p = p.parent()
                    if main_win is None:
                        for w in QtWidgets.QApplication.topLevelWidgets():
                            if hasattr(w, 'logs_text'):
                                main_win = w
                                break
                    logs_text = ""
                    if main_win is not None and hasattr(main_win, 'logs_text'):
                        try:
                            logs_text = main_win.logs_text.toPlainText()  # type: ignore[attr-defined]
                        except Exception:
                            logs_text = ""
                    # write (replace) general log file with timestamped lines
                    try:
                        gen = get_general_log_file()
                        lines = (logs_text or "").splitlines()
                        with open(gen, 'w', encoding='utf-8') as f:
                            for ln in lines:
                                if ln is None:
                                    continue
                                text = ln.rstrip('\r\n')
                                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                f.write(f"[{ts}] {text}\n")
                    except Exception:
                        pass

                    # write (replace) critical log file containing only critical lines
                    try:
                        crit = get_critical_log_file()
                        critical_keywords = (
                            'critical', 'critical error', 'authentication failed',
                            'error while decrypting', 'failed to decrypt', 'decryption failed', 'encryption failed',
                            'failed to encrypt'
                        )
                        lines = (logs_text or "").splitlines()
                        with open(crit, 'w', encoding='utf-8') as fc:
                            for ln in lines:
                                if not ln:
                                    continue
                                if any(k in (ln or '').lower() for k in critical_keywords):
                                    text = ln.rstrip('\r\n')
                                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    fc.write(f"[{ts}] {text}\n")
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def open_logs_folder(self) -> None:
        """Open the logs directory in the system file explorer."""
        logs_dir = get_logs_dir()
        try:
            # Prefer Qt's cross-platform open
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(logs_dir))
        except Exception:
            # Fallbacks for typical platforms
            try:
                if sys.platform.startswith("win"):
                    os.startfile(logs_dir)
                elif sys.platform.startswith("darwin"):
                    subprocess.run(["open", logs_dir], check=False)
                else:
                    subprocess.run(["xdg-open", logs_dir], check=False)
            except Exception:
                from widgets.custom_title_bar import show_message
                show_message(self, "Error", "Could not open logs folder.", icon="warning")
