# console.py - safe stdout writer (stdlib only, no gfglock imports)

import sys


def safe_print(msg: str) -> None:
    """Write a UTF-8 message to stdout, safe for Windows console environments."""
    try:
        sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
        except Exception:
            pass
