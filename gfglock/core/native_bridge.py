# native_bridge.py — Python gateway to the gfglock_native C++ extension.
# Provides typed wrappers with transparent CPU fallback when the .pyd is absent.

import hashlib
import os
import sys
from typing import Callable, Optional

# ── Locate and load the .pyd ──────────────────────────────────────────────────

def _core_dir() -> str:
    """Return the directory that contains this file (gfglock/core/)."""
    return os.path.dirname(os.path.abspath(__file__))


def _frozen_core_dir() -> str:
    """Return the _MEIPASS-relative path used in PyInstaller frozen builds."""
    meipass = getattr(sys, "_MEIPASS", None)
    return os.path.join(meipass, "gfglock", "core") if meipass else _core_dir()


def _log(msg: str) -> None:
    """Write msg to stdout; avoids importing helpers to prevent circular imports."""
    try:
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(msg, flush=True)
        except Exception:
            pass


_pyd_dir = _frozen_core_dir()
if _pyd_dir not in sys.path:
    sys.path.insert(0, _pyd_dir)

try:
    import gfglock_native as _native  # type: ignore[import]
    NATIVE_AVAILABLE: bool = True
except ImportError:
    _native = None
    NATIVE_AVAILABLE = False

# ── KDF ───────────────────────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes, iterations: int = 200000) -> bytes:
    """Derive a 32-byte key via PBKDF2-HMAC-SHA256 (native when available)."""
    try:
        if NATIVE_AVAILABLE and _native is not None:
            return bytes(_native.pbkdf2_sha256(password, salt, iterations, 32))
    except Exception:
        pass
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)

# ── AES-256-GCM ───────────────────────────────────────────────────────────────

def encrypt_gcm(
    path: str,
    password: str,
    encrypt_name: bool = False,
    chunk_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Encrypt a file with AES-256-GCM via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.encrypt_gcm(path, password, encrypt_name, chunk_size, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while encrypting {path}: {e}"


def decrypt_gcm(
    path: str,
    password: str,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Decrypt a .gfglock file with AES-256-GCM via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.decrypt_gcm(path, password, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while decrypting {path}: {e}"

# ── AES-256-CFB ───────────────────────────────────────────────────────────────

def encrypt_cfb(
    path: str,
    password: str,
    encrypt_name: bool = False,
    chunk_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Encrypt a file with AES-256-CFB via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.encrypt_cfb(path, password, encrypt_name, chunk_size, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while encrypting {path}: {e}"


def decrypt_cfb(
    path: str,
    password: str,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Decrypt a .gfglck file with AES-256-CFB via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.decrypt_cfb(path, password, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while decrypting {path}: {e}"

# ── ChaCha20-Poly1305 ─────────────────────────────────────────────────────────

def encrypt_chacha(
    path: str,
    password: str,
    encrypt_name: bool = False,
    chunk_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Encrypt a file with ChaCha20-Poly1305 via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.encrypt_chacha(path, password, encrypt_name, chunk_size, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while encrypting {path}: {e}"


def decrypt_chacha(
    path: str,
    password: str,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Decrypt a .gfgcha file with ChaCha20-Poly1305 via the native module."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        result = _native.decrypt_chacha(path, password, callback)
        return bool(result[0]), str(result[1])
    except Exception as e:
        return False, f"Critical error while decrypting {path}: {e}"

