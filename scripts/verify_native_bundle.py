"""Verify the native extension can load from a PyInstaller onedir bundle."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


def verify_bundle(bundle_dir: Path) -> None:
    """Import the bundled extension with its adjacent runtime DLLs available."""
    extensions = list(bundle_dir.rglob("gfglock_native*.pyd"))
    if not extensions:
        raise FileNotFoundError(f"No gfglock_native .pyd found under {bundle_dir}")

    dll_handles = []
    for directory in {extension.parent for extension in extensions}:
        sys.path.insert(0, str(directory))
        if hasattr(os, "add_dll_directory"):
            dll_handles.append(os.add_dll_directory(str(directory)))

    module = importlib.import_module("gfglock_native")
    required_functions = (
        "pbkdf2_sha256",
        "encrypt_gcm",
        "decrypt_gcm",
        "encrypt_cfb",
        "decrypt_cfb",
        "encrypt_chacha",
        "decrypt_chacha",
    )
    missing = [name for name in required_functions if not callable(getattr(module, name, None))]
    if missing:
        raise ImportError(f"Bundled gfglock_native is missing functions: {', '.join(missing)}")

    print(f"Native extension loaded from: {module.__file__}")
    # Keep the DLL search handles alive until after import completes.
    del dll_handles


def main() -> int:
    """Verify the bundle path passed on the command line."""
    if len(sys.argv) != 2:
        print("Usage: verify_native_bundle.py <onedir-bundle>", file=sys.stderr)
        return 2

    try:
        verify_bundle(Path(sys.argv[1]).resolve())
    except Exception as error:
        print(f"Native bundle verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
