# Third-Party Notices

gfgLock is free and open-source software, released under the [MIT License](LICENSE). The
installers and the portable app bundle the open-source components below. Each keeps its own
licence; the complete source for every one is available from the project linked.

| Component | Licence | Used for |
|---|---|---|
| [OpenSSL](https://www.openssl.org/) 3 (`libcrypto-3-x64.dll`) | Apache-2.0 | AES-256 GCM/CFB, ChaCha20-Poly1305, and PBKDF2 in the native engine |
| [pybind11](https://github.com/pybind/pybind11) (compiled into `gfglock_native`) | BSD-3-Clause | Connecting the native engine to Python |
| [Qt 6](https://www.qt.io/) and [Qt for Python (PySide6, shiboken6)](https://wiki.qt.io/Qt_for_Python) | LGPL-3.0-only | The user interface |
| [Python](https://www.python.org/) | PSF License 2.0 | The app runtime |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause | Python fallback ciphers |
| [cffi](https://github.com/python-cffi/cffi) and [pycparser](https://github.com/eliben/pycparser) (used by cryptography) | MIT-0; BSD-3-Clause | Python fallback ciphers |
| [PyCryptodome](https://github.com/Legrandin/pycryptodome) | BSD-2-Clause, parts public domain | Python fallback ChaCha20-Poly1305 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) bootloader | GPL-2.0-or-later with the bootloader exception, which allows distributing it with any program | Starting the bundled app |

## Qt and PySide6 (LGPL-3.0)

Qt and PySide6 are used as separate, replaceable libraries: the installed app keeps them as
individual DLL and `.pyd` files in its `_internal` folder, so they can be swapped for other builds
of the same version. Their source is available from <https://download.qt.io/> and
<https://code.qt.io/>. The full LGPL-3.0 text is at <https://www.gnu.org/licenses/lgpl-3.0.html>.
