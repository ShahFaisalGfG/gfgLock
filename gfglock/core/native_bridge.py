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

# Version 2 moved naming and deletion out of C++ (an older module's unsafe logic must not run);
# version 4 gave both transforms a read size argument. An older module left on disk is ignored.
REQUIRED_API_VERSION = 4

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
    except Exception as error:
        _log(f"Native key derivation failed ({error}); using the Python fallback")
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)

# ── File transforms ──────────────────────────────────────────────────────────

def encrypt_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    original_name: str,
    password: str,
    read_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str]:
    """Encrypt input_path into output_path natively ("gcm", "cfb", or "chacha"); read_size 0 is the default.

    Returns (ok, error).
    """
    try:
        assert NATIVE_AVAILABLE and _native is not None
        ok, error = _native.encrypt_file(algorithm, input_path, output_path, original_name, password, read_size, callback)
        return bool(ok), str(error)
    except Exception as e:
        return False, str(e) or repr(e)


def decrypt_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    password: str,
    read_size: int = 0,
    callback: Optional[Callable[[float], None]] = None,
) -> tuple[bool, str, bytes]:
    """Decrypt input_path into output_path natively. Returns (ok, error, stored_name_bytes)."""
    try:
        assert NATIVE_AVAILABLE and _native is not None
        ok, error, name = _native.decrypt_file(algorithm, input_path, output_path, password, read_size, callback)
        return bool(ok), str(error), bytes(name)
    except Exception as e:
        return False, str(e) or repr(e), b""
