# console.py - safe stdout writer (stdlib only, no gfglock imports)
#
# The engine echoes what it does through safe_print. The window has no console, so it goes to
# stdout unread; the command line, whose stdout carries its own output (JSON with --json), sends
# it elsewhere with set_sink().

import sys
from collections.abc import Callable

_sink: Callable[[str], None] | None = None


def set_sink(sink: Callable[[str], None] | None) -> None:
    """Send safe_print's messages to `sink` instead of stdout; None goes back to stdout."""
    global _sink
    _sink = sink


def safe_print(msg: str) -> None:
    """Write a UTF-8 message to stdout (or the sink set with set_sink), safe for Windows consoles."""
    if _sink is not None:
        _sink(str(msg))
        return
    try:
        sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write(str(msg) + "\n")
            sys.stdout.flush()
        except Exception:
            pass
