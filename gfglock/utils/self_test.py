# self_test.py - checks that a build can encrypt, decrypt, and load every QML module it ships
#
# PyInstaller only follows static imports, and the bundle's custom QtQml hook trims Qt modules, so
# a build can succeed and still fail on a user's machine (missing OpenSSL DLL, trimmed QML plugin,
# missing crypto backend). The release workflow runs the frozen exe with --self-test so a missing
# piece fails the build instead. Everything runs in a temporary folder; no user file or setting
# is touched. Each check imports what it tests inside its own body so one missing library is
# reported as one failed check, not as a crash that hides every other result.

import os
import re
import sys
import tempfile
import traceback
from typing import Callable, Optional

from gfglock.utils.console import safe_print
from gfglock.utils.helpers import resource_path
Check = tuple[str, Callable[[], None]]

_QML_DIR = "gfglock/qml"
_PASSWORD = "self-test password"
_SAMPLE = os.urandom(5 << 19) + "é ü 日本".encode("utf-8")  # 2.5 MiB: three v2 chunks

# The QApplication must outlive every QML engine, so it is kept for the rest of the process.
_qt_app: Optional[object] = None


def _check_native_extension() -> None:
    """Load gfglock_native (and its OpenSSL DLLs) at the required API version."""
    from gfglock.core import native_bridge

    if not native_bridge.NATIVE_AVAILABLE:
        raise RuntimeError(
            f"gfglock_native is missing or older than API version {native_bridge.REQUIRED_API_VERSION}"
        )


def _check_openssl() -> None:
    """The native module runs on the OpenSSL it was built with, not another libcrypto found on PATH."""
    from gfglock.core import native_bridge

    if not native_bridge.NATIVE_AVAILABLE:
        raise RuntimeError("needs the native extension")
    runtime, built = native_bridge.openssl_version(), native_bridge.openssl_build_version()
    if runtime != built:
        raise RuntimeError(f"OpenSSL {runtime} is loaded, but gfglock_native was built with OpenSSL {built}")


def _check_file_round_trip() -> None:
    """Encrypt and decrypt a file with every algorithm through the same path the app uses."""
    from gfglock.core.file_ops import ENCRYPT_ALGORITHMS, decrypt_file, encrypt_file
    from gfglock.core.format_v2 import KeyRing

    keys = KeyRing(_PASSWORD)  # the default Argon2id cost, as in a run
    for algorithm in ENCRYPT_ALGORITHMS:
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "sample.txt")
            with open(source, "wb") as fh:
                fh.write(_SAMPLE)
            ok, message = encrypt_file(source, keys, algorithm, encrypt_name=True)
            if not ok:
                raise RuntimeError(f"{algorithm} encrypt: {message}")
            (encrypted,) = os.listdir(tmp)
            ok, message = decrypt_file(os.path.join(tmp, encrypted), keys)
            if not ok:
                raise RuntimeError(f"{algorithm} decrypt: {message}")
            with open(source, "rb") as fh:
                if fh.read() != _SAMPLE:
                    raise RuntimeError(f"{algorithm} round trip changed the file contents")


def _check_engines() -> None:
    """Every available engine opens every engine's v2 output, and all engines write the same bytes."""
    from gfglock.core import format_v2, native_bridge, py_cipher
    from gfglock.core.file_ops import ENCRYPT_ALGORITHMS

    engines = {"Python": (py_cipher.seal_stream, py_cipher.open_stream)}
    if native_bridge.NATIVE_AVAILABLE:
        engines["native"] = (native_bridge.seal_file, native_bridge.open_file)
    # The engines take the key as given, so the cheapest Argon2id cost is enough here.
    keys = format_v2.KeyRing(_PASSWORD, format_v2.KdfParams(memory_kib=64, iterations=1, lanes=1))
    metadata = format_v2.pack_metadata("sample.txt", 0)
    for algorithm in ENCRYPT_ALGORITHMS:
        header, key = keys.new_header(algorithm)
        written: dict[bytes, str] = {}
        with tempfile.TemporaryDirectory() as tmp:
            source, encrypted, restored = (os.path.join(tmp, name) for name in ("in", "enc", "out"))
            with open(source, "wb") as fh:
                fh.write(_SAMPLE)
            for writer, (seal, _) in engines.items():
                ok, error = seal(algorithm, source, encrypted, header.pack(), key, header.nonce_prefix,
                                 header.chunk_size, metadata)
                if not ok:
                    raise RuntimeError(f"{algorithm} {writer} seal: {error}")
                with open(encrypted, "rb") as fh:
                    written[fh.read()] = writer
                for reader, (_, open_stream) in engines.items():
                    ok, error, stored = open_stream(algorithm, encrypted, restored, header.pack(), key,
                                                    header.nonce_prefix, header.chunk_size)
                    if not ok:
                        raise RuntimeError(f"{algorithm} {writer} -> {reader} open: {error}")
                    with open(restored, "rb") as fh:
                        if fh.read() != _SAMPLE or stored != metadata:
                            raise RuntimeError(f"{algorithm} {writer} -> {reader} changed the file contents")
        if len(written) > 1:
            raise RuntimeError(f"{algorithm}: the engines wrote different files")


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


def _check_images() -> None:
    """Every image the app shows is bundled; QML shows a missing image as a blank, not an error."""
    from gfglock.app import SPLASH_LOGO, WINDOW_ICONS

    missing = [path for path in (SPLASH_LOGO, *WINDOW_ICONS.values()) if not os.path.isfile(resource_path(path))]
    for qml in _qml_files():
        with open(qml, encoding="utf-8") as fh:
            for source in re.findall(r'source:\s*"([^"]+\.(?:png|ico|svg))"', fh.read()):
                if not os.path.isfile(os.path.join(os.path.dirname(qml), source)):
                    missing.append(f"{source} (from {os.path.basename(qml)})")
    if missing:
        raise RuntimeError("missing images: " + ", ".join(missing))


CHECKS: list[Check] = [
    ("Native extension", _check_native_extension),
    ("OpenSSL version", _check_openssl),
    ("Encrypt and decrypt files", _check_file_round_trip),
    ("Encryption engines agree", _check_engines),
    ("QML", _check_qml),
    ("Images", _check_images),
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
