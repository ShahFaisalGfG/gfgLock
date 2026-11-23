"""The command line and the engine it uses never import Qt, so the console exe runs without PySide6."""

import subprocess
import sys

MODULES = [
    "gfglock.cli",
    "gfglock.config.defaults",
    "gfglock.core.batch",
    "gfglock.core.file_ops",
    "gfglock.core.format_v2",
    "gfglock.core.locks",
    "gfglock.core.native_bridge",
    "gfglock.core.passwords",
    "gfglock.core.py_cipher",
    "gfglock.core.reasons",
    "gfglock.core.scan",
    "gfglock.utils.agent_skills",
    "gfglock.utils.console",
    "gfglock.utils.helpers",
    "gfglock.utils.logging",
    "gfglock.utils.paths",
    "gfglock.utils.settings",
]


def test_core_has_no_qt_imports() -> None:
    """Import each module in a fresh interpreter and check no PySide6 module was loaded."""
    code = (
        "import importlib, sys\n"
        f"for name in {MODULES!r}:\n"
        "    importlib.import_module(name)\n"
        "print(sorted(m for m in sys.modules if m.startswith(('PySide6', 'shiboken6'))))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"
