# config/__init__.py
# UI configuration and constants for gfgLock

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
    LabelSizes,
    ThemeColors,
    StyleSheets,
    EncryptionModes,
    ChunkSizeOptions,
    get_scaled_window_size,
    get_button_style,
    get_dialog_margins,
)

from config.defaults import (
    get_default_settings,
    ThemeDefaults,
    EncryptionDefaults,
    DecryptionDefaults,
    AlgorithmDefaults,
    LoggingDefaults,
)

__all__ = [
    # UI Config exports
    'get_dpi_scale',
    'scale_size',
    'scale_value',
    'WindowSizes',
    'IconSizes',
    'ButtonSizes',
    'Spacing',
    'FontSizes',
    'ComboBoxSizes',
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
