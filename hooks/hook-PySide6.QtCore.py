"""Collect QtCore without Qt's translation catalogs, which the app never loads."""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, _translations = add_qt6_dependencies(__file__)
datas = []
