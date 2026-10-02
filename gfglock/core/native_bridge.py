# native_bridge.py - Python gateway to the gfglock_native C++ extension.
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

# The file-transform API changed in version 2 (explicit output path, no file deletion in C++).
# An older module left on disk is ignored so its unsafe naming/deletion logic can't run.
REQUIRED_API_VERSION = 2

try:
    import gfglock_native as _native  # type: ignore[import]
    NATIVE_AVAILABLE: bool = getattr(_native, "API_VERSION", 1) >= REQUIRED_API_VERSION
    if not NATIVE_AVAILABLE:
        _log("gfglock_native is outdated (rebuild with scripts/build_native.ps1); using the Python fallback")
        _native = None
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

# ── File transforms ──────────────────────────────────────────────────────────

def encrypt_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    original_name: str,
    password: str,
    chunk_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Encrypt input_path into output_path natively ("gcm", "cfb", or "chacha"). Returns (ok, error)."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        ok, error = _native.encrypt_file(algorithm, input_path, output_path, original_name, password, chunk_size, callback)
        return bool(ok), str(error)
    except Exception as e:
        return False, str(e) or repr(e)


def decrypt_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    password: str,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str, bytes]:
    """Decrypt input_path into output_path natively. Returns (ok, error, stored_name_bytes)."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        ok, error, name = _native.decrypt_file(algorithm, input_path, output_path, password, callback)
        return bool(ok), str(error), bytes(name)
    except Exception as e:
        return False, str(e) or repr(e), b""
