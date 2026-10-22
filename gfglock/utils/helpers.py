# helpers.py - file, size, and name utilities

import os
import sys
from datetime import datetime
from secrets import token_hex


def resource_path(relative_path: str) -> str:
    """Return absolute path to a resource, works for dev and PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(os.path.dirname(utils_dir))  # project root
    return os.path.normpath(os.path.join(base, relative_path))


def format_bytes(bytes_val: float, strip_zeros: bool = False) -> str:
    """Convert bytes to a human-readable size string."""
    bytes_val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0:
            return _format_size(bytes_val, unit, strip_zeros)
        bytes_val /= 1024.0
    return _format_size(bytes_val, "PB", strip_zeros)


def _format_size(value: float, unit: str, strip_zeros: bool) -> str:
    """Format one (value, unit) pair, stripping a trailing '.0' when requested."""
    number = f"{value:.1f}"
    if strip_zeros:
        number = number.rstrip("0").rstrip(".")
    return f"{number} {unit}"


def generate_encrypted_name(src_path: str, encrypt_name: bool, ext: str) -> str:
    """Return the preferred output filename for an encrypted file.

    The full original name is kept (report.docx -> report.docx.gfglock) so files that differ
    only by extension never map to the same encrypted name. With encrypt_name, a timestamp
    plus random suffix hides the original name; it is restored from inside the file on decrypt.
    """
    if encrypt_name:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        rand = token_hex(4)
        return f"{now}_{rand}{ext}"
    return os.path.basename(src_path) + ext
