# defaults.py — default application preferences and settings for gfgLock

import os
from typing import Any, Dict


class AppInfo:
    """Application information and metadata."""

    APP_NAME = "gfgLock"
    APP_VERSION = "2.7.5"
    APP_AUTHOR = "Shah Faisal"
    APP_COMPANY = "gfgRoyal"
    APP_DESCRIPTION = "Secure AES-256 file encryption and decryption — fast, simple, reliable"


def _get_cpu_thread_count() -> int:
    """Return half of available logical CPU threads (min 1)."""
    cpu_count_val = os.cpu_count()
    if cpu_count_val is None:
        return 1
    return max(1, cpu_count_val // 2)


class ThemeDefaults:
    """Default theme preferences."""

    DEFAULT_THEME = "system"
    SUPPORTED_THEMES = ["system", "light", "dark"]


class AppearanceDefaults:
    """Default appearance preferences."""

    LOG_TEXT_WRAP = True


class EncryptionDefaults:
    """Default encryption settings."""

    DEFAULT_THREADS = _get_cpu_thread_count()
    DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024
    DEFAULT_ENCRYPT_FILENAMES = False


class DecryptionDefaults:
    """Default decryption settings."""

    DEFAULT_THREADS = _get_cpu_thread_count()
    DEFAULT_CHUNK_SIZE = 32 * 1024 * 1024


class AlgorithmDefaults:
    """Default encryption algorithm preferences."""

    DEFAULT_ALGORITHM = "aes256_gcm"
    SUPPORTED_ALGORITHMS = ["aes256_gcm", "aes256_cfb", "chacha20_poly1305"]


class LoggingDefaults:
    """Default logging preferences."""

    ENABLE_LOGS = False
    DEFAULT_LOG_LEVEL = "critical"
    SUPPORTED_LOG_LEVELS = ["critical", "all"]


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
        "appearance": {
            "log_text_wrap": AppearanceDefaults.LOG_TEXT_WRAP,
        },
        "encryption": {
            "cpu_threads": EncryptionDefaults.DEFAULT_THREADS,
            "chunk_size": EncryptionDefaults.DEFAULT_CHUNK_SIZE,
            "encrypt_filenames": EncryptionDefaults.DEFAULT_ENCRYPT_FILENAMES,
        },
        "decryption": {
            "cpu_threads": DecryptionDefaults.DEFAULT_THREADS,
            "chunk_size": DecryptionDefaults.DEFAULT_CHUNK_SIZE,
        },
        "advanced": {
            "encryption_mode": AlgorithmDefaults.DEFAULT_ALGORITHM,
            "enable_logs": LoggingDefaults.ENABLE_LOGS,
            "log_level": LoggingDefaults.DEFAULT_LOG_LEVEL,
            "clamp_cpu_threads": PerformanceDefaults.CLAMP_CPU_THREADS,
            "operation_notifications": NotificationDefaults.OPERATION_NOTIFICATIONS,
        },
    }
