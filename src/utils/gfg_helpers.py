# gfg_helpers.py
# Shared helper functions for gfgLock encryption modules

import hashlib
import json
import os
import sys
from secrets import token_hex
from datetime import datetime
from typing import Dict, Any


# Note: config.defaults is imported lazily in functions to avoid circular imports


# ============== DEPRECATED: Use config instead ==============
# These functions are kept for backward compatibility but are deprecated
# All new code should import from config


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller.
    
    Prioritizes sys._MEIPASS (frozen/PyInstaller) over module directory.
    For development, uses the src directory as base.
    
    Args:
        relative_path: Path relative to base (e.g., "./assets/icons/gfgLock.png")
    
    Returns:
        Absolute normalized path to the resource.
    """
    base = getattr(sys, '_MEIPASS', None)
    if base is None:
        # Development: src directory is parent of utils directory
        utils_dir = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(utils_dir)  # Go up to src
    
    return os.path.normpath(os.path.join(base, relative_path))


def get_cpu_thread_count() -> int:
    """
    Detects the number of logical CPU threads available on the system.
    Returns(int): The number of logical CPU threads. Returns 0 if the number cannot be determined.
    """
    cpu_count_val = os.cpu_count()
    if cpu_count_val is None:
        return 0  # Return 0 if the count is undetermined
    return cpu_count_val

def clamp_threads(threads: int) -> int:
    """Clamp thread count to safe value (max = CPU count - 1).
    
    Args:
        threads: Desired thread count
    
    Returns:
        int: Safe thread count clamped to valid range
    """
    from multiprocessing import cpu_count
    try:
        max_safe = max(cpu_count() - 1, 1)
    except Exception:
        max_safe = 1
    if not isinstance(threads, int) or threads < 1:
        return 1
    return min(threads, max_safe)

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string for UI display.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        str: Formatted duration (e.g., "2 mins 30 sec", "1 hrs 5 mins 12 sec")
    """
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


def derive_key(password: str, salt: bytes, iterations: int = 200000) -> bytes:
    """PBKDF2 key derivation with salt for better security."""
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations, dklen=32)


def safe_print(msg: str) -> None:
    """Write message as UTF-8 bytes to stdout.buffer to avoid encoding errors in Windows workers."""
    try:
        out = sys.stdout.buffer
        out.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        out.flush()
    except Exception:
        try:
            # last resort
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
        except Exception:
            pass


# ============== SETTINGS MANAGEMENT ==============

def get_settings_file() -> str:
    """Get the path to the settings.json file."""
    # When frozen (PyInstaller/exe) we should store user-modifiable data
    # in the user's application data directory (e.g. %APPDATA% on Windows).
    try:
        if getattr(sys, 'frozen', False):
            appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
            data_dir = os.path.join(appdata, 'gfgLock')
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, 'settings.json')
    except Exception:
        pass

    # During development keep settings next to the package
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "settings.json")


def get_default_settings() -> Dict[str, Any]:
    """Get default application settings.
    
    Imported from config.defaults module - see that file for customization.
    """
    from config.defaults import get_default_settings as get_defaults
    return get_defaults()


def load_settings() -> Dict[str, Any]:
    """Load settings from file, create with defaults if not exists."""
    settings_file = get_settings_file()
    
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Merge with defaults to ensure all keys exist
                defaults = get_default_settings()
                merged = merge_settings(defaults, settings)
                return merged
        except Exception:
            pass
    
    # Return defaults if file doesn't exist or failed to load
    return get_default_settings()


