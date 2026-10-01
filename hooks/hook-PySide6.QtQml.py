"""Collect Qt QML plugins while omitting the unused Qt WebEngine module."""

from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()


def _is_webengine_entry(entry: tuple[str, str]) -> bool:
    """Return whether a QML plugin file belongs to Qt WebEngine."""
    return any(part.casefold() == "qtwebengine" for part in Path(entry[0]).parts)


binaries.extend(entry for entry in qml_binaries if not _is_webengine_entry(entry))
datas.extend(entry for entry in qml_datas if not _is_webengine_entry(entry))
