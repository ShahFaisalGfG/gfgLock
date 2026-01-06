import os

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import ChunkSizeOptions, EncryptionModes, ComboBoxSizes, WindowSizes, scale_size, scale_value
from services import EncryptDecryptWorker
from utils import apply_theme
from utils import load_settings, write_general_log, write_critical_log, write_log, resource_path
from views.progress_dialog import ProgressDialog
from widgets import CustomTitleBar


class EncryptDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mode="encrypt"):
        super().__init__(parent)
        self.mode = mode
        self.errors = []
        self.current_file = ""
        self.settings = load_settings()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)  # type: ignore[attr-defined]
        self.setWindowTitle("Encryption" if mode == "encrypt" else "Decryption")
        # DPI-scaled size from config
        resize_w, resize_h = scale_size(WindowSizes.ENCRYPT_DIALOG_WIDTH, WindowSizes.ENCRYPT_DIALOG_HEIGHT)
        self.resize(resize_w, resize_h)
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
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
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
        self.pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        pw_layout.addWidget(QtWidgets.QLabel("Password:"))
        pw_layout.addWidget(self.pass_input)

        if self.mode == "encrypt":
            self.confirm_pass_input = QtWidgets.QLineEdit()
            self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
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
        # DPI-scaled width from config: base 77 at 96 DPI (10% reduction)
        self.threads_combo.setFixedWidth(scale_value(ComboBoxSizes.CPU_THREADS_WIDTH))

        if str(default_threads) in [str(i) for i in range(1, max_safe + 1)]:
            self.threads_combo.setCurrentText(str(default_threads))

        # chunk size
        self.chunk_combo = QtWidgets.QComboBox()
        # DPI-scaled initial width from config: base 81 at 96 DPI (10% reduction)
        self.chunk_combo.setFixedWidth(scale_value(ComboBoxSizes.CHUNK_WIDTH))
        
        for label, val in ChunkSizeOptions.get_options():
            self.chunk_combo.addItem(label, val)
        # Automatically size based on content
        self.chunk_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)

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
            self.alg_combo.setFixedWidth(scale_value(ComboBoxSizes.ALG_WIDTH))
            for label, mode_id in EncryptionModes.get_options():
                self.alg_combo.addItem(label, mode_id)
            try:
                default_algo = self.settings.get("advanced", {}).get("encryption_mode", "aes256_gcm")
                idx = self.alg_combo.findData(default_algo)
                if idx >= 0:
                    self.alg_combo.setCurrentIndex(idx)
            except Exception:
                pass
            # Automatically size based on content
            self.alg_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
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
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
            if self.mode == "encrypt":
                self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)
        else:
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            if self.mode == "encrypt":
                self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

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

            if etype == QtCore.QEvent.Type.DragEnter:  # type: ignore[attr-defined]
                get_mime = getattr(event, 'mimeData', None)
                mime = get_mime() if callable(get_mime) else None
                if mime and getattr(mime, 'hasUrls', lambda: False)():
                    accept_fn = getattr(event, 'accept', None)
                    if callable(accept_fn):
                        accept_fn()
                    return True

            if etype == QtCore.QEvent.Type.Drop:  # type: ignore[attr-defined]
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
            elided = fm.elidedText(display, Qt.TextElideMode.ElideMiddle, avail)
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

