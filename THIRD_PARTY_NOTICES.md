# Third-Party Notices

gfgLock is free and open-source software, released under the [MIT License](LICENSE). The
installers and the portable app bundle the open-source components below. Each keeps its own
licence, and the complete source for every one is available from the project linked.

The full licence texts are in the [`licenses`](licenses) folder. The installers put it in the
`docs\licenses` folder of the install folder, the portable `.7z` next to `gfgLock.exe`, and the
portable exe carries it inside itself.

| Component | Licence | Licence text | Used for |
|---|---|---|---|
| [OpenSSL](https://www.openssl.org/) 3.6, built by [vcpkg](https://vcpkg.io/) | Apache-2.0 | `licenses/OpenSSL/LICENSE.txt` | AES-256-GCM, ChaCha20-Poly1305, AES-256-CFB (decryption only), and PBKDF2 in the native engine |
| [pybind11](https://github.com/pybind/pybind11) (compiled into `gfglock_native`) | BSD-3-Clause | `licenses/pybind11/LICENSE.txt` | Connecting the native engine to Python |
| [Qt 6](https://www.qt.io/) and [Qt for Python (PySide6, shiboken6)](https://wiki.qt.io/Qt_for_Python) | LGPL-3.0-only | `licenses/Qt/LGPL-3.0.txt`, and `licenses/Qt/GPL-3.0.txt`, whose terms the LGPL builds on | The user interface |
| [Python](https://www.python.org/) 3.12 | PSF License 2.0 | `licenses/Python/LICENSE.txt`, which also covers the libraries in Python's Windows build: bzip2, libffi, OpenSSL 3.0, xz, zlib, expat, and mpdecimal | The app runtime |
| [libffi](https://github.com/libffi/libffi) (used by Python's `ctypes`) | MIT | `licenses/libffi/LICENSE.txt` | Calling Windows functions from Python |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause | `licenses/cryptography/` | Argon2id key derivation and the Python fallback ciphers |
| [cffi](https://github.com/python-cffi/cffi) (used by cryptography) | MIT-0 | `licenses/cffi/LICENSE.txt` | Python fallback ciphers |
| [pycparser](https://github.com/eliben/pycparser) (used by cffi) | BSD-3-Clause | `licenses/pycparser/LICENSE.txt` | Python fallback ciphers |
| [PyCryptodome](https://github.com/Legrandin/pycryptodome) | BSD-2-Clause, parts public domain | `licenses/pycryptodome/LICENSE.txt` | Python fallback ChaCha20-Poly1305 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) bootloader | GPL-2.0-or-later with the bootloader exception, which allows distributing it with any program | `licenses/PyInstaller/COPYING.txt` | Starting the bundled app |
| Microsoft Visual C++ runtime and Universal C Runtime | Microsoft's redistribution terms | See below | Running the compiled parts |

## Qt and PySide6 (LGPL-3.0)

Qt and PySide6 are used as separate, replaceable libraries: the installed app keeps them as
individual DLL and `.pyd` files in its `_internal` folder, so they can be swapped for other builds
of the same version. Their source is available from <https://download.qt.io/> and
<https://code.qt.io/>.

The Qt DLLs include third-party code under its own permissive licences, for example PCRE2 and
zlib in `Qt6Core.dll`, HarfBuzz and libpng in `Qt6Gui.dll`, PDFium in `Qt6Pdf.dll`, and
libjpeg-turbo, libtiff, and libwebp in the image format plugins. Qt lists every one with its
licence at <https://doc.qt.io/qt-6/licenses-used-in-qt.html>.

## cryptography

The `_rust.pyd` module of cryptography is statically linked with OpenSSL 3 (Apache-2.0, the
text in `licenses/OpenSSL/LICENSE.txt`) and with Rust crates under the MIT or Apache-2.0
licences, which cryptography lists in its software bill of materials at
<https://github.com/pyca/cryptography>.

## Microsoft runtime libraries

`VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `MSVCP140.dll`, `MSVCP140_1.dll`, and `MSVCP140_2.dll`
(the Visual C++ runtime, shipped by Python and PySide6), and `ucrtbase.dll` with the
`api-ms-win-*.dll` files (the Universal C Runtime), are Microsoft's redistributable files. They
are distributed under the Visual Studio redistribution terms, which allow shipping them with an
application; Windows 10 and later include the Universal C Runtime. Python's licence text above
describes the conditions for the copies that come with Python. The Explorer shell extension
`gfglock_shell.dll` links the C runtime statically and needs none of these files.

## Bundled DLLs

Every DLL and Python extension module the app bundle ships, by component.

- **gfgLock** (MIT, this project): `gfglock_native.cp312-win_amd64.pyd`; in the installers also
  `gfglock_shell.dll`.
- **OpenSSL 3.6** (vcpkg): `libcrypto-3-x64.dll`.
- **Python 3.12**: `python312.dll`, `python3.dll`, `libffi-8.dll`, `libcrypto-3.dll` and
  `libssl-3.dll` (OpenSSL 3.0, used by Python's `_hashlib` and `_ssl`), and the extension modules
  `_bz2.pyd`, `_ctypes.pyd`, `_decimal.pyd`, `_hashlib.pyd`, `_lzma.pyd`, `_multiprocessing.pyd`,
  `_queue.pyd`, `_socket.pyd`, `_ssl.pyd`, `_wmi.pyd`, `pyexpat.pyd`, `select.pyd`, and
  `unicodedata.pyd`.
- **Qt 6.11**: `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, `Qt6Network.dll`, `Qt6OpenGL.dll`,
  `Qt6Svg.dll`, `Qt6Pdf.dll`, `Qt6VirtualKeyboard.dll`, `Qt6Qml.dll`, `Qt6QmlMeta.dll`,
  `Qt6QmlModels.dll`, `Qt6QmlWorkerScript.dll`, `Qt6Quick.dll`, `Qt6QuickControls2.dll`,
  `Qt6QuickControls2Basic.dll`, `Qt6QuickControls2BasicStyleImpl.dll`,
  `Qt6QuickControls2Impl.dll`, `Qt6QuickControls2Material.dll`,
  `Qt6QuickControls2MaterialStyleImpl.dll`, `Qt6QuickDialogs2.dll`,
  `Qt6QuickDialogs2QuickImpl.dll`, `Qt6QuickDialogs2Utils.dll`, `Qt6QuickLayouts.dll`,
  `Qt6QuickShapes.dll`, `Qt6QuickTemplates2.dll`, and `Qt6LabsFolderListModel.dll`.
- **Qt plugins** (`PySide6\plugins`): `platforms\qwindows.dll`, `platforms\qdirect2d.dll`,
  `platforms\qminimal.dll`, `platforms\qoffscreen.dll`, `styles\qmodernwindowsstyle.dll`,
  `iconengines\qsvgicon.dll`, `generic\qtuiotouchplugin.dll`,
  `platforminputcontexts\qtvirtualkeyboardplugin.dll`, and the image formats `qgif.dll`,
  `qicns.dll`, `qico.dll`, `qjpeg.dll`, `qpdf.dll`, `qsvg.dll`, `qtga.dll`, `qtiff.dll`,
  `qwbmp.dll`, and `qwebp.dll`.
- **Qt Quick modules** (`PySide6\qml`): the plugins of QtQml, QtQml.Models, QtQml.WorkerScript,
  QtQuick, QtQuick.Window, QtQuick.Layouts, QtQuick.Shapes, QtQuick.Templates, QtQuick.Controls,
  QtQuick.Controls.impl, QtQuick.Controls.Basic, QtQuick.Controls.Basic.impl,
  QtQuick.Controls.Material, QtQuick.Controls.Material.impl, QtQuick.Dialogs,
  QtQuick.Dialogs.quickimpl, and Qt.labs.folderlistmodel.
- **PySide6 and shiboken6**: `pyside6.abi3.dll`, `pyside6qml.abi3.dll`, `shiboken6.abi3.dll`,
  `Shiboken.pyd`, and the modules `QtCore.pyd`, `QtGui.pyd`, `QtWidgets.pyd`, `QtNetwork.pyd`,
  `QtOpenGL.pyd`, `QtQml.pyd`, `QtQuick.pyd`, and `QtQuickControls2.pyd`.
- **cryptography**: `cryptography\hazmat\bindings\_rust.pyd`; **cffi**:
  `_cffi_backend.cp312-win_amd64.pyd`.
- **PyCryptodome**: the `.pyd` modules in `Crypto\Cipher`, `Crypto\Hash`, `Crypto\Math`,
  `Crypto\Protocol`, `Crypto\PublicKey`, and `Crypto\Util`.
- **Microsoft runtime**: `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `MSVCP140.dll`,
  `MSVCP140_1.dll`, `MSVCP140_2.dll`, `ucrtbase.dll`, and the `api-ms-win-*.dll` files.
