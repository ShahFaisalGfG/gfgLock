# paths.py - where gfgLock keeps its settings and logs (stdlib only, no gfglock imports)
#
# The installed app uses %APPDATA%\gfgLock. A portable build keeps them in a "gfgLock data" folder
# next to its exe, so it leaves nothing behind on the PC it runs on; when that folder can't be
# written (a read-only drive, say), it falls back to %APPDATA%\gfgLock. A build is portable when it
# is the one-file exe, or when the file gfgLock-portable.txt sits next to the exe (the portable .7z
# ships the one-folder build with that marker). Running from source has no data folder: the callers
# keep their files inside the project.

import os
import shutil
import sys

PORTABLE_FOLDER = "gfgLock data"
PORTABLE_MARKER = "gfgLock-portable.txt"
_UNSET = object()
_data_dir: object = _UNSET


def appdata_dir() -> str:
    """%APPDATA%\\gfgLock, the installed app's data folder."""
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "gfgLock")


def is_portable() -> bool:
    """True for a portable build: the one-file exe, or an exe with gfgLock-portable.txt next to it.

    The one-file exe unpacks itself into a temp folder at each start; the installed (one-folder)
    build keeps its files in _internal next to the exe instead.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or bundle is None:
        return False
    if os.path.isfile(os.path.join(_exe_dir(), PORTABLE_MARKER)):
        return True
    return _is_one_file(bundle)


def app_folder() -> str | None:
    """The folder holding the app's own files, None when running from source.

    That is the install folder of a one-folder build, and the temp folder the one-file exe unpacks
    into: the one-file exe's own folder is the user's (Downloads, say), not the app's.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or bundle is None:
        return None
    return os.path.abspath(bundle) if _is_one_file(bundle) else _exe_dir()


def _exe_dir() -> str:
    return os.path.dirname(os.path.abspath(sys.executable))


def _is_one_file(bundle: str) -> bool:
    """The one-file exe unpacks to a temp folder; a one-folder build keeps _internal beside the exe."""
    return os.path.normcase(os.path.dirname(os.path.abspath(bundle))) != os.path.normcase(_exe_dir())


def data_dir() -> str | None:
    """The folder for settings and logs, created if needed; None when running from source."""
    global _data_dir
    if _data_dir is _UNSET:
        _data_dir = _resolve()
    return _data_dir  # type: ignore[return-value]


def _resolve() -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    if is_portable():
        folder = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), PORTABLE_FOLDER)
        if _writable(folder):
            _adopt_installed_settings(folder)
            return folder
    folder = appdata_dir()
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        pass  # reported later by whoever fails to write there
    return folder


def _writable(folder: str) -> bool:
    """Create folder if needed and check a file can be written in it."""
    probe = os.path.join(folder, ".write-test")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def _adopt_installed_settings(folder: str) -> None:
    """On the portable exe's first start, begin with the settings of an earlier version, if any.

    Portable versions before 3.1.0 kept their settings in %APPDATA%\\gfgLock.
    """
    target = os.path.join(folder, "settings.json")
    source = os.path.join(appdata_dir(), "settings.json")
    if os.path.exists(target) or not os.path.isfile(source):
        return
    try:
        shutil.copyfile(source, target)
    except OSError:
        pass  # the defaults apply instead; nothing is lost
