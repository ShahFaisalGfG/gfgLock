# config/__init__.py
# UI configuration and constants for gfgLock

from config.defaults import (
    AppInfo,
    get_default_settings,
    ThemeDefaults,
    EncryptionDefaults,
    DecryptionDefaults,
    AlgorithmDefaults,
    LoggingDefaults,
)
from config.ui_config import (
    get_dpi_scale,
    scale_size,
    scale_value,
    WindowSizes,
    IconSizes,
    ButtonSizes,
    Spacing,
    FontSizes,
    ComboBoxSizes,
    CheckBoxSizes,
    LabelSizes,
    ThemeColors,
    StyleSheets,
    EncryptionModes,
    ChunkSizeOptions,
    get_scaled_window_size,
    get_button_style,
    get_dialog_margins,
)

__all__ = [
    # UI Config exports
    'AppInfo',
    'get_dpi_scale',
    'scale_size',
    'scale_value',
    'WindowSizes',
    'IconSizes',
    'ButtonSizes',
    'Spacing',
    'FontSizes',
    'ComboBoxSizes',
    'CheckBoxSizes',
    'LabelSizes',
    'ThemeColors',
    'StyleSheets',
    'EncryptionModes',
    'ChunkSizeOptions',
    'get_scaled_window_size',
    'get_button_style',
    'get_dialog_margins',
    # Defaults exports
    'get_default_settings',
    'ThemeDefaults',
    'EncryptionDefaults',
    'DecryptionDefaults',
    'AlgorithmDefaults',
    'LoggingDefaults',
]
