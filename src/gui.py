import os
import shlex
import sys
from multiprocessing import freeze_support

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextOption

from services.worker import EncryptDecryptWorker
from utils.gfg_helpers import load_settings, write_general_log, write_critical_log, write_log, get_chunk_sizes, \
    get_encryption_modes, resource_path
from utils.theme_manager import apply_theme
from views.preferences import PreferencesWindow
from widgets.custom_title_bar import CustomTitleBar

# === PYINSTALLER SHELL ARGUMENT FIX - MUST BE HERE! ===
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    import ctypes
    from ctypes import wintypes
    try:
        GetCommandLineW = ctypes.windll.kernel32.GetCommandLineW
        GetCommandLineW.argtypes = []
        GetCommandLineW.restype = wintypes.LPCWSTR

        CommandLineToArgvW = ctypes.windll.shell32.CommandLineToArgvW
        CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)

        cmd = GetCommandLineW()
        argc = ctypes.c_int()
        argv = CommandLineToArgvW(cmd, ctypes.byref(argc))
        sys.argv = [argv[i] for i in range(argc.value)]
        if sys.argv:
            sys.argv[0] = sys.executable
    except:
        pass
# ========================================================

os.environ["QT_QPA_PLATFORM"] = "windows"
# ... rest of your code



# ========================================================
# ========================================================
app_name = "gfgLock"
app_version = "2.7.0"
author = "Shah Faisal"
company = "gfgRoyal"

# ========================================================
# ========================================================


class ProgressDialog(QtWidgets.QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  # type: ignore[attr-defined]
        self.setWindowTitle("Progress")
        # Set minimum size and initial size - allow user to resize larger
        self.setMinimumSize(620, 380)
        self.resize(620, 370)
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
            self.label_current.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.label_current.setWordWrap(False)
            self.label_current.setMinimumWidth(0)
            self.label_current.setFixedHeight(20)
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
            self.logs.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            self.logs.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Prevent the logs widget from growing the dialog based on content length.
        # Ignore content-based size adjustments and allow the widget to expand
        # only when the user resizes the dialog.
        try:
            self.logs.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustIgnored)
            self.logs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.logs.setMinimumHeight(100)  # Set minimum height to prevent large sizeHint
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
        self.resize(620, 370)


class EncryptDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mode="encrypt"):
        super().__init__(parent)
        self.mode = mode
        self.errors = []
        self.current_file = ""
        self.settings = load_settings()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  # type: ignore[attr-defined]
        self.setWindowTitle("Encryption" if mode == "encrypt" else "Decryption")
        self.resize(720, 470)
        self.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

        enc_main = QtWidgets.QVBoxLayout(self)

        # custom title bar
        try:
            self.custom_title_bar = CustomTitleBar("Encryption" if mode == "encrypt" else "Decryption", self)
            enc_main.insertWidget(0, self.custom_title_bar)
        except Exception:
            pass

        # File list
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        enc_main.addWidget(self.list_widget)
        # Keep track of counts and selections
        self.list_widget.itemSelectionChanged.connect(lambda: self.update_count_label())

        # Add files/folders
        h = QtWidgets.QHBoxLayout()
        self.btn_add_files = QtWidgets.QPushButton("Add Files")
        self.btn_add_folders = QtWidgets.QPushButton("Add Folders")
        self.btn_remove = QtWidgets.QPushButton("Remove Selected")
        self.btn_remove.setEnabled(False)  # Disabled until files are selected
        h.addWidget(self.btn_add_files)
        h.addWidget(self.btn_add_folders)
        h.addWidget(self.btn_remove)
        enc_main.addLayout(h)

        # OPTIONS AREA
        form = QtWidgets.QFormLayout()

        # Password row
        pw_layout = QtWidgets.QHBoxLayout()

        self.pass_input = QtWidgets.QLineEdit()
        self.pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
        pw_layout.addWidget(QtWidgets.QLabel("Password:"))
        pw_layout.addWidget(self.pass_input)

        if self.mode == "encrypt":
            self.confirm_pass_input = QtWidgets.QLineEdit()
            self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
            pw_layout.addWidget(QtWidgets.QLabel("Confirm:"))
            pw_layout.addWidget(self.confirm_pass_input)

        # Show password checkbox placed on the same row as password inputs
        self.show_pass_cb = QtWidgets.QCheckBox("Show")
        self.show_pass_cb.stateChanged.connect(self.toggle_password)
        pw_layout.addWidget(self.show_pass_cb)

        form.addRow(pw_layout)

        # CPU Threads + Chunk Size on same row
        row = QtWidgets.QHBoxLayout()

        # CPU threads - load from settings
        total_threads = os.cpu_count() or 1
        max_safe = max(total_threads - 1, 1)

        if self.mode == "encrypt":
            default_threads = self.settings.get("encryption", {}).get("cpu_threads", max(1, total_threads // 2))
            default_chunk = self.settings.get("encryption", {}).get("chunk_size", 8*1024*1024)
            default_encrypt_name = self.settings.get("encryption", {}).get("encrypt_filenames", False)
        else:
            default_threads = self.settings.get("decryption", {}).get("cpu_threads", max(1, total_threads // 2))
            default_chunk = self.settings.get("decryption", {}).get("chunk_size", 8*1024*1024)
            default_encrypt_name = False  # Not used in decrypt

        self.threads_combo = QtWidgets.QComboBox()
        for i in range(1, max_safe + 1):
            self.threads_combo.addItem(str(i))
        # reduced width to save horizontal space
        self.threads_combo.setFixedWidth(85)

        if str(default_threads) in [str(i) for i in range(1, max_safe + 1)]:
            self.threads_combo.setCurrentText(str(default_threads))

        # chunk size
        self.chunk_combo = QtWidgets.QComboBox()
        self.chunk_combo.setFixedWidth(90)
        
        for label, val in get_chunk_sizes():
            self.chunk_combo.addItem(label, val)
        # slightly smaller chunk size combobox
        self.chunk_combo.setFixedWidth(120)

        # Set chunk size from settings
        chunk_index = self.chunk_combo.findData(default_chunk)
        if chunk_index >= 0:
            self.chunk_combo.setCurrentIndex(chunk_index)
        else:
            self.chunk_combo.setCurrentText("16 MB (fast)")

        row.addWidget(QtWidgets.QLabel("CPU Threads:"))
        row.addWidget(self.threads_combo)
        row.addWidget(QtWidgets.QLabel("Chunk Size:"))
        row.addWidget(self.chunk_combo)
        # Algorithm dropdown moved to the same row as threads/chunk
        # Algorithm dropdown is only shown for encryption mode
        if self.mode == "encrypt":
            row.addWidget(QtWidgets.QLabel("Algorithm:"))
            self.alg_combo = QtWidgets.QComboBox()
            for label, mode_id in get_encryption_modes():
                self.alg_combo.addItem(label, mode_id)
            try:
                default_algo = self.settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                idx = self.alg_combo.findData(default_algo)
                if idx >= 0:
                    self.alg_combo.setCurrentIndex(idx)
            except Exception:
                pass
            row.addWidget(self.alg_combo)

        row.addStretch()
        form.addRow(row)

        # Encrypt filenames (kept in options area for encrypt mode)
        if self.mode == "encrypt":
            bottom_row = QtWidgets.QHBoxLayout()
            self.encrypt_name_cb = QtWidgets.QCheckBox("Encrypt filenames")
            self.encrypt_name_cb.setChecked(default_encrypt_name)
            bottom_row.addWidget(self.encrypt_name_cb)
            bottom_row.addStretch()
            form.addRow(bottom_row)

        enc_main.addLayout(form)

        # Bottom Start/Cancel buttons
        bottom = QtWidgets.QHBoxLayout()
        # File count label on the left
        self.count_label = QtWidgets.QLabel("0 files")
        bottom.addWidget(self.count_label)
        bottom.addStretch()
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_start = QtWidgets.QPushButton(
            "Start Encryption" if self.mode == "encrypt" else "Start Decryption"
        )
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_start)
        # add resize grip to allow resizing frameless dialog
        try:
            grip_h = QtWidgets.QHBoxLayout()
            grip_h.addStretch()
            grip = QtWidgets.QSizeGrip(self)
            grip_h.addWidget(grip)
            enc_main.addLayout(grip_h)
        except Exception:
            pass
        enc_main.addLayout(bottom)

        # Connect signals
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_folders.clicked.connect(self.add_folders)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_start.clicked.connect(self.start_op)

        # Set initial focus and tab order
        self.pass_input.setFocus()
        # Make start button the default so Enter triggers it
        self.btn_start.setDefault(True)
        self.btn_start.setAutoDefault(True)

        if self.mode == "encrypt":
            # password -> confirm -> start
            self.setTabOrder(self.pass_input, self.confirm_pass_input)
            self.setTabOrder(self.confirm_pass_input, self.btn_start)
        else:
            # decryption: password -> start
            self.setTabOrder(self.pass_input, self.btn_start)

        # Enable drag & drop on the list widget
        self.list_widget.setAcceptDrops(True)
        self.list_widget.installEventFilter(self)

        self.worker = None
        self.progress_dlg = None
        self.threadpool = QtCore.QThreadPool.globalInstance()

    def toggle_password(self):
        if self.show_pass_cb.isChecked():
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            if self.mode == "encrypt":
                self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
            if self.mode == "encrypt":
                self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.Password)

    def add_files(self):
        # For decrypt mode, show only encrypted file types in the dialog
        if self.mode == 'decrypt':
            file_filter = "Encrypted Files (*.gfglock *.gfglck *.gfgcha)"
            files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select files", "", file_filter)
        else:
            # Show non-encrypted files by default (can't exclude by pattern in QFileDialog,
            # so show all and we'll filter out encrypted extensions after selection)
            file_filter = "All Files (*.*)"
            files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select files", "", file_filter)
        if not files:
            return
        enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
        if self.mode == 'encrypt':
            # allow only files that are NOT already encrypted
            files = [f for f in files if not f.lower().endswith(enc_exts)]
        else:
            # decrypt mode: allow only encrypted files
            files = [f for f in files if f.lower().endswith(enc_exts)]
        for f in files:
            self.add_path_to_list(f)
        self.update_count_label()

    def add_folders(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
            for root, _, files in os.walk(folder):
                for fn in files:
                    fp = os.path.join(root, fn)
                    if self.mode == 'encrypt':
                        if fp.lower().endswith(enc_exts):
                            continue
                    else:
                        if not fp.lower().endswith(enc_exts):
                            continue
                    self.add_path_to_list(fp)
        self.update_count_label()

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self.update_count_label()

    def add_path_to_list(self, path):
        # Add only unique absolute normalized paths
        p = os.path.abspath(path)
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())] # type: ignore
        if p not in items:
            self.list_widget.addItem(p)
            self.update_count_label()

    def update_count_label(self):
        total = self.list_widget.count()
        selected = len(self.list_widget.selectedItems())
        if selected > 0:
            text = f"{total} files | {selected} selected"
            self.btn_remove.setEnabled(True)
        else:
            text = f"{total} files"
            self.btn_remove.setEnabled(False)
        self.count_label.setText(text)

    def eventFilter(self, a0, a1):
        # Handle drag & drop on the list widget: accept filesystem URLs.
        # Use parameter names that match the base signature to satisfy the
        # static analyzer.
        obj = a0
        event = a1
        if obj is self.list_widget:
            try:
                etype = event.type()  # type: ignore[attr-defined]
            except Exception:
                return super().eventFilter(a0, a1)

            if etype == QtCore.QEvent.DragEnter:  # type: ignore[attr-defined]
                get_mime = getattr(event, 'mimeData', None)
                mime = get_mime() if callable(get_mime) else None
                if mime and getattr(mime, 'hasUrls', lambda: False)():
                    accept_fn = getattr(event, 'accept', None)
                    if callable(accept_fn):
                        accept_fn()
                    return True

            if etype == QtCore.QEvent.Drop:  # type: ignore[attr-defined]
                get_mime = getattr(event, 'mimeData', None)
                mime = get_mime() if callable(get_mime) else None
                if mime and getattr(mime, 'hasUrls', lambda: False)():
                    urls = getattr(mime, 'urls', lambda: [])()
                    for url in urls:
                        try:
                            local = url.toLocalFile()
                        except Exception:
                            local = str(getattr(url, 'toString', lambda: str(url))())
                        if os.path.isdir(local):
                            enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
                            for root, _, files in os.walk(local):
                                for fn in files:
                                    fp = os.path.join(root, fn)
                                    if self.mode == 'encrypt':
                                        if fp.lower().endswith(enc_exts):
                                            continue
                                    else:
                                        if not fp.lower().endswith(enc_exts):
                                            continue
                                    self.add_path_to_list(fp)
                        elif os.path.isfile(local):
                            enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
                            if self.mode == 'encrypt':
                                if not local.lower().endswith(enc_exts):
                                    self.add_path_to_list(local)
                            else:
                                if local.lower().endswith(enc_exts):
                                    self.add_path_to_list(local)
                    self.update_count_label()
                    accept_fn = getattr(event, 'accept', None)
                    if callable(accept_fn):
                        accept_fn()
                    return True

        return super().eventFilter(a0, a1)

    def start_op(self):
        paths = [self.list_widget.item(i).text() for i in range(self.list_widget.count())] # type: ignore

        if not paths:
            from widgets.custom_title_bar import show_message
            show_message(self, "No files", "Add files first.", icon="warning")
            return

        password = self.pass_input.text().strip()
        if not password:
            from widgets.custom_title_bar import show_message
            show_message(self, "Password required", "Enter a password.", icon="warning")
            return

        if self.mode == "encrypt":
            from widgets.custom_title_bar import show_message
            confirm_password = self.confirm_pass_input.text().strip()
            if not confirm_password:
                show_message(self, "Confirm required", "Please confirm your password.", icon="warning")
                return
            if password != confirm_password:
                show_message(self, "Password mismatch", "Password and Confirm Password must match.", icon="warning")
                return

        self.errors = []
        self.current_file = ""

        threads = int(self.threads_combo.currentText())
        chunk_size = self.chunk_combo.currentData()
        encrypt_name = self.encrypt_name_cb.isChecked() if self.mode == "encrypt" else False

        # Progress dialog
        self.progress_dlg = ProgressDialog(len(paths), self)
        self.progress_dlg.show()
        QtWidgets.QApplication.processEvents()

        # Worker
        enc_algo = None
        if self.mode == "encrypt":
            try:
                enc_algo = self.alg_combo.currentData()
            except Exception:
                enc_algo = None

        self.worker = EncryptDecryptWorker(
            paths, password,
            mode=self.mode,
            encrypt_name=encrypt_name,
            threads=threads,
            chunk_size=chunk_size,
            enc_algo=enc_algo
        )

        self.worker.signals.progress.connect(self.on_progress, QtCore.Qt.ConnectionType.QueuedConnection) # type: ignore
        self.worker.signals.file_changed.connect(self.on_current_file, QtCore.Qt.ConnectionType.QueuedConnection) # type: ignore
        self.worker.signals.status.connect(self.on_status, QtCore.Qt.ConnectionType.QueuedConnection) # type: ignore
        self.worker.signals.error.connect(self.on_error, QtCore.Qt.ConnectionType.QueuedConnection) # type: ignore
        self.worker.signals.finished.connect(self.on_finished, QtCore.Qt.ConnectionType.QueuedConnection) # type: ignore

        self.progress_dlg.btn_cancel.clicked.connect(self.worker.cancel)

        self.threadpool.start(self.worker) # type: ignore

    def on_progress(self, done, total):
        self.progress_dlg.progress_bar.setValue(done) # type: ignore
        self.progress_dlg.detail.setText(f"{done}/{total}") # type: ignore

    def on_current_file(self, text):
        # Update the current file label only. Actual logs from core are
        # forwarded via the status signal and will be appended to the logs panel.
        self.current_file = text
        if not self.progress_dlg:
            return

        label = self.progress_dlg.label_current

        # Show only the filename (not the full path) in the label to avoid
        # making the dialog grow. Keep the full path available as a tooltip.
        if text:
            try:
                fname = os.path.basename(text)
            except Exception:
                fname = text
            display = "Current: " + (fname or text)
            try:
                label.setToolTip(text)
            except Exception:
                pass
        else:
            display = "Current:"
            try:
                label.setToolTip("")
            except Exception:
                pass

        # Elide long filenames to avoid resizing the dialog. Prefer to elide
        # in the middle so both ends remain visible.
        try:
            fm = label.fontMetrics()
            avail = max(50, label.width() - 20)
            if avail <= 50:
                try:
                    avail = max(100, self.progress_dlg.width() - 120)
                except Exception:
                    avail = 300
            elided = fm.elidedText(display, QTextOption.ElideMiddle, avail)
        except Exception:
            elided = display if len(display) <= 200 else display[:200] + "..."

        label.setText(elided) # type: ignore

    def on_status(self, msg):
        # Append core/log messages to the logs panel exactly as they would
        # appear on the console.
        self.progress_dlg.logs.appendPlainText(msg) # type: ignore
        # Determine if message is critical by checking common keywords
        try:
            lc = (msg or "").lower()
            critical_keywords = (
                'critical', 'critical error', 'authentication failed',
                'error while decrypting', 'failed to decrypt', 'decryption failed', 'encryption failed',
                'failed to encrypt'
            )
            is_critical = any(k in lc for k in critical_keywords)

            settings = load_settings()
            adv = settings.get("advanced", {})
            enabled = adv.get("enable_logs", False)
            level = adv.get("log_level", "critical")

            # If 'all' selected, write all messages to general log
            if enabled and level == 'all':
                try:
                    write_general_log(msg)
                except Exception:
                    try:
                        write_log(msg, level='general')
                    except Exception:
                        pass

            # If message looks critical, write to critical log when enabled
            if is_critical and enabled and level in ('critical', 'all'):
                try:
                    write_critical_log(msg)
                except Exception:
                    pass
        except Exception:
            pass

    def on_error(self, msg):
        # Keep a record of errors; status messages from core are already
        # appended via on_status. Store errors for final reporting.
        error_msg = f"{msg}"
        self.progress_dlg.logs.appendPlainText(error_msg) # type: ignore
        self.errors.append(error_msg)
        # Write critical logs immediately when Critical logging is enabled.
        try:
            settings = load_settings()
            adv = settings.get("advanced", {})
            if adv.get("enable_logs", False):
                # always write critical logs for errors when critical logging enabled
                if adv.get("log_level", "critical") in ("critical", "all"):
                    try:
                        write_critical_log(error_msg)
                    except Exception:
                        pass
                # if 'all' selected, also write to general log
                if adv.get("log_level", "critical") == "all":
                    try:
                        write_general_log(error_msg)
                    except Exception:
                        try:
                            write_log(error_msg, level="general")
                        except Exception:
                            pass
        except Exception:
            pass

    def on_finished(self, elapsed, total, succeeded, failed, skipped):
        # Summarize operation and show a concise result message.
        op = "Encrypted" if self.mode == "encrypt" else "Decrypted"


        # Compose a single combined message including details
        lines = [f"{op} {succeeded} files in {elapsed:.2f} seconds."]
        if skipped > 0:
            if self.mode == "encrypt":
                lines.append(f"{skipped} files were already encrypted.")
            else:
                lines.append(f"{skipped} files were already decrypted.")
        if failed > 0:
            if self.mode == "decrypt":
                lines.append(f"{failed} files decryption failed.")
                lines.append("Possible reasons: wrong password, insufficient permissions, or file corruption.")
            else:
                lines.append(f"{failed} files failed to encrypt.")

        full_msg = "\n".join(lines)
        # Show a single dialog. This call blocks until user clicks OK.
        from widgets.custom_title_bar import show_message
        if failed > 0:
            show_message(self, f"{op} completed with issues", full_msg, icon="warning")
        else:
            show_message(self, op, full_msg, icon="info")

        # After user closed the message box, copy progress logs to main window logs panel
        try:
            logs_text = self.progress_dlg.logs.toPlainText() if self.progress_dlg else ""
            main_win = None
            # climb parents
            p = self.parent()
            while p is not None:
                if hasattr(p, 'logs_text'):
                    main_win = p
                    break
                p = p.parent()
            # fallback: search top-level widgets
            if main_win is None:
                for w in QtWidgets.QApplication.topLevelWidgets():
                    if hasattr(w, 'logs_text'):
                        main_win = w
                        break

            if main_win is not None and logs_text:
                # Prefer appending to a `logs_text` widget if present
                logs_widget = getattr(main_win, 'logs_text', None)
                if logs_widget is not None:
                    try:
                        logs_widget.append(logs_text)
                    except Exception:
                        pass
                else:
                    # Fallback to `show_logs` method if available
                    show_logs_fn = getattr(main_win, 'show_logs', None)
                    existing = ""
                    logs_widget2 = getattr(main_win, 'logs_text', None)
                    if logs_widget2 is not None:
                        try:
                            existing = logs_widget2.toPlainText()
                        except Exception:
                            existing = ""
                    if callable(show_logs_fn):
                        try:
                            show_logs_fn(existing + "\n" + logs_text)
                        except Exception:
                            pass
        except Exception:
            pass

        self.progress_dlg.close() # type: ignore
        self.accept()






class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)  # type: ignore[attr-defined]
        self.setWindowTitle("gfgLock")
        self.resize(720, 470)
        self.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

        mw_main = QtWidgets.QWidget()
        self.setCentralWidget(mw_main)

        v = QtWidgets.QVBoxLayout(mw_main)

        # custom title bar
        try:
            self.custom_title_bar = CustomTitleBar("gfgLock", self)
            v.insertWidget(0, self.custom_title_bar)
        except Exception:
            pass

        # Professional header: icon + title + subtitle
        header_widget = QtWidgets.QWidget()
        header_widget.setObjectName("header_widget")
        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        try:
            pix = QtGui.QPixmap(resource_path("./assets/icons/gfgLock.png"))
            if not pix.isNull():
                icon_lbl = QtWidgets.QLabel()
                icon_lbl.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))  # type: ignore[attr-defined]
                icon_lbl.setFixedSize(52, 52)
                header_layout.addWidget(icon_lbl)
        except Exception:
            pass

        title_layout = QtWidgets.QVBoxLayout()
        title_lbl = QtWidgets.QLabel("<span style='font-size:16pt;font-weight:700;'>gfgLock</span>")
        title_lbl.setObjectName("title_label")
        title_lbl.setTextFormat(Qt.RichText)  # type: ignore[attr-defined]
        subtitle_lbl = QtWidgets.QLabel("Secure AES-256 file encryption and decryption — fast, simple, reliable")
        subtitle_lbl.setObjectName("subtitle_label")
        subtitle_lbl.setStyleSheet("font-size:9pt;")

        title_layout.addWidget(title_lbl)
        title_layout.addWidget(subtitle_lbl)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        v.addWidget(header_widget)

        # Main action buttons — emphasize primary actions
        h = QtWidgets.QHBoxLayout()
        self.btn_encrypt = QtWidgets.QPushButton("Encryption")
        self.btn_decrypt = QtWidgets.QPushButton("Decryption")

        # Secondary buttons
        self.btn_prefs = QtWidgets.QPushButton("Preferences")
        self.btn_about = QtWidgets.QPushButton("About")
        self.btn_update = QtWidgets.QPushButton("Check Updates")

        # Use consistent, moderate styling for all buttons
        main_btn_style = "font-size:9pt; padding:8px 12px;"
        for b in (self.btn_encrypt, self.btn_decrypt, self.btn_prefs, self.btn_about, self.btn_update):
            b.setStyleSheet(main_btn_style)
            b.setMinimumHeight(34)

        h.addWidget(self.btn_encrypt)
        h.addWidget(self.btn_decrypt)
        h.addStretch(1)
        h.addWidget(self.btn_update)
        h.addWidget(self.btn_prefs)
        h.addWidget(self.btn_about)
        v.addLayout(h)

        self.btn_encrypt.clicked.connect(lambda: EncryptDialog(self, "encrypt").exec_()) # type: ignore
        self.btn_decrypt.clicked.connect(lambda: EncryptDialog(self, "decrypt").exec_()) # type: ignore
        self.btn_prefs.clicked.connect(self.open_preferences) # type: ignore
        self.btn_about.clicked.connect(self.show_about_dialog) # type: ignore

        # Check Updates button opens GitHub releases
        def _open_updates():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock"))
        self.btn_update.clicked.connect(_open_updates)
        self.btn_update.setToolTip("Open GitHub releases page to check for latest version")

        self.status = QtWidgets.QLabel("Ready")
        v.addWidget(self.status)

        # Dev-only logs panel - Remove after testing
        self.logs_text = QtWidgets.QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setPlaceholderText("Output logs...")
        # Prefer horizontal scrolling for long lines
        try:
            self.logs_text.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
            self.logs_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        except Exception:
            pass
        v.addWidget(self.logs_text)
        # Clear logs button: place in bottom-right footer row to match dialogs
        self.btn_clear_logs = QtWidgets.QPushButton("🧹 Clear")
        self.btn_clear_logs.setToolTip("Clear all logs")
        self.btn_clear_logs.setMinimumHeight(34)
        self.btn_clear_logs.clicked.connect(self.clear_logs_panel)
        # add resize grip for frameless main window (above the clear button)
        try:
            grip_h = QtWidgets.QHBoxLayout()
            grip_h.addStretch()
            grip = QtWidgets.QSizeGrip(self)
            grip_h.addWidget(grip)
            v.addLayout(grip_h)
        except Exception:
            pass

        # Footer row with clear logs button at the very bottom
        clear_footer = QtWidgets.QHBoxLayout()
        clear_footer.addStretch()
        clear_footer.addWidget(self.btn_clear_logs)
        v.addLayout(clear_footer)

    def show_logs(self, text):
        self.logs_text.setText(text)

    def clear_logs_panel(self):
        """Clear the logs text area."""
        self.logs_text.clear()

    def open_preferences(self):
        """Open the preferences window."""
        prefs_window = PreferencesWindow(self)
        prefs_window.settings_changed.connect(self.on_settings_changed)
        prefs_window.exec_()

    def on_settings_changed(self, settings):
        """Handle settings changed signal."""
        self.settings = settings
        # Reapply theme if changed
        apply_theme(None, settings.get("theme", "system"))

    def show_about_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("About gfgLock")
        dlg.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

        dlg.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  # type: ignore[attr-defined]
        layout = QtWidgets.QVBoxLayout(dlg)
        # custom title bar
        try:
            title_bar = CustomTitleBar("About gfgLock", dlg)
            layout.insertWidget(0, title_bar)
        except Exception:
            pass

        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Centered header: logo, app name, subtitle
        header = QtWidgets.QWidget()
        hl = QtWidgets.QVBoxLayout(header)
        hl.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]

        try:
            pix = QtGui.QPixmap(resource_path("./assets/icons/gfgLock.png"))
            if not pix.isNull():
                logo = QtWidgets.QLabel()
                logo.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))  # type: ignore[attr-defined]
                logo.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
                hl.addWidget(logo)
        except Exception:
            pass

        title = QtWidgets.QLabel("<span style='font-size:18pt;font-weight:700;'>gfgLock</span>")
        title.setTextFormat(Qt.RichText)  # type: ignore[attr-defined]
        title.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        hl.addWidget(title)

        version = QtWidgets.QLabel("v" + app_version)
        version.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        version.setStyleSheet("font-size:8pt; color: #999999; font-weight: 500;")
        hl.addWidget(version)

        subtitle = QtWidgets.QLabel("Secure AES-256 file encryption and decryption")
        subtitle.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        subtitle.setStyleSheet("font-size:9pt; color: #666666;")
        hl.addWidget(subtitle)

        layout.addWidget(header)

        # Description
        desc = QtWidgets.QLabel(
            "gfgLock provides fast, easy-to-use AES-256 file encryption and decryption.\n"
            "Supports multi-threaded processing, chunked file I/O and optional filename encryption.\n"
            "Designed for simplicity and reliability for both casual and power users."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Company / Author
        info = QtWidgets.QWidget()
        info_l = QtWidgets.QFormLayout(info)
        info_l.setLabelAlignment(Qt.AlignRight)  # type: ignore[attr-defined]
        info_l.addRow("Company:", QtWidgets.QLabel(company))
        info_l.addRow("Author:", QtWidgets.QLabel(author))
        layout.addWidget(info)

        # Links row
        links = QtWidgets.QHBoxLayout()
        links.addStretch()

        email_btn = QtWidgets.QPushButton("Contact: shahfaisalgfg@outlook.com")
        email_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_mail():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("mailto:shahfaisalgfg@outlook.com"))
        email_btn.clicked.connect(_open_mail)
        links.addWidget(email_btn)

        github_btn = QtWidgets.QPushButton("GitHub Repo")
        github_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_github():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/ShahFaisalGfG/gfgLock"))
        github_btn.clicked.connect(_open_github)
        links.addWidget(github_btn)

        site_btn = QtWidgets.QPushButton("Website")
        site_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_site():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://shahfaisalgfg.github.io/shahfaisal"))
        site_btn.clicked.connect(_open_site)
        links.addWidget(site_btn)

        links.addStretch()
        layout.addLayout(links)

        # Close button
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)

        dlg.exec_()


