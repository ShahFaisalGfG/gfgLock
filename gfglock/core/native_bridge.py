# native_bridge.py - Python gateway to the gfglock_native C++ extension (the native engine).
# Typed wrappers that turn native failures into the same (ok, error, ...) results as py_cipher;
# file_ops uses this engine while NATIVE_AVAILABLE is true and the Python one otherwise.

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Callable
from types import ModuleType
from typing import TYPE_CHECKING

from gfglock.utils.console import safe_print

if TYPE_CHECKING:
    from gfglock.core.py_cipher import StopToken

# ── Locate and load the .pyd ──────────────────────────────────────────────────

def _core_dir() -> str:
    """Return the directory that contains this file (gfglock/core/)."""
    return os.path.dirname(os.path.abspath(__file__))


def _frozen_core_dir() -> str:
    """Return the _MEIPASS-relative path used in PyInstaller frozen builds."""
    meipass = getattr(sys, "_MEIPASS", None)
    return os.path.join(meipass, "gfglock", "core") if meipass else _core_dir()


_pyd_dir = _frozen_core_dir()
if _pyd_dir not in sys.path:
    sys.path.insert(0, _pyd_dir)

# Version 2 moved naming and deletion out of C++ (an older module's unsafe logic must not run);
# version 4 added the read size; version 5 writes the v2 format (seal_file, open_file, CancelToken)
# and keeps v1 for decryption only. An older module left on disk is ignored.
REQUIRED_API_VERSION = 5
V1_ITERATIONS = 200_000
_NATIVE_ERRORS = (RuntimeError, ValueError, OSError, MemoryError)

try:
    import gfglock_native as _native  # type: ignore[import]
    NATIVE_AVAILABLE: bool = getattr(_native, "API_VERSION", 1) >= REQUIRED_API_VERSION
    if not NATIVE_AVAILABLE:
        safe_print("gfglock_native is outdated (rebuild with scripts/build_native.ps1); using the Python fallback")
        _native = None
except ModuleNotFoundError:
    _native = None
    NATIVE_AVAILABLE = False
except ImportError as load_error:  # the module is there but failed to load, e.g. a missing OpenSSL DLL
    safe_print(f"gfglock_native could not be loaded ({load_error}); using the Python fallback")
    _native = None
    NATIVE_AVAILABLE = False


def _module() -> ModuleType:
    """The loaded native module; raises RuntimeError while the Python engine is in use."""
    if not NATIVE_AVAILABLE or _native is None:
        raise RuntimeError("the native engine is not loaded")
    return _native

# ── Keys and versions ─────────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes, iterations: int = V1_ITERATIONS) -> bytes:
    """Derive a v1 file's 32-byte key with PBKDF2-HMAC-SHA256 (native when available)."""
    if NATIVE_AVAILABLE and _native is not None:
        try:
            return bytes(_native.pbkdf2_sha256(password, salt, iterations, 32))
        except _NATIVE_ERRORS as error:
            safe_print(f"Native key derivation failed ({error}); using the Python fallback")
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def new_cancel_token() -> StopToken:
    """A native CancelToken, the only kind the native transforms accept."""
    return _module().CancelToken()


def openssl_version() -> str:
    """The OpenSSL version the native module runs with ("" without the module)."""
    return str(_native.openssl_version()) if NATIVE_AVAILABLE and _native is not None else ""


def openssl_build_version() -> str:
    """The OpenSSL version the native module was compiled against ("" without the module)."""
    return str(_native.openssl_build_version()) if NATIVE_AVAILABLE and _native is not None else ""

# ── File transforms (same parameters and results as py_cipher) ────────────────

def seal_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    header: bytes,
    key: bytes,
    nonce_prefix: bytes,
    chunk_size: int,
    metadata: bytes,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: Callable[[float], None] | None = None,
) -> tuple[bool, str]:
    """Write header, then metadata + the input file sealed in chunks, to output_path. Returns (ok, error)."""
    try:
        ok, error = _module().seal_file(algorithm, input_path, output_path, header, key, nonce_prefix,
                                        chunk_size, metadata, block_size, cancel, callback)
        return bool(ok), str(error)
    except _NATIVE_ERRORS as error:
        return False, str(error) or repr(error)


def open_file(
    algorithm: str,
    input_path: str,
    output_path: str,
    header: bytes,
    key: bytes,
    nonce_prefix: bytes,
    chunk_size: int,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: Callable[[float], None] | None = None,
) -> tuple[bool, str, bytes]:
    """Open the chunk stream after `header`: write the file data to output_path, return (ok, error, metadata)."""
    try:
        ok, error, metadata = _module().open_file(algorithm, input_path, output_path, header, key, nonce_prefix,
                                                  chunk_size, block_size, cancel, callback)
        return bool(ok), str(error), bytes(metadata)
    except _NATIVE_ERRORS as error:
        return False, str(error) or repr(error), b""


def decrypt_file_v1(
    algorithm: str,
    input_path: str,
    output_path: str,
    password: str,
    block_size: int = 0,
    cancel: StopToken | None = None,
    callback: Callable[[float], None] | None = None,
) -> tuple[bool, str, bytes]:
    """Decrypt a v1 file into output_path. Returns (ok, error, stored_name_bytes); the name is untrusted."""
    try:
        ok, error, name = _module().decrypt_file_v1(algorithm, input_path, output_path, password,
                                                    block_size, cancel, callback)
        return bool(ok), str(error), bytes(name)
    except _NATIVE_ERRORS as error:
        return False, str(error) or repr(error), b""
