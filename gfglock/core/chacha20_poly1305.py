# chacha20_poly1305.py - ChaCha20-Poly1305 (.gfgcha) file encryption.
# The native C++ path is used when the .pyd is present, the Python fallback otherwise; both go
# through gfglock.core.file_ops, which owns output naming, validation, and source deletion.

from typing import Callable, Optional

from gfglock.core import file_ops


def encrypt_file(
    path: str,
    password: str,
    encrypt_name: bool = False,
    read_size: int = 0,
    progress_callback: Optional[Callable] = None,
) -> file_ops.FileResult:
    """Encrypt a single file using ChaCha20-Poly1305."""
    return file_ops.encrypt_file(path, password, "chacha", encrypt_name, read_size, progress_callback)


def decrypt_file(
    path: str,
    password: str,
    read_size: int = 0,
    progress_callback: Optional[Callable] = None,
) -> file_ops.FileResult:
    """Decrypt a single .gfgcha file."""
    return file_ops.decrypt_file(path, password, read_size, progress_callback)
