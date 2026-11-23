"""Render gfgLock's window offscreen in each of its main states, as PNG files.

Used to check the layout at small and large sizes in both themes, and to refresh the README's
screenshots. Nothing touches your settings or files: the app runs on a temporary data folder and
sample files in a temporary folder, with a fast key derivation so the runs finish at once.

    python scripts/render_screenshots.py --out screenshots
    python scripts/render_screenshots.py --out build/renders --size 820x560 --size 1920x1040 --theme light --theme dark
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# The offscreen platform finds no fonts unless it is told where Windows keeps them.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QObject, QThreadPool  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gfglock.utils import paths  # noqa: E402

# Sample files, as a user might have them: (path inside the Documents folder, size in bytes).
SAMPLES = [("Budget 2026.xlsx", 40_960), ("Client contract.docx", 96_051), ("Passport scan.jpg", 2_306_867),
           ("Tax return 2025.pdf", 1_887_437), ("Family photos/Beach day.jpg", 4_194_304),
           ("Family photos/Birthday.jpg", 3_670_016)]
PASSWORD = "correct horse battery staple"
SETTLE_S = 0.4


def _settle(seconds: float = SETTLE_S) -> None:
    """Let Qt deliver queued signals, run timers, and lay out for a moment."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def _wait_idle(controller: QObject, timeout: float = 60.0) -> None:
    """Wait for a tab's scan and run to end."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if not controller.property("busy") and not controller.property("scanning"):
            QThreadPool.globalInstance().waitForDone(500)
            _settle()
            return
        time.sleep(0.02)
    raise TimeoutError("the run did not finish in time")


class Renderer:
    """Builds the app's controllers and window the way app.py does, on a temporary data folder."""

    def __init__(self, data_dir: Path, theme: str) -> None:
        paths._data_dir = str(data_dir)  # settings and logs go to the temporary folder
        data_dir.mkdir(parents=True, exist_ok=True)
        from gfglock.utils.settings import get_default_settings, save_settings

        settings = get_default_settings()
        settings["theme"] = theme
        save_settings(settings)
        from gfglock import app as app_module
        from gfglock.controllers import encrypt_ctrl
        from gfglock.controllers.app_ctrl import AppController
        from gfglock.controllers.prefs_ctrl import PrefsController
        from gfglock.controllers.update_ctrl import UpdateController
        from gfglock.core.format_v2 import KdfParams, KeyRing

        cheap = KdfParams(memory_kib=64, iterations=1, lanes=1)
        encrypt_ctrl.KeyRing = lambda password: KeyRing(password, cheap)  # type: ignore[assignment]
        self.app_ctrl = AppController()
        self.encrypt = encrypt_ctrl.EncryptController("encrypt")
        self.decrypt = encrypt_ctrl.EncryptController("decrypt")
        self.prefs = PrefsController()
        self.prefs.set_run_controllers([self.encrypt, self.decrypt])
        self.updates = UpdateController(app_module._update_config())
        self.engine = QQmlApplicationEngine()
        context = self.engine.rootContext()
        for name, controller in (("appController", self.app_ctrl), ("encryptController", self.encrypt),
                                 ("decryptController", self.decrypt), ("prefsController", self.prefs),
                                 ("updateController", self.updates)):
            context.setContextProperty(name, controller)
        qml = ROOT / "gfglock" / "qml"
        self.engine.addImportPath(str(qml))
        self.engine.load(str(qml / "main.qml"))
        if not self.engine.rootObjects():
            raise RuntimeError("main.qml failed to load")
        self.window: QQuickWindow = self.engine.rootObjects()[0]  # type: ignore[assignment]
        _settle()

    def find(self, class_name: str = "", **properties: object) -> list[QObject]:
        """Objects in the window whose class name contains class_name and whose properties match."""
        found = []
        for obj in self.window.findChildren(QObject):
            if class_name and class_name not in obj.metaObject().className():
                continue
            if all(obj.property(key) == value for key, value in properties.items()):
                found.append(obj)
        return found

    def show_tab(self, index: int) -> None:
        """Switch to the Encrypt (0) or Decrypt (1) tab."""
        self.find("TabBar")[0].setProperty("currentIndex", index)
        _settle()

    def type_password(self, encrypting: bool, password: str) -> None:
        """Type the password (twice when encrypting) into the tab's boxes."""
        for field in self.find(label="Password", showStrength=encrypting):
            field.setProperty("text", password)
        if encrypting:
            for field in self.find(label="Confirm password"):
                field.setProperty("text", password)
        _settle()

    def resize(self, width: int, height: int) -> None:
        """Give the window a size; a large one stands in for maximized."""
        self.window.setWidth(width)
        self.window.setHeight(height)
        _settle()

    def save(self, path: Path) -> None:
        """Render the window and save it."""
        _settle()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.window.grabWindow().save(str(path)):
            raise OSError(f"couldn't save {path}")
        print(path)

    def save_preferences(self, path: Path, width: int, height: int) -> None:
        """Open Preferences, render it, and close it again."""
        self.window.metaObject().invokeMethod(self.window, "openPreferences")
        _settle()
        prefs = [window for window in QGuiApplication.topLevelWindows()
                 if isinstance(window, QQuickWindow) and window.title() == "Preferences"]
        if not prefs:
            raise RuntimeError("Preferences didn't open")
        window = prefs[0]
        window.setWidth(min(width, 820))
        window.setHeight(min(height, 600))
        _settle()
        path.parent.mkdir(parents=True, exist_ok=True)
        window.grabWindow().save(str(path))
        print(path)
        window.close()
        _settle()


