# defaults.py - default application preferences and the option lists shown in the UI

import os
from typing import Any, Dict


class AppInfo:
    """Application information and metadata."""

    APP_NAME = "gfgLock"
    APP_VERSION = "3.2.0"
    APP_AUTHOR = "Shah Faisal"
    APP_DESCRIPTION = "Lock files and folders with a password, using strong encryption"


def _get_cpu_thread_count() -> int:
    """Return half of available logical CPU threads (min 1)."""
    cpu_count_val = os.cpu_count()
    if cpu_count_val is None:
        return 1
    return max(1, cpu_count_val // 2)


def thread_limit(reserve_one: bool) -> int:
    """The most files a run works on at a time: every CPU thread, or one fewer kept free for Windows."""
    total = os.cpu_count() or 1
    return max(1, total - 1) if reserve_one else total


class ThemeDefaults:
    """Default theme preferences."""

    DEFAULT_THEME = "system"
    SUPPORTED_THEMES = ["system", "light", "dark"]
    OPTIONS = [
        ("System (follow Windows)", "system"),
        ("Light", "light"),
        ("Dark", "dark"),
    ]


class EncryptionDefaults:
    """Default encryption settings."""

    DEFAULT_THREADS = _get_cpu_thread_count()
    DEFAULT_ENCRYPT_FILENAMES = False


class DecryptionDefaults:
    """Default decryption settings."""

    DEFAULT_THREADS = _get_cpu_thread_count()


class AlgorithmDefaults:
    """Encryption algorithms: (label, code, what choosing it means)."""

    DEFAULT_ALGORITHM = "aes256_gcm"
    # AES-256 CFB (.gfglck) is no longer offered for new files; gfgLock still decrypts it.
    OPTIONS = [
        ("AES-256 GCM (recommended)", "aes256_gcm",
         "Strong encryption that also detects a damaged or altered file, and the fastest on most PCs."),
        ("ChaCha20-Poly1305", "chacha20_poly1305",
         "Just as strong and also detects changes; faster than GCM on PCs without AES hardware."),
    ]
    SUPPORTED_ALGORITHMS = [code for _, code, _ in OPTIONS]
    # The cipher name the encryption engine (gfglock.core.file_ops) uses for each code.
    CIPHERS = {"aes256_gcm": "gcm", "chacha20_poly1305": "chacha"}


class ReadSizeDefaults:
    """How much of a file is read at once: (label, bytes). 0 is the default size, 4 MB, which
    measured fastest on a typical desktop; the best size depends on the disk and CPU, so the
    Preferences window can time each size on this PC and save the fastest."""

    DEFAULT = 0
    # The size the default stands for (DEFAULT_BLOCK_SIZE in native/src/aes_cpu.cpp, BUFFER_SIZE in py_cipher).
    DEFAULT_BYTES = 4 * 1024 * 1024
    OPTIONS = [
        ("Default (4 MB)", DEFAULT),
        ("1 MB", 1 * 1024 * 1024),
        ("8 MB", 8 * 1024 * 1024),
        ("16 MB", 16 * 1024 * 1024),
        ("32 MB", 32 * 1024 * 1024),
        ("64 MB (uses the most memory)", 64 * 1024 * 1024),
    ]
    # Every size the speed test times, the default's included.
    TEST_SIZES = sorted([DEFAULT_BYTES] + [size for _, size in OPTIONS if size])


class LoggingDefaults:
    """Default logging preferences."""

    ENABLE_LOGS = False
    DEFAULT_LOG_LEVEL = "critical"
    OPTIONS = [
        ("Errors only", "critical"),
        ("Everything", "all"),
    ]
    SUPPORTED_LOG_LEVELS = [code for _, code in OPTIONS]


class PerformanceDefaults:
    """Default performance preferences."""

    CLAMP_CPU_THREADS = True


class NotificationDefaults:
    """Default notification preferences."""

    OPERATION_NOTIFICATIONS = True


def get_default_settings() -> Dict[str, Any]:
    """Return complete default settings dictionary."""
    return {
        "theme": ThemeDefaults.DEFAULT_THEME,
        "encryption": {
            "cpu_threads": EncryptionDefaults.DEFAULT_THREADS,
            "read_size": ReadSizeDefaults.DEFAULT,
            "encrypt_filenames": EncryptionDefaults.DEFAULT_ENCRYPT_FILENAMES,
        },
        "decryption": {
            "cpu_threads": DecryptionDefaults.DEFAULT_THREADS,
            "read_size": ReadSizeDefaults.DEFAULT,
        },
        "advanced": {
            "encryption_mode": AlgorithmDefaults.DEFAULT_ALGORITHM,
            "enable_logs": LoggingDefaults.ENABLE_LOGS,
            "log_level": LoggingDefaults.DEFAULT_LOG_LEVEL,
            "clamp_cpu_threads": PerformanceDefaults.CLAMP_CPU_THREADS,
            "operation_notifications": NotificationDefaults.OPERATION_NOTIFICATIONS,
        },
    }
