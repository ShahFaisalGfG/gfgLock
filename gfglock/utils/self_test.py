# self_test.py - checks that a build can encrypt, decrypt, and load every QML module it ships
#
# PyInstaller only follows static imports, and the bundle's custom QtQml hook trims Qt modules, so
# a build can succeed and still fail on a user's machine (missing OpenSSL DLL, trimmed QML plugin,
# missing crypto backend). The release workflow runs the frozen exe with --self-test so a missing
# piece fails the build instead. Everything runs in a temporary folder; no user file or setting
# is touched. Each check imports what it tests inside its own body so one missing library is
# reported as one failed check, not as a crash that hides every other result.

import os
import sys
import tempfile
import traceback
from typing import Callable, Optional

from gfglock.utils.console import safe_print
from gfglock.utils.helpers import resource_path
Check = tuple[str, Callable[[], None]]

_QML_DIR = "gfglock/qml"
_PASSWORD = "self-test password"
_SAMPLE = os.urandom(300_000) + "é ü 日本".encode("utf-8")

# The QApplication must outlive every QML engine, so it is kept for the rest of the process.
_qt_app: Optional[object] = None


def _check_native_extension() -> None:
    """Load gfglock_native (and its OpenSSL DLLs) at the required API version."""
    from gfglock.core import native_bridge

    if not native_bridge.NATIVE_AVAILABLE:
        raise RuntimeError(
            f"gfglock_native is missing or older than API version {native_bridge.REQUIRED_API_VERSION}"
        )


def _check_file_round_trip() -> None:
    """Encrypt and decrypt a file with every algorithm through the same path the app uses."""
    from gfglock.core.file_ops import EXTENSIONS, decrypt_file, encrypt_file

    for algorithm in EXTENSIONS:
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "sample.txt")
            with open(source, "wb") as fh:
                fh.write(_SAMPLE)
            ok, message = encrypt_file(source, _PASSWORD, algorithm, encrypt_name=True)
            if not ok:
                raise RuntimeError(f"{algorithm} encrypt: {message}")
            (encrypted,) = os.listdir(tmp)
            ok, message = decrypt_file(os.path.join(tmp, encrypted), _PASSWORD)
            if not ok:
                raise RuntimeError(f"{algorithm} decrypt: {message}")
            with open(source, "rb") as fh:
                if fh.read() != _SAMPLE:
                    raise RuntimeError(f"{algorithm} round trip changed the file contents")


def _check_python_fallback() -> None:
    """Decrypt native output with the Python ciphers and the reverse, for every algorithm."""
    from gfglock.core import native_bridge, py_cipher
    from gfglock.core.file_ops import EXTENSIONS

    for algorithm in EXTENSIONS:
        with tempfile.TemporaryDirectory() as tmp:
            source, encrypted, restored = (os.path.join(tmp, name) for name in ("in", "enc", "out"))
            with open(source, "wb") as fh:
                fh.write(_SAMPLE)
            pairs = (
                (native_bridge.encrypt_file, py_cipher.decrypt_stream, "native -> Python"),
                (py_cipher.encrypt_stream, native_bridge.decrypt_file, "Python -> native"),
            )
            for encrypt, decrypt, direction in pairs:
                ok, error = encrypt(algorithm, source, encrypted, "sample.txt", _PASSWORD)
                if not ok:
                    raise RuntimeError(f"{algorithm} {direction} encrypt: {error}")
                ok, error, name = decrypt(algorithm, encrypted, restored, _PASSWORD)
                if not ok:
                    raise RuntimeError(f"{algorithm} {direction} decrypt: {error}")
                with open(restored, "rb") as fh:
                    if fh.read() != _SAMPLE or name != b"sample.txt":
                        raise RuntimeError(f"{algorithm} {direction} produced different output")


def _qml_files() -> list[str]:
    """Return every bundled .qml file."""
    root = resource_path(_QML_DIR)
    files = [
        os.path.join(folder, name)
        for folder, _dirs, names in os.walk(root)
        for name in names
        if name.endswith(".qml")
    ]
    if not files:
        raise RuntimeError(f"no QML files found in {root}")
    return sorted(files)


def _check_qml() -> None:
    """Compile every bundled QML file, which resolves each Qt module and component it imports."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtWidgets import QApplication

    global _qt_app
    _qt_app = QApplication.instance() or QApplication([sys.argv[0]])
    engine = QQmlEngine()
    errors: list[str] = []
    for path in _qml_files():
        component = QQmlComponent(engine, QUrl.fromLocalFile(path))
        if component.isError():
            errors.extend(error.toString() for error in component.errors())
    if errors:
        raise RuntimeError("; ".join(errors))


CHECKS: list[Check] = [
    ("Native extension", _check_native_extension),
    ("Encrypt and decrypt files", _check_file_round_trip),
    ("Python fallback matches native", _check_python_fallback),
    ("QML", _check_qml),
]


def run_self_test(report_path: Optional[str] = None, checks: Optional[list[Check]] = None) -> int:
    """Run every check, write a PASS/FAIL report, and return 0 when all checks pass, else 1.

    The report goes to report_path when given and to stdout when one exists; a --windowed
    build has no console, so the release workflow reads the report file.
    """
    selected = CHECKS if checks is None else checks
    lines: list[str] = []
    failed = 0
    for name, check in selected:
        try:
            check()
            lines.append(f"PASS  {name}")
        except Exception as e:
            failed += 1
            lines.append(f"FAIL  {name}: {e!r}")
            lines.extend("      " + line for line in traceback.format_exc().rstrip().splitlines())
    lines.append(f"{failed} of {len(selected)} checks failed" if failed else f"All {len(selected)} checks passed")
    report = "\n".join(lines) + "\n"
    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report)
    if sys.stdout is not None:
        safe_print(report.rstrip("\n"))
    return 1 if failed else 0