def merge_settings(defaults: Dict[str, Any], user_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge user settings with defaults."""
    result = defaults.copy()
    for key, value in user_settings.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def save_settings(settings: Dict[str, Any]) -> bool:
    """Save settings to file."""
    try:
        settings_file = get_settings_file()
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception:
        return False


# ============== LOGGING MANAGEMENT ==============

def get_logs_dir() -> str:
    """Get the logs directory path, create if not exists."""
    # Prefer a per-user writable location when running as a bundled/frozen app
    try:
        if getattr(sys, 'frozen', False):
            appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
            logs_dir = os.path.join(appdata, 'gfgLock', 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            return logs_dir
    except Exception:
        pass

    # place logs folder inside the `src` package (one level above `utils`) during development
    app_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(app_dir)
    logs_dir = os.path.join(src_dir, "logs")
    
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except Exception:
            pass

    return logs_dir


def get_critical_log_file() -> str:
    """Get the critical logs file path."""
    logs_dir = get_logs_dir()
    return os.path.join(logs_dir, "gfglock_critical.log")


def get_general_log_file() -> str:
    """Get the general logs file path."""
    logs_dir = get_logs_dir()
    return os.path.join(logs_dir, "gfglock_general.log")


def write_critical_log(message: str) -> bool:
    """Write a critical error log message."""
    try:
        log_file = get_critical_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        return True
    except Exception:
        return False


def write_general_log(message: str) -> bool:
    """Write a general log message."""
    try:
        log_file = get_general_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        return True
    except Exception:
        return False


def write_log(message: str, level: str = "general") -> bool:
    """Write a log message based on level.
    
    level: "critical" or "general"
    If level is "all", both critical and general logs are written.
    """
    settings = load_settings()
    
    if not settings.get("advanced", {}).get("enable_logs", False):
        return False
    
    log_level = settings.get("advanced", {}).get("log_level", "critical")
    
    if log_level == "critical":
        return write_critical_log(message)
    elif log_level == "all":
        # Write to both logs when "all" is selected
        success1 = write_critical_log(message)
        success2 = write_general_log(message)
        return success1 and success2
    
    return False


def clear_logs() -> bool:
    """Clear all log files."""
    try:
        for log_file in [get_critical_log_file(), get_general_log_file()]:
            if os.path.exists(log_file):
                open(log_file, 'w', encoding='utf-8').close()
        return True
    except Exception:
        return False


def generate_encrypted_name(src_path: str, encrypt_name: bool, ext: str) -> str:
    """
    Generate an encrypted output filename for `src_path`.
    If `encrypt_name` is True a timestamp+random suffix is used, otherwise
    the original base name is preserved and the provided extension appended.

    Returns the file name (not full path).
    """
    if encrypt_name:
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        rand = token_hex(4)
        return f"{now}_{rand}{ext}"
    base = os.path.splitext(os.path.basename(src_path))[0]
    return base + ext

import os

def predict_encrypted_size(file_path, mode="GCM"):
    """
    Calculates the exact size of the resulting encrypted file.
    
    Modes:
    - 'CHACHA': For chacha20_poly1305.py (.gfgcha)
    - 'GCM': For aes256_gcm_cfb.py with AEAD=True (.gfglock)
    - 'CFB': For aes256_gcm_cfb.py with AEAD=False (.gfglck)
    
    Args:
        file_path: Path to original (unencrypted) file
        mode: Encryption mode ('GCM', 'CFB', or 'CHACHA')
    
    Returns:
        int: Predicted encrypted file size in bytes
    """
    original_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    # Filename is encoded to UTF-8 before encryption in your scripts
    filename_len = len(filename.encode('utf-8'))
    
    # Base overheads calculated from your scripts:
    # Salt(16) + ChunkField(4) + NullTerminator(1) = 21 (Common to all)
    common_overhead = 21 
    
    if mode.upper() == "CHACHA":
        # Common(21) + Nonce(12) + Tag(16) = 49
        total_overhead = 49
    elif mode.upper() == "GCM":
        # Common(21) + Nonce(12) + Tag(16) = 49
        total_overhead = 49
    elif mode.upper() == "CFB":
        # Common(21) + IV(16) + No Tag(0) = 37
        total_overhead = 37
    else:
        raise ValueError("Unknown mode. Use 'CHACHA', 'GCM', or 'CFB'.")

    return original_size + filename_len + total_overhead


def predict_decrypted_size(encrypted_file_path):
    """
    Estimates the original file size (decrypted) from an encrypted file.
    
    Since the original filename is encrypted within the file, we estimate based on
    the encrypted file size minus known fixed overhead. The filename length is 
    estimated using a heuristic (10-100 bytes typically).
    
    This avoids decrypting the file header which would slow down progress calculation
    without meaningful benefit. The estimate is usually within 1-5% of actual size.
    
    Encrypted file overhead breakdown:
    - GCM (.gfglock): Salt(16) + Nonce(12) + ChunkField(4) + Tag(16) = 48 bytes fixed
    - CFB (.gfglck): Salt(16) + IV(16) + ChunkField(4) = 36 bytes fixed
    - ChaCha (.gfgcha): Salt(16) + Nonce(12) + ChunkField(4) + Tag(16) = 48 bytes fixed
    - Plus: filename + null terminator (10-100 bytes estimated)
    
    Args:
        encrypted_file_path: Path to encrypted file (.gfglock, .gfglck, or .gfgcha)
    
    Returns:
        int: Estimated original file size in bytes
    
    Raises:
        ValueError: If file is not a recognized encrypted format or is corrupted
    """
    try:
        if not os.path.exists(encrypted_file_path):
            raise ValueError(f"File not found: {encrypted_file_path}")
        
        file_size = os.path.getsize(encrypted_file_path)
        
        # Determine encryption mode from file extension
        ext = os.path.splitext(encrypted_file_path)[1].lower()
        
        if ext == '.gfglock':
            # AES-256-GCM mode
            # Fixed overhead: Salt(16) + Nonce(12) + ChunkField(4) + Tag(16) = 48 bytes
            fixed_overhead = 48
            
        elif ext == '.gfglck':
            # AES-256-CFB mode (no authentication tag)
            # Fixed overhead: Salt(16) + IV(16) + ChunkField(4) = 36 bytes
            fixed_overhead = 36
            
        elif ext == '.gfgcha':
            # ChaCha20-Poly1305 mode
            # Fixed overhead: Salt(16) + Nonce(12) + ChunkField(4) + Tag(16) = 48 bytes
            fixed_overhead = 48
            
        else:
            raise ValueError(f"Unknown encrypted file format: {ext}. Expected .gfglock, .gfglck, or .gfgcha")
        
        # The remaining size after fixed overhead includes:
        # - Encrypted filename + null terminator (variable, estimated 10-100 bytes)
        # - Original file data (variable)
        remaining_size = file_size - fixed_overhead
        
        if remaining_size < 1:
            raise ValueError(f"Encrypted file appears corrupted: too small ({file_size} bytes)")
        
        # Estimate filename length using heuristic:
        # Most filenames when UTF-8 encoded are 10-100 bytes
        # Conservative estimate: assume filename is ~1% of remaining size, capped at 100 bytes
        # Minimum 10 bytes for very small files
        estimated_filename_len = min(max(remaining_size // 100, 10), 100)
        
        # Account for null terminator (1 byte after filename)
        estimated_metadata_len = estimated_filename_len + 1
        
        # Original file size = remaining_size - metadata_len
        estimated_original = remaining_size - estimated_metadata_len
        
        return max(estimated_original, 0)
        
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Error predicting decrypted size: {e}")


# Quick Test
# print(f"Predicted Encrypted Size: {predict_encrypted_size('my_video.mp4', 'GCM')} bytes")
# print(f"Predicted Decrypted Size: {predict_decrypted_size('my_video.mp4.gfglock')} bytes")