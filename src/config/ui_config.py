# ui_config.py
# Centralized UI configuration and styling constants for gfgLock
# All sizing, spacing, padding, and styling values in one place for easy customization

from typing import Tuple

# ============== DPI SCALING ==============
def get_dpi_scale() -> float:
    """Get screen DPI scaling factor for PyQt6 compatibility.
    
    Returns a multiplier to scale hardcoded sizes based on screen DPI.
    Standard DPI is 96, so a 150% scaled screen returns 1.5625.
    
    Returns:
        float: DPI scale factor (1.0 for 96 DPI, >1.0 for high-DPI displays)
    """
    try:
        from PyQt6 import QtGui
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return 1.0
        
        dpi = screen.logicalDotsPerInch()
        # Standard DPI is 96 on most systems
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


def scale_size(width: int, height: int) -> Tuple[int, int]:
    """Scale a size by DPI factor for PyQt6 high-DPI support.
    
    Args:
        width: Base width in pixels (at 96 DPI)
        height: Base height in pixels (at 96 DPI)
    
    Returns:
        Tuple[int, int]: Scaled (width, height)
    """
    scale = get_dpi_scale()
    return int(width * scale), int(height * scale)


def scale_value(value: int) -> int:
    """Scale a single value by DPI factor.
    
    Args:
        value: Base value in pixels (at 96 DPI)
    
    Returns:
        int: Scaled value
    """
    scale = get_dpi_scale()
    return int(value * scale)


# ============== WINDOW SIZES (Base values at 96 DPI, scaled by DPI factor) ==============
class WindowSizes:
    """Main application window and dialog sizes."""
    
    # MainWindow: 720x470 base → 648x423 (10% reduction)
    MAIN_WINDOW_WIDTH = 648
    MAIN_WINDOW_HEIGHT = 423

    # EncryptDialog: 720x470 base → 648x423 (10% reduction)
    ENCRYPT_DIALOG_WIDTH = 648
    ENCRYPT_DIALOG_HEIGHT = 423

    # PreferencesWindow: 540x630 (10% reduction)
    PREFERENCES_WINDOW_WIDTH = 540
    PREFERENCES_WINDOW_HEIGHT = 630
    
    # ProgressDialog: 558x342 base (10% reduction)
    PROGRESS_DIALOG_WIDTH = 558
    PROGRESS_DIALOG_MIN_HEIGHT = 342
    PROGRESS_DIALOG_HEIGHT = 333  # Slightly smaller for initial display
    
    # Message dialogs: 340x130 (10% reduction)
    MESSAGE_DIALOG_WIDTH = 340
    MESSAGE_DIALOG_HEIGHT = 130


# ============== ICON SIZES (Base values at 96 DPI, scaled by DPI factor) ==============
class IconSizes:
    """Icon dimensions used throughout the UI."""
    
    MEDIUM = 32
    HEADER_CONTAINER = 56
    LARGE = 96


# ============== BUTTON SIZES (Base values at 96 DPI, scaled by DPI factor) ==============
class ButtonSizes:
    """Button dimensions used in UI."""
    
    # Custom title bar buttons: 32x25 base (10% reduction from 36x28)
    TITLE_BAR_WIDTH = 32
    TITLE_BAR_HEIGHT = 25
    
    # Main window buttons: 31px height (10% reduction from 34)
    MAIN_BUTTON_HEIGHT = 31
    
    # Button padding: 7px 11px (10% reduction from 8px 12px)
    BUTTON_PADDING = "7px 11px"
    BUTTON_STYLE = f"font-size:9pt; padding:{BUTTON_PADDING};"


# ============== SPACING & PADDING (Base values at 96 DPI, scaled by DPI factor) ==============
class Spacing:
    """Spacing and padding constants for layouts and widgets."""
    
    # Title bar layout
    TITLE_BAR_HEIGHT = 31  # DPI-scaled
    TITLE_BAR_MARGINS = 7  # Left/right margins (top/bottom = 0)
    TITLE_BAR_SPACING = 5  # Space between items
    
    # Dialog margins and padding
    DIALOG_PADDING = 14  # Standard dialog padding (10% reduction from 16)
    DIALOG_MARGINS = (14, 14, 14, 14)  # (left, top, right, bottom)
    DIALOG_SPACING = 9  # Vertical space between elements (10% reduction from 10)
    
    # GroupBox spacing
    GROUPBOX_MARGIN_TOP = 8
    GROUPBOX_PADDING_TOP = 8
    
    # Tab bar padding
    TAB_PADDING_VERTICAL = 6
    TAB_PADDING_HORIZONTAL = 12
    
    # Window resize edge margin: 6px (edge tolerance for cursor/resize detection)
    WINDOW_RESIZE_MARGIN = 6


