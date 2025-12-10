# gui.py
import sys
import os

from PyQt5.QtCore import Qt

os.environ["QT_QPA_PLATFORM"] = "windows"

from PyQt5 import QtWidgets, QtCore, QtGui
from worker import EncryptDecryptWorker
import gfglock_fast_aes256_cryptography as core

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


class ProgressDialog(QtWidgets.QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        help_action = QtWidgets.QAction("Help", self)
        help_action.triggered.connect(lambda: QtWidgets.QMessageBox.information(
            self,
            "Usage Guide",
            "See README.md for full usage instructions:\nhttps://github.com/shahfaisalgfg/gfgLock"
        ))
        self.addAction(help_action)
        self.setWindowTitle("Progress")
        self.resize(520, 160)
        self.setWindowIcon(QtGui.QIcon(resource_path("assets/icons/gfgLock.png")))

        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        self.label_current = QtWidgets.QLabel("Current file:")
        layout.addWidget(self.label_current)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, total)
        layout.addWidget(self.progress_bar)

        self.detail = QtWidgets.QLabel(f"0/{total}")
        layout.addWidget(self.detail)

        h = QtWidgets.QHBoxLayout()
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        h.addStretch()
        h.addWidget(self.btn_cancel)
        layout.addLayout(h)


class EncryptDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, mode="encrypt"):
        super().__init__(parent)
        self.mode = mode

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowTitle("Encryption" if mode == "encrypt" else "Decryption")
        self.resize(700, 480)
        self.setWindowIcon(QtGui.QIcon(resource_path("assets/icons/gfgLock.png")))

        main = QtWidgets.QVBoxLayout(self)

        # File list
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        main.addWidget(self.list_widget)

        # Add files/folders
        h = QtWidgets.QHBoxLayout()
        self.btn_add_files = QtWidgets.QPushButton("Add Files")
        self.btn_add_folders = QtWidgets.QPushButton("Add Folders")
        self.btn_remove = QtWidgets.QPushButton("Remove Selected")
        h.addWidget(self.btn_add_files)
        h.addWidget(self.btn_add_folders)
        h.addWidget(self.btn_remove)
        main.addLayout(h)

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

        form.addRow(pw_layout)



        # CPU Threads + Chunk Size on same row
        row = QtWidgets.QHBoxLayout()

        # CPU threads
        total_threads = os.cpu_count() or 1
        max_safe = max(total_threads - 1, 1)
        self.threads_combo = QtWidgets.QComboBox()
        for i in range(1, max_safe + 1):
            self.threads_combo.addItem(str(i))
        self.threads_combo.setFixedWidth(120)

        default_thr = max(1, total_threads // 2)
        if str(default_thr) in [str(i) for i in range(1, max_safe + 1)]:
            self.threads_combo.setCurrentText(str(default_thr))

        # chunk size
        self.chunk_combo = QtWidgets.QComboBox()
        chunks = [
            ("1 MB", 1*1024*1024),
            ("8 MB (default)", 8*1024*1024),
            ("16 MB (fast)", 16*1024*1024),
            ("18 MB (fast)", 18*1024*1024),
            ("32 MB", 32*1024*1024),
        ]
        for label, val in chunks:
            self.chunk_combo.addItem(label, val)
        self.chunk_combo.setFixedWidth(150)
        self.chunk_combo.setCurrentText("18 MB (fast)")

        row.addWidget(QtWidgets.QLabel("CPU Threads:"))
        row.addWidget(self.threads_combo)
        row.addWidget(QtWidgets.QLabel("Chunk Size:"))
        row.addWidget(self.chunk_combo)
        row.addStretch()
        form.addRow(row)

        # Encrypt filenames + Show Password
        if self.mode == "encrypt":
            bottom_row = QtWidgets.QHBoxLayout()
            self.encrypt_name_cb = QtWidgets.QCheckBox("Encrypt filenames")
            self.show_pass_cb = QtWidgets.QCheckBox("Show Password")
            self.show_pass_cb.stateChanged.connect(self.toggle_password)
            bottom_row.addWidget(self.encrypt_name_cb)
            bottom_row.addWidget(self.show_pass_cb)
            bottom_row.addStretch()
            form.addRow(bottom_row)

        main.addLayout(form)

        # Bottom Start/Cancel buttons
        bottom = QtWidgets.QHBoxLayout()
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_start = QtWidgets.QPushButton(
            "Start Encryption" if self.mode == "encrypt" else "Start Decryption"
        )
        bottom.addStretch()
        bottom.addWidget(self.btn_cancel)
        bottom.addWidget(self.btn_start)
        main.addLayout(bottom)

        # Connect signals
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_add_folders.clicked.connect(self.add_folders)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_start.clicked.connect(self.start_op)

        self.worker = None
        self.progress_dlg = None
        self.threadpool = QtCore.QThreadPool.globalInstance()

    def toggle_password(self):
        if self.show_pass_cb.isChecked():
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self.pass_input.setEchoMode(QtWidgets.QLineEdit.Password)
            self.confirm_pass_input.setEchoMode(QtWidgets.QLineEdit.Password)

    def add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select files")
        for f in files:
            self.list_widget.addItem(f)

    def add_folders(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            import os
            for root, _, files in os.walk(folder):
                for fn in files:
                    self.list_widget.addItem(os.path.join(root, fn))

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def start_op(self):
        paths = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

        if not paths:
            QtWidgets.QMessageBox.warning(self, "No files", "Add files first.")
            return

        password = self.pass_input.text().strip()
        if not password:
            QtWidgets.QMessageBox.warning(self, "Password required", "Enter a password.")
            return

        if self.mode == "encrypt":
            confirm_password = self.confirm_pass_input.text().strip()
            if not confirm_password:
                QtWidgets.QMessageBox.warning(self, "Confirm required", "Please confirm your password.")
                return
            if password != confirm_password:
                QtWidgets.QMessageBox.warning(self, "Password mismatch", "Password and Confirm Password must match.")
                return

        threads = int(self.threads_combo.currentText())
        chunk_size = self.chunk_combo.currentData()
        encrypt_name = self.encrypt_name_cb.isChecked() if self.mode == "encrypt" else False

        threads = int(self.threads_combo.currentText())
        chunk_size = self.chunk_combo.currentData()
        encrypt_name = self.encrypt_name_cb.isChecked() if self.mode == "encrypt" else False

        # Progress dialog
        self.progress_dlg = ProgressDialog(len(paths), self)
        self.progress_dlg.show()
        QtWidgets.QApplication.processEvents()

        # Worker
        self.worker = EncryptDecryptWorker(
            paths, password,
            mode=self.mode,
            encrypt_name=encrypt_name,
            threads=threads,
            chunk_size=chunk_size
        )

        self.worker.signals.progress.connect(self.on_progress, QtCore.Qt.QueuedConnection)
        self.worker.signals.file_changed.connect(self.on_current_file, QtCore.Qt.QueuedConnection)
        self.worker.signals.status.connect(self.on_status, QtCore.Qt.QueuedConnection)
        self.worker.signals.error.connect(self.on_error, QtCore.Qt.QueuedConnection)
        self.worker.signals.finished.connect(self.on_finished, QtCore.Qt.QueuedConnection)

        self.progress_dlg.btn_cancel.clicked.connect(self.worker.cancel)

        self.threadpool.start(self.worker)

    def on_progress(self, done, total):
        self.progress_dlg.progress_bar.setValue(done)
        self.progress_dlg.detail.setText(f"{done}/{total}")

    def on_current_file(self, text):
        self.progress_dlg.label_current.setText("Current: " + text)

    def on_status(self, msg):
        self.progress_dlg.detail.setText(msg)

    def on_error(self, msg):
        QtWidgets.QMessageBox.critical(self, "Error", msg)

    def on_finished(self, elapsed, total):
        op = "Encrypted" if self.mode == "encrypt" else "Decrypted"
        QtWidgets.QMessageBox.information(
            self,
            f"{op} Completed",
            f"{op} Completed\n\n{op} {total} files in {elapsed:.2f} seconds."
        )
        self.progress_dlg.close()
        self.accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowTitle("gfgLock")
        self.resize(720, 420)
        self.setWindowIcon(QtGui.QIcon(resource_path("assets/icons/gfgLock.ico")))

        main = QtWidgets.QWidget()
        self.setCentralWidget(main)

        v = QtWidgets.QVBoxLayout(main)

        header = QtWidgets.QLabel("<h2>gfgLock – Encrypt / Decrypt</h2>")
        v.addWidget(header)

        h = QtWidgets.QHBoxLayout()
        self.btn_encrypt = QtWidgets.QPushButton("Encryption")
        self.btn_decrypt = QtWidgets.QPushButton("Decryption")
        self.btn_prefs = QtWidgets.QPushButton("Preferences")
        self.btn_about = QtWidgets.QPushButton("About")
        h.addWidget(self.btn_encrypt)
        h.addWidget(self.btn_decrypt)
        h.addWidget(self.btn_prefs)
        h.addWidget(self.btn_about)
        v.addLayout(h)

        self.btn_encrypt.clicked.connect(lambda: EncryptDialog(self, "encrypt").exec_())
        self.btn_decrypt.clicked.connect(lambda: EncryptDialog(self, "decrypt").exec_())
        self.btn_prefs.clicked.connect(lambda: QtWidgets.QMessageBox.information(self, "Preferences", "Coming soon."))
        self.btn_about.clicked.connect(lambda: QtWidgets.QMessageBox.information(self, "About",
            "gfgLock\nDeveloped by Shah Faisal\ngfgroyal.com"))

        self.status = QtWidgets.QLabel("Ready")
        v.addWidget(self.status)


def main():
    app = QtWidgets.QApplication(sys.argv)

    args = sys.argv[1:]
    if args:
        mode = None
        paths = []

        # First argument is explicit mode from registry
        if args[0].lower() == "encrypt":
            mode = "encrypt"
            paths = args[1:]
        elif args[0].lower() == "decrypt":
            mode = "decrypt"
            paths = args[1:]

        if mode and paths:
            dlg = EncryptDialog(None, mode)
            for p in paths:
                if os.path.isfile(p):
                    dlg.list_widget.addItem(p)
                elif os.path.isdir(p):
                    for root, _, files in os.walk(p):
                        for fn in files:
                            dlg.list_widget.addItem(os.path.join(root, fn))
            dlg.exec_()
            sys.exit(0)

        # Auto-detect double-clicked .gfglock file
        gfglock_files = [a for a in args if os.path.isfile(a) and a.endswith(".gfglock")]
        if gfglock_files:
            dlg = EncryptDialog(None, "decrypt")
            for f in gfglock_files:
                dlg.list_widget.addItem(f)
            dlg.exec_()
            sys.exit(0)

    # Default launch → show main window
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
