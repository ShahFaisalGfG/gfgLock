# helpers.py - file/size/format utilities and cryptographic helpers

import os
import sys
from datetime import datetime
from secrets import token_hex

from gfglock.core import native_bridge as _bridge
from gfglock.utils.console import safe_print


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


def predict_encrypted_size(file_path: str, mode: str = "GCM") -> int:
    """Return the exact expected size of the encrypted output file."""
    original_size = os.path.getsize(file_path)
    filename_len = len(os.path.basename(file_path).encode("utf-8"))
    mode_upper = mode.upper()
    if mode_upper in ("GCM", "CHACHA"):
        total_overhead = 49  # salt(16) + nonce(12) + tag(16) + chunk_field(4) + null(1)
    elif mode_upper == "CFB":
        total_overhead = 37  # salt(16) + iv(16) + chunk_field(4) + null(1)
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'GCM', 'CFB', or 'CHACHA'.")
    return original_size + filename_len + total_overhead


def derive_key(password: str, salt: bytes, iterations: int = 200000) -> bytes:
    """Derive a 256-bit key via PBKDF2-HMAC-SHA256 (native C++ when available)."""
    return _bridge.derive_key(password, salt, iterations)


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
