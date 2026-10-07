# aes256_gcm_cfb.py - AES-256 GCM (.gfglock) and CFB (.gfglck) file encryption.
# The native C++ path is used when the .pyd is present, the Python fallback otherwise; both go
# through gfglock.core.file_ops, which owns output naming, validation, and source deletion.

from typing import Callable, Optional

from gfglock.core import file_ops


def encrypt_file(
    path: str,
    password: str,
    encrypt_name: bool = False,
    read_size: int = 0,
    AEAD: bool = True,
    progress_callback: Optional[Callable] = None,
) -> file_ops.FileResult:
    """Encrypt a single file using AES-256 GCM (AEAD, default) or CFB."""
    algorithm = "gcm" if AEAD else "cfb"
    return file_ops.encrypt_file(path, password, algorithm, encrypt_name, read_size, progress_callback)


def decrypt_file(
    path: str,
    password: str,
    read_size: int = 0,
    progress_callback: Optional[Callable] = None,
) -> file_ops.FileResult:
    """Decrypt a single .gfglock (GCM) or .gfglck (CFB) file."""
    return file_ops.decrypt_file(path, password, read_size, progress_callback)