def render(out: Path, sizes: list[tuple[int, int]], themes: list[str], samples: Path | None, plain: bool) -> None:
    """Render every state at every size and theme into out.

    The sample files go in samples (removed afterwards when the script made it), or in a temporary
    folder under build: the system temp folder is inside AppData, which encrypting leaves alone.
    """
    (ROOT / "build").mkdir(exist_ok=True)
    made = samples is not None and not samples.exists()
    try:
        for theme in themes:
            for width, height in sizes:
                suffix = "" if plain else f"_{theme}_{width}x{height}"
                with tempfile.TemporaryDirectory(prefix="render-", dir=ROOT / "build") as temp:
                    folder = (samples or Path(temp)) / "Documents"
                    for name, size in SAMPLES:
                        (folder / name).parent.mkdir(parents=True, exist_ok=True)
                        (folder / name).write_bytes(os.urandom(size))
                    try:
                        _render_states(out, suffix, folder, Path(temp) / "data", theme, width, height)
                    finally:
                        shutil.rmtree(folder, ignore_errors=True)
    finally:
        if made and samples is not None:
            shutil.rmtree(samples, ignore_errors=True)


def _render_states(out: Path, suffix: str, folder: Path, data: Path, theme: str, width: int, height: int) -> None:
    """Render each state of one window size and theme."""
    renderer = Renderer(data, theme)
    renderer.resize(width, height)
    renderer.save(out / f"encrypt_empty{suffix}.png")

    renderer.encrypt.addFiles([str(folder)])
    _wait_idle(renderer.encrypt)
    renderer.type_password(True, PASSWORD)
    renderer.save(out / f"encrypt_ready{suffix}.png")
    pages = renderer.find(_optionsOpen=False)
    for page in pages:
        page.setProperty("_optionsOpen", True)
    renderer.save(out / f"encrypt_options{suffix}.png")
    for page in pages:
        page.setProperty("_optionsOpen", False)

    renderer.encrypt.start(PASSWORD, False, "")
    _wait_idle(renderer.encrypt)
    renderer.save(out / f"encrypt_done{suffix}.png")

    renderer.show_tab(1)
    renderer.decrypt.addFiles([str(folder)])
    _wait_idle(renderer.decrypt)
    renderer.type_password(False, "wrong password")
    renderer.decrypt.start("wrong password", False, "")
    _wait_idle(renderer.decrypt)
    renderer.save(out / f"decrypt_wrong_password{suffix}.png")

    renderer.type_password(False, PASSWORD)
    renderer.decrypt.start(PASSWORD, False, "")
    _wait_idle(renderer.decrypt)
    renderer.save(out / f"decrypt_done{suffix}.png")

    about = renderer.find("Dialog", title="About gfgLock")[0]
    about.metaObject().invokeMethod(about, "open")
    renderer.save(out / f"about{suffix}.png")
    about.metaObject().invokeMethod(about, "close")
    renderer.save_preferences(out / f"preferences{suffix}.png", width, height)
    renderer.engine.deleteLater()
    _settle()


def _size(text: str) -> tuple[int, int]:
    width, _, height = text.lower().partition("x")
    return int(width), int(height)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "renders", help="folder for the PNG files")
    parser.add_argument("--size", type=_size, action="append", help="window size, such as 820x560 (repeatable)")
    parser.add_argument("--theme", choices=("light", "dark"), action="append", help="theme (repeatable)")
    parser.add_argument("--samples", type=Path,
                        help="make the sample files in DIR/Documents, so the rows show a tidy path (removed after)")
    parser.add_argument("--plain-names", action="store_true",
                        help="name the files encrypt_ready.png and so on, as the README uses them (one size and theme)")
    args = parser.parse_args()
    QQuickStyle.setStyle("Material")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # The offscreen platform's font list names Windows' variable Segoe UI differently; its static
    # sibling looks the same at these sizes.
    QFont.insertSubstitution("Segoe UI Variable Text", "Segoe UI")
    render(args.out, args.size or [(820, 560)], args.theme or ["light"], args.samples, args.plain_names)


if __name__ == "__main__":
    main()
