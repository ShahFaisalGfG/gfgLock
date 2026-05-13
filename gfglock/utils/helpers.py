# helpers.py — file/size/format utilities and cryptographic helpers

import hashlib
import os
import sys
from datetime import datetime
from multiprocessing import cpu_count
from secrets import token_hex


def resource_path(relative_path: str) -> str:
    """Return absolute path to a resource, works for dev and PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(os.path.dirname(utils_dir))  # project root
    return os.path.normpath(os.path.join(base, relative_path))


def get_cpu_thread_count() -> int:
    """Return the number of logical CPU threads available."""
    count = os.cpu_count()
    return 0 if count is None else count


def clamp_threads(threads: int) -> int:
    """Clamp thread count to a safe maximum (CPU count - 1, min 1)."""
    try:
        max_safe = max(cpu_count() - 1, 1)
    except Exception:
        max_safe = 1
    if not isinstance(threads, int) or threads < 1:
        return 1
    return min(threads, max_safe)


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        mins, secs = divmod(seconds, 60)
        return f"{mins} mins {secs} sec"
    else:
        hours, remainder = divmod(seconds, 3600)
        mins, secs = divmod(remainder, 60)
        return f"{hours} hrs {mins} mins {secs} sec"


def format_bytes(bytes_val: float, strip_zeros: bool = False) -> str:
    """Convert bytes to a human-readable size string."""
    bytes_val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024.0:
            result = f"{bytes_val:.1f} {unit}"
            if strip_zeros:
                result = result.rstrip("0").rstrip(".")
            return result
        bytes_val /= 1024.0
    result = f"{bytes_val:.1f} PB"
    if strip_zeros:
        result = result.rstrip("0").rstrip(".")
    return result


def format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def choose_scale(total_bytes: float) -> tuple:
    """Choose a (scale, unit, scaled_total) that fits in a signed 32-bit int."""
    units = ["B", "KB", "MB", "GB", "TB"]
    scaled = float(total_bytes)
    idx = 0
    MAX_INT32 = 2_147_483_647
    while scaled > MAX_INT32 and idx < len(units) - 1:
        scaled = (scaled + 1023) / 1024
        idx += 1
    return 1024 ** idx, units[idx], int(scaled)


def calculate_files_total_size(file_paths: list) -> float:
    """Return total size in bytes of all existing files in the list."""
    total = 0
    for file_path in file_paths:
        try:
            if os.path.isfile(file_path):
                total += os.path.getsize(file_path)
        except Exception:
            pass
    return total


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
    """Derive a 256-bit key from a password using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=32
    )


def safe_print(msg: str) -> None:
    """Write a UTF-8 message to stdout, safe for Windows console environments."""
    try:
        sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def generate_encrypted_name(src_path: str, encrypt_name: bool, ext: str) -> str:
    """Return the output filename for an encrypted file."""
    if encrypt_name:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        rand = token_hex(4)
        return f"{now}_{rand}{ext}"
    base = os.path.splitext(os.path.basename(src_path))[0]
    return base + ext
