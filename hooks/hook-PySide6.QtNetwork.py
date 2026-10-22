"""Collect QtNetwork without its plugins or an OpenSSL build.

gfgLock uses QtNetwork only for QLocalServer and QLocalSocket (the single-instance pipe), so the
TLS, network-information and network-access plugins are left out. PyInstaller's own hook also
bundles whichever libssl/libcrypto Qt finds on PATH, which can replace the pinned OpenSSL that
gfglock_native loads (both are named libcrypto-3-x64.dll); this hook never collects it.
"""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, _plugins, datas = add_qt6_dependencies(__file__)
binaries = []
