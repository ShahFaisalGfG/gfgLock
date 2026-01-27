from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from config import AppInfo, WindowSizes, Spacing, ButtonSizes, FontSizes, IconSizes, StyleSheets, scale_size, scale_value
from utils import apply_theme
from utils import load_settings, resource_path
from views.encrypt_dialog import EncryptDialog
from views.preferences import PreferencesWindow
from widgets import CustomTitleBar


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)  # type: ignore[attr-defined]
        self.setWindowTitle("gfgLock")
        self.resize(*scale_size(WindowSizes.MAIN_WINDOW_WIDTH, WindowSizes.MAIN_WINDOW_HEIGHT))
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
                target_size = scale_value(IconSizes.HEADER_CONTAINER * 2)
                pix_scaled = pix.scaledToWidth(target_size, Qt.TransformationMode.SmoothTransformation)  # type: ignore[attr-defined]
                pix_scaled.setDevicePixelRatio(2.0)
                icon_lbl.setPixmap(pix_scaled)
                icon_lbl.setFixedSize(scale_value(IconSizes.HEADER_CONTAINER), scale_value(IconSizes.HEADER_CONTAINER))
                header_layout.addWidget(icon_lbl)
        except Exception:
            pass

        title_layout = QtWidgets.QVBoxLayout()
        title_lbl = QtWidgets.QLabel(f"<span style='{StyleSheets.MAIN_TITLE_LABEL}'>gfgLock</span>")
        title_lbl.setObjectName("title_label")
        title_lbl.setTextFormat(Qt.TextFormat.RichText)  # type: ignore[attr-defined]
        subtitle_lbl = QtWidgets.QLabel("Secure AES-256 file encryption and decryption — fast, simple, reliable")
        subtitle_lbl.setObjectName("subtitle_label")
        subtitle_lbl.setStyleSheet(StyleSheets.MAIN_SUBTITLE)

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
        main_btn_style = ButtonSizes.BUTTON_STYLE + ButtonSizes.BUTTON_BOLD_WEIGHT
        for b in (self.btn_encrypt, self.btn_decrypt, self.btn_prefs, self.btn_about, self.btn_update):
            b.setStyleSheet(main_btn_style)
            b.setMinimumHeight(scale_value(ButtonSizes.MAIN_BUTTON_HEIGHT))

        h.addWidget(self.btn_encrypt)
        h.addWidget(self.btn_decrypt)
        h.addStretch(1)
        h.addWidget(self.btn_update)
        h.addWidget(self.btn_prefs)
        h.addWidget(self.btn_about)
        v.addLayout(h)

        self.btn_encrypt.clicked.connect(lambda: EncryptDialog(self, "encrypt").exec()) # type: ignore
        self.btn_decrypt.clicked.connect(lambda: EncryptDialog(self, "decrypt").exec()) # type: ignore
        self.btn_prefs.clicked.connect(self.open_preferences) # type: ignore
        self.btn_about.clicked.connect(self.show_about_dialog) # type: ignore

        # Check Updates button opens GitHub releases
        def _open_updates():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/ShahFaisalGfG/gfgLock/releases/"))
        self.btn_update.clicked.connect(_open_updates)
        self.btn_update.setToolTip("Open GitHub releases page to check for latest version")

        self.status = QtWidgets.QLabel("Ready")
        self.status.setStyleSheet(StyleSheets.STATUS_LABEL)
        v.addWidget(self.status)

        # Dev-only logs panel - Remove after testing
        self.logs_text = QtWidgets.QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setPlaceholderText("Output logs...")
        # Prefer horizontal scrolling for long lines
        try:
            self.logs_text.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
            self.logs_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)  # type: ignore[attr-defined]
        except Exception:
            pass
        v.addWidget(self.logs_text)
        # Clear logs button: place in bottom-right footer row to match dialogs
        self.btn_clear_logs = QtWidgets.QPushButton("🧹 Clear")
        self.btn_clear_logs.setToolTip("Clear all logs")
        self.btn_clear_logs.clicked.connect(self.clear_logs_panel)
        self.btn_clear_logs.setStyleSheet(main_btn_style)
        # DPI-scaled minimum height: base 31 at 96 DPI (10% reduction)
        self.btn_clear_logs.setMinimumHeight(scale_value(ButtonSizes.MAIN_BUTTON_HEIGHT))
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
        prefs_window.exec()

    def on_settings_changed(self, settings):
        """Handle settings changed signal."""
        self.settings = settings
        # Reapply theme if changed
        apply_theme(None, settings.get("theme", "system"))

    def show_about_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("About gfgLock")
        dlg.setWindowIcon(QtGui.QIcon(resource_path("./assets/icons/gfgLock.png")))

        dlg.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)  # type: ignore[attr-defined]
        layout = QtWidgets.QVBoxLayout(dlg)
        # custom title bar
        try:
            title_bar = CustomTitleBar("About gfgLock", dlg)
            layout.insertWidget(0, title_bar)
        except Exception:
            pass

        layout.setContentsMargins(scale_value(Spacing.DIALOG_PADDING), scale_value(Spacing.DIALOG_PADDING), scale_value(Spacing.DIALOG_PADDING), scale_value(Spacing.DIALOG_PADDING))
        layout.setSpacing(scale_value(Spacing.DIALOG_SPACING))

        # Centered header: logo, app name, subtitle
        header = QtWidgets.QWidget()
        hl = QtWidgets.QVBoxLayout(header)
        hl.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]

        try:
            pix = QtGui.QPixmap(resource_path("./assets/icons/gfgLock.png"))
            if not pix.isNull():
                logo = QtWidgets.QLabel()
                # Scale pixmap at 2x resolution for crisp display on high-DPI screens
                target_size = scale_value(IconSizes.LARGE * 2)
                pix_scaled = pix.scaledToWidth(target_size, Qt.TransformationMode.SmoothTransformation)  # type: ignore[attr-defined]
                pix_scaled.setDevicePixelRatio(2.0)
                logo.setPixmap(pix_scaled)
                logo.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
                hl.addWidget(logo)
        except Exception:
            pass

        title = QtWidgets.QLabel(f"<span style='{StyleSheets.ABOUT_TITLE}'>gfgLock</span>")
        title.setTextFormat(Qt.TextFormat.RichText)  # type: ignore[attr-defined]
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        hl.addWidget(title)

        version = QtWidgets.QLabel("v" + AppInfo.APP_VERSION)
        version.setObjectName("version_label")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        version.setStyleSheet(StyleSheets.ABOUT_VERSION)
        hl.addWidget(version)

        subtitle = QtWidgets.QLabel("Secure AES-256 file encryption and decryption")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)  # type: ignore[attr-defined]
        subtitle.setStyleSheet(StyleSheets.ABOUT_SUBTITLE)
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
        info_l.setLabelAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]
        info_l.addRow("Company:", QtWidgets.QLabel(AppInfo.APP_COMPANY))
        info_l.addRow("Author:", QtWidgets.QLabel(AppInfo.APP_AUTHOR))
        layout.addWidget(info)

        # Links row
        links = QtWidgets.QHBoxLayout()
        links.addStretch()

        email_btn = QtWidgets.QPushButton("Contact: shahfaisalgfg@outlook.com")
        email_btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_mail():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("mailto:shahfaisalgfg@outlook.com"))
        email_btn.clicked.connect(_open_mail)
        links.addWidget(email_btn)

        github_btn = QtWidgets.QPushButton("GitHub Repo")
        github_btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_github():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/ShahFaisalGfG/gfgLock"))
        github_btn.clicked.connect(_open_github)
        links.addWidget(github_btn)

        site_btn = QtWidgets.QPushButton("Website")
        site_btn.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))  # type: ignore[attr-defined]
        def _open_site():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://shahfaisalgfg.github.io/shahfaisal"))
        site_btn.clicked.connect(_open_site)
        links.addWidget(site_btn)

        links.addStretch()
        layout.addLayout(links)

        # Close button
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        # Apply bold styling to OK button
        ok_button = btns.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setStyleSheet(ButtonSizes.BUTTON_STYLE + ButtonSizes.BUTTON_BOLD_WEIGHT)
        layout.addWidget(btns)

        dlg.exec()

