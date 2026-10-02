# chacha20_poly1305.py - ChaCha20-Poly1305 (.gfgcha) file encryption.
# The native C++ path is used when the .pyd is present, the Python fallback otherwise; both go
# through gfglock.core.file_ops, which owns output naming, validation, and source deletion.

from typing import Callable, Optional

from gfglock.core import file_ops


def encrypt_file(
    path: str,
    password: str,
    encrypt_name: bool = False,
    chunk_size=None,
    progress_callback: Optional[Callable] = None,
) -> tuple[bool, str]:
    """Encrypt a single file using ChaCha20-Poly1305."""
    return file_ops.encrypt_file(path, password, "chacha", encrypt_name, chunk_size, progress_callback)


def decrypt_file(
    path: str,
    password: str,
    chunk_size=None,
    progress_callback: Optional[Callable] = None,
) -> tuple[bool, str]:
    """Decrypt a single .gfgcha file.

    chunk_size is accepted for API compatibility; the layout is read from the file itself.
    """
    del chunk_size
    return file_ops.decrypt_file(path, password, progress_callback)