def main():
    app = QtWidgets.QApplication(sys.argv)
    freeze_support()
    app.setStyle("Fusion")
    app.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

    # Apply theme
    apply_theme(app)

    args = sys.argv[1:]
    debug_logs = [f"Raw args received: {args}"]

    # No args → normal launch
    if not args:
        win = MainWindow()
        win.show()
        sys.exit(app.exec_())

    # === Detect operation mode ===
    mode = None
    path_args = args

    if args and args[0].lower() in ("encrypt", "decrypt"):
        mode = args[0].lower()
        path_args = args[1:]
        debug_logs.append(f"Explicit mode: {mode}")
    else:
        # Auto-detect: if any encrypted file exists in args → decrypt
        enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
        enc_files = [p for p in args if os.path.exists(p) and p.lower().endswith(enc_exts)]
        if enc_files:
            mode = "decrypt"
            debug_logs.append("Auto-detected decrypt mode (encrypted files found)")

    # If no valid mode → open main window
    if not mode:
        debug_logs.append("No valid mode → opening main window")
        win = MainWindow()
        win.show_logs("\n".join(debug_logs))
        win.show()
        sys.exit(app.exec_())

    # === Reconstruct paths correctly (Windows Explorer breaks paths with spaces) ===
    raw_paths = []

    if path_args:
        combined = " ".join(path_args)
        debug_logs.append(f"Combined path string: {combined}")

        # First: try if the combined string is a real path
        if os.path.exists(combined):
            raw_paths = [combined]
            debug_logs.append("Combined path exists → using as single item")
        else:
            # Second: try shlex (handles quoted paths like "C:\My Folder\file.gfglock")
            try:
                raw_paths = shlex.split(combined)
                debug_logs.append(f"shlex parsed: {raw_paths}")
            except:
                raw_paths = path_args  # fallback

            # Final fallback: if nothing works, treat as one broken path
            if not any(os.path.exists(p.strip('"')) for p in raw_paths):
                raw_paths = [combined]
                debug_logs.append("Fallback: treating all args as one broken path")

    # === Expand folders and collect only real files (especially .gfglock for decrypt) ===
    final_paths = []

    for path in raw_paths:
        p = path.strip('"\'')
        abs_p = os.path.abspath(p)

        if not os.path.exists(abs_p):
            final_paths.append(abs_p)  # keep for error visibility
            continue

        # Only include files appropriate for the selected mode:
        enc_exts = ('.gfglock', '.gfglck', '.gfgcha')
        if os.path.isfile(abs_p):
            # Encrypt mode: skip files that are already encrypted
            if mode == "encrypt":
                if abs_p.lower().endswith(enc_exts):
                    continue
            # Decrypt mode: include only encrypted files
            else:
                if not abs_p.lower().endswith(enc_exts):
                    continue
            final_paths.append(abs_p)

        elif os.path.isdir(abs_p):
            for root, _, files in os.walk(abs_p):
                for f in files:
                    fp = os.path.join(root, f)
                    if mode == "encrypt":
                        # In encrypt mode, skip files that already have an encrypted extension
                        if fp.lower().endswith(enc_exts):
                            continue
                    else:
                        # In decrypt mode, only include encrypted files
                        if not fp.lower().endswith(enc_exts):
                            continue
                    final_paths.append(fp)

    # Remove duplicates
    seen = set()
    unique_paths = [p for p in final_paths if not (p in seen or seen.add(p))]

    debug_logs.append(f"Final files to process: {unique_paths}")

    # === Launch dialog ===
    dlg = EncryptDialog(None, mode)

    for p in unique_paths:
        dlg.add_path_to_list(p)

    if unique_paths:
        dlg.pass_input.setFocus()
    else:
        from widgets.custom_title_bar import show_message
        show_message(None, "No files", f"No valid files found for {mode}ion.", icon="warning")

    dlg.exec_()
    sys.exit(0)


if __name__ == "__main__":
    main()