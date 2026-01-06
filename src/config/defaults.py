# defaults.py
# Default application preferences and settings for gfgLock
# Centralized configuration for easy customization of default options

import os
from typing import Dict, Any


# ============== APP INFO ==============
class AppInfo:
    """Application information and metadata."""
    
    APP_NAME = "gfgLock"
    APP_VERSION = "2.7.0"
    APP_AUTHOR = "Shah Faisal"
    APP_COMPANY = "gfgRoyal"
    APP_DESCRIPTION = "Secure AES-256 file encryption and decryption — fast, simple, reliable"


# ============== HELPER FUNCTIONS ==============
def _get_cpu_thread_count() -> int:
    """Get logical CPU thread count for system.
    
    Local helper to avoid circular imports with gfg_helpers.
    Returns half the available threads (min 1) for default concurrency.
    """
    cpu_count_val = os.cpu_count()
    if cpu_count_val is None:
        return 1
    return max(1, cpu_count_val // 2)


# ============== THEME DEFAULTS ==============
class ThemeDefaults:
    """Default theme preferences."""
    
    # Default theme: "system" (auto-detect), "light", or "dark"
    DEFAULT_THEME = "system"
    
    # Supported themes
    SUPPORTED_THEMES = ["system", "light", "dark"]


# ============== ENCRYPTION DEFAULTS ==============
class EncryptionDefaults:
    """Default encryption settings."""
    
    # CPU threads for encryption (default: half of available threads, min 1)
    DEFAULT_THREADS = max(1, _get_cpu_thread_count() // 2)
    
    # Chunk size for file I/O (16 MB default, good balance of speed/memory)
    DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB
    
    # Encrypt filenames by default
    DEFAULT_ENCRYPT_FILENAMES = False


# ============== DECRYPTION DEFAULTS ==============
class DecryptionDefaults:
    """Default decryption settings."""
    
    # CPU threads for decryption (default: half of available threads, min 1)
    DEFAULT_THREADS = max(1, _get_cpu_thread_count() // 2)
    
    # Chunk size for file I/O (16 MB default, same as encryption)
    DEFAULT_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB
    
    # Note: encrypt_filenames is determined by file header during decryption
    # This setting is not used for decryption
    DEFAULT_ENCRYPT_FILENAMES = False


# ============== ENCRYPTION ALGORITHM DEFAULTS ==============
class AlgorithmDefaults:
    """Default encryption algorithm preferences."""
    
    # Default encryption algorithm: "aes256_gcm" (recommended, AEAD)
    # Options: "aes256_gcm", "aes256_cfb", "chacha20_poly1305"
    DEFAULT_ALGORITHM = "aes256_gcm"
    
    # Supported algorithms
    SUPPORTED_ALGORITHMS = ["aes256_gcm", "aes256_cfb", "chacha20_poly1305"]


# ============== LOGGING DEFAULTS ==============
class LoggingDefaults:
    """Default logging preferences."""
    
    # Enable logging by default
    ENABLE_LOGS = False
    
    # Log level: "critical" (only errors), "all" (all messages)
    DEFAULT_LOG_LEVEL = "critical"
    
    # Supported log levels
    SUPPORTED_LOG_LEVELS = ["critical", "all"]


# ============== COMPLETE DEFAULT SETTINGS ==============
def get_default_settings() -> Dict[str, Any]:
    """Get complete default application settings.
    
    Returns a dictionary with all default preference values for the application.
    This is used when settings.json doesn't exist or when resetting to defaults.
    
    Returns:
        Dict[str, Any]: Complete default settings structure
    """
    return {
        "theme": ThemeDefaults.DEFAULT_THEME,
        "encryption": {
            "cpu_threads": EncryptionDefaults.DEFAULT_THREADS,
            "chunk_size": EncryptionDefaults.DEFAULT_CHUNK_SIZE,
            "encrypt_filenames": EncryptionDefaults.DEFAULT_ENCRYPT_FILENAMES
        },
        "decryption": {
            "cpu_threads": DecryptionDefaults.DEFAULT_THREADS,
            "chunk_size": DecryptionDefaults.DEFAULT_CHUNK_SIZE,
            "encrypt_filenames": DecryptionDefaults.DEFAULT_ENCRYPT_FILENAMES
        },
        "advanced": {
            "encryption_mode": AlgorithmDefaults.DEFAULT_ALGORITHM,
            "enable_logs": LoggingDefaults.ENABLE_LOGS,
            "log_level": LoggingDefaults.DEFAULT_LOG_LEVEL
        }
    }


# ============== QUICK REFERENCE ==============
"""
Quick Reference for Default Values:

THEME:
  - "system" (auto-detect), "light", or "dark"
  - Default: "system"

ENCRYPTION:
  - cpu_threads: {EncryptionDefaults.DEFAULT_THREADS} (based on available CPUs)
  - chunk_size: {EncryptionDefaults.DEFAULT_CHUNK_SIZE} bytes (16 MB)
  - encrypt_filenames: {EncryptionDefaults.DEFAULT_ENCRYPT_FILENAMES}

DECRYPTION:
  - cpu_threads: {DecryptionDefaults.DEFAULT_THREADS} (based on available CPUs)
  - chunk_size: {DecryptionDefaults.DEFAULT_CHUNK_SIZE} bytes (16 MB)
  - encrypt_filenames: {DecryptionDefaults.DEFAULT_ENCRYPT_FILENAMES}

ADVANCED:
  - encryption_mode: "{AlgorithmDefaults.DEFAULT_ALGORITHM}"
    Options: "aes256_gcm" (recommended), "aes256_cfb", "chacha20_poly1305"
  - enable_logs: {LoggingDefaults.ENABLE_LOGS}
  - log_level: "{LoggingDefaults.DEFAULT_LOG_LEVEL}"
    Options: "critical", "all"

CUSTOMIZATION:
To change any default, modify the corresponding class constant above:
  1. ThemeDefaults.DEFAULT_THEME
  2. EncryptionDefaults.DEFAULT_*
  3. DecryptionDefaults.DEFAULT_*
  4. AlgorithmDefaults.DEFAULT_ALGORITHM
  5. LoggingDefaults.ENABLE_LOGS / DEFAULT_LOG_LEVEL

Example:
  # To change default encryption algorithm to ChaCha20:
  AlgorithmDefaults.DEFAULT_ALGORITHM = "chacha20_poly1305"
  
  # To enable logging by default:
  LoggingDefaults.ENABLE_LOGS = True
  
  # To change default theme to dark:
  ThemeDefaults.DEFAULT_THEME = "dark"
"""
