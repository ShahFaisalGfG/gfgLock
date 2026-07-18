# ui_config.py - centralized UI size constants and DPI utilities for gfgLock
# QML owns all visual styling; this file provides size/spacing data and DPI helpers.

from typing import Tuple

from PySide6 import QtGui


def get_dpi_scale() -> float:
    """Return screen DPI scaling factor (1.0 at 96 DPI)."""
    try:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return 1.0
        dpi = screen.logicalDotsPerInch()
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


def scale_size(width: int, height: int) -> Tuple[int, int]:
    """Scale a (width, height) pair by DPI factor."""
    scale = get_dpi_scale()
    return int(width * scale), int(height * scale)


def scale_value(value: int) -> int:
    """Scale a single pixel value by DPI factor."""
    return int(value * get_dpi_scale())


class WindowSizes:
    """Window and dialog base dimensions (at 96 DPI)."""

    MAIN_WINDOW_WIDTH = 648
    MAIN_WINDOW_HEIGHT = 423
    ENCRYPT_DIALOG_WIDTH = 900
    ENCRYPT_DIALOG_HEIGHT = 600
    PREFERENCES_WINDOW_WIDTH = 540
    PREFERENCES_WINDOW_HEIGHT = 630
    PROGRESS_DIALOG_WIDTH = 558
    PROGRESS_DIALOG_HEIGHT = 342
    MESSAGE_DIALOG_WIDTH = 340
    MESSAGE_DIALOG_HEIGHT = 130


class IconSizes:
    """Icon dimensions used throughout the UI."""

    MEDIUM = 32
    HEADER_CONTAINER = 56
    LARGE = 96


class ButtonSizes:
    """Button dimension constants."""

    TITLE_BAR_WIDTH = 32
    TITLE_BAR_HEIGHT = 25
    MAIN_BUTTON_HEIGHT = 31
    DIALOG_BUTTON_HEIGHT = 26


class Spacing:
    """Layout spacing and margin constants."""

    TITLE_BAR_HEIGHT = 31
    TITLE_BAR_MARGINS = 7
    TITLE_BAR_SPACING = 5
    DIALOG_PADDING = 14
    DIALOG_SPACING = 9
    GROUPBOX_MARGIN_TOP = 8
    TAB_PADDING_VERTICAL = 6
    TAB_PADDING_HORIZONTAL = 12
    WINDOW_RESIZE_MARGIN = 6


class FontSizes:
    """Font size constants (in points)."""

    MAIN_TITLE = 15
    DIALOG_TITLE = 16
    COMPACT_DIALOG_TITLE = 13
    SUBTITLE = 9
    VERSION = 8
    BODY = 9
    COMPACT_BODY = 8
    TITLE_BAR = 10
    INFO = 8


class ComboBoxSizes:
    """ComboBox width constants."""

    CPU_THREADS_WIDTH = 65
    CHUNK_WIDTH = 108
    ALG_WIDTH = 232
    COMPACT_INPUT_HEIGHT = 26


class LabelSizes:
    """Label and text widget size constants."""

    CURRENT_FILE_HEIGHT = 18
    LOGS_MIN_HEIGHT = 90
    TITLE_BAR_HEIGHT = 31


class ThemeColors:
    """Accent color constants (shared between light and dark themes)."""

    ACCENT_COLOR = "#0078d4"
    LIGHT_ACCENT = "#0078d4"
    DARK_ACCENT = "#0078d4"


class EncryptionModes:
    """Encryption algorithm options for UI dropdowns."""

    OPTIONS = [
        ("AES-256 GCM (Recommended - AEAD)", "aes256_gcm"),
        ("AES-256 CFB (Fast - No AEAD)", "aes256_cfb"),
        ("ChaCha20-Poly1305 (AEAD)", "chacha20_poly1305"),
    ]

    @staticmethod
    def get_options() -> list:
        """Return list of (label, mode_id) tuples."""
        return EncryptionModes.OPTIONS


class ChunkSizeOptions:
    """Chunk size options for file I/O (label, bytes)."""

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
        """Return list of (label, size_in_bytes) tuples."""
        return ChunkSizeOptions.OPTIONS


class FileItemSizes:
    """Size constants for file list items."""

    MIN_HEIGHT = 96
    PADDING = (12, 10, 12, 10)
    MAIN_SPACING = 16
    LEFT_WIDTH = 90
    ICON_SIZE = 64
    EMPTY_MIN_HEIGHT = 140
    ELIDE_OFFSET = 140
    SCROLLBAR_WIDTH = 10
    CONTAINER_RADIUS = 8


class FileItemColors:
    """Color hints for file item extension badges."""

    EXT_BG_LIGHT = "rgba(0, 120, 212, 0.08)"
    EXT_BG_DARK = "rgba(0, 120, 212, 0.15)"
    EXT_TEXT = "#0078d4"


def get_scaled_window_size(width: int, height: int) -> Tuple[int, int]:
    """Return a window size scaled by the current DPI factor."""
    return scale_size(width, height)


def get_dialog_margins() -> Tuple[int, int, int, int]:
    """Return standard dialog margins scaled to the current DPI."""
    margin = scale_value(Spacing.DIALOG_PADDING)
    return (margin, margin, margin, margin)
