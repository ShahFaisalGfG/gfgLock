# views/__init__.py
# Public API for views module - exports all main window and dialog classes

from views.encrypt_dialog import EncryptDialog
from views.main_window import MainWindow
from views.preferences import PreferencesWindow
from views.progress_dialog import ProgressDialog

__all__ = [
    'MainWindow',
    'EncryptDialog',
    'ProgressDialog',
    'PreferencesWindow',
]
