# widgets/__init__.py
# Public API for widgets module - exports custom widgets and UI components

from widgets.custom_title_bar import CustomTitleBar, show_message

__all__ = [
    'CustomTitleBar',
    'show_message',
]