# ============== FONT SIZES ==============
class FontSizes:
    """Font sizes used in UI (in points)."""
    
    # Main window title: 15pt (10% reduction from 16pt)
    MAIN_TITLE = 15
    
    # Dialog titles: 16pt (10% reduction from 18pt)
    DIALOG_TITLE = 16
    
    # Subtitles and descriptions: 9pt
    SUBTITLE = 9
    
    # Version and metadata: 8pt
    VERSION = 8
    
    # Default body text: 9pt
    BODY = 9
    
    # Title bar and button text: 10pt
    TITLE_BAR = 10
    
    # Small info text: 8pt
    INFO = 8


# ============== COMBO BOX SIZES ==============
class ComboBoxSizes:
    """ComboBox width settings."""
    
    CPU_THREADS_WIDTH = 65
    CHUNK_WIDTH = 108
    ALG_WIDTH = 232
# ============== LABEL HEIGHTS ==============
class LabelSizes:
    """Label and text widget sizes."""
    
    # Progress dialog current file label: 18px (10% reduction from 20)
    CURRENT_FILE_HEIGHT = 18
    
    # Progress bar logs minimum height: 90px (10% reduction from 100)
    LOGS_MIN_HEIGHT = 90


# ============== ENCRYPTION & CHUNK SIZE OPTIONS ==============
class EncryptionModes:
    """Encryption algorithm options for UI selection."""
    
    # List of (display_label, mode_id) tuples
    OPTIONS = [
        ("AES-256 GCM (Recommended - AEAD)", "aes256_gcm"),
        ("AES-256 CFB (Fast - No AEAD)", "aes256_cfb"),
        ("ChaCha20-Poly1305 (AEAD)", "chacha20_poly1305"),
    ]
    
    @staticmethod
    def get_options() -> list:
        """Get list of (label, mode_id) tuples for UI dropdowns."""
        return EncryptionModes.OPTIONS


class ChunkSizeOptions:
    """Chunk size options for file I/O."""
    
    # List of (display_label, bytes) tuples
    OPTIONS = [
        ("Off (no chunking)", None),
        ("8 MB (normal)", 8 * 1024 * 1024),
        ("16 MB (fast)", 16 * 1024 * 1024),
        ("32 MB (faster)", 32 * 1024 * 1024),
        ("64 MB (heavy)", 64 * 1024 * 1024),
        ("128 MB (experimental)", 128 * 1024 * 1024),
    ]
    
    @staticmethod
    def get_options() -> list:
        """Get list of (label, size_in_bytes) tuples for UI dropdowns."""
        return ChunkSizeOptions.OPTIONS





# ============== COLORS & THEME VALUES ==============
class ThemeColors:
    """Theme-related color values (note: actual colors defined in theme_manager.py stylesheets)."""
    
    # Light theme accent
    LIGHT_ACCENT = "#0078d4"
    
    # Dark theme accent
    DARK_ACCENT = "#0078d4"
    
    # Common accent color
    ACCENT_COLOR = "#0078d4"


# ============== STYLE SHEETS ==============
class StyleSheets:
    """Inline style sheet snippets for quick access."""
    
    # Button styling for main window buttons
    MAIN_BUTTON = f"font-size:9pt; padding:{ButtonSizes.BUTTON_PADDING};"
    
    # Clear logs button (uses theme color, no hardcoded color)
    CLEAR_LOGS = ""  # Inherits theme color, no hardcoded color
    
    # Version label (uses theme color via object name)
    VERSION_LABEL = f"font-size:{FontSizes.VERSION}pt; font-weight: 500;"
    
    # Subtitle (uses theme color via object name)
    SUBTITLE_LABEL = f"font-size:{FontSizes.SUBTITLE}pt;"


# ============== UTILITY FUNCTIONS ==============
def get_scaled_window_size(width: int, height: int) -> Tuple[int, int]:
    """Get a window size scaled by DPI factor."""
    return scale_size(width, height)


def get_button_style(font_size: int = 9, padding: str = ButtonSizes.BUTTON_PADDING) -> str:
    """Generate button style string."""
    return f"font-size:{font_size}pt; padding:{padding};"


def get_dialog_margins() -> Tuple[int, int, int, int]:
    """Get standard dialog margins (scaled)."""
    margin = scale_value(Spacing.DIALOG_PADDING)
    return (margin, margin, margin, margin)


