# Developer Setup Guide

## Requirements

- Python 3.11+
- PowerShell 7 (`pwsh`) for the build scripts
- Visual Studio 2022+ Build Tools with the C++ workload and the "C++ CMake tools for Windows" component (for the native extension; the build script uses the CMake and Ninja that come with it)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the installers)

---

## 1. Virtual Environment

```powershell
# Create
python -m venv .venv

# Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (CMD)
.venv\Scripts\activate.bat
```

---

## 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs the exact versions every build uses: `PySide6`, `cryptography`, `pycryptodome`, `pyinstaller`, `pybind11`, and `pytest`. `pyproject.toml` lists the looser version ranges the code supports.

---

## 3. Run in Development Mode

```powershell
python -m gfglock
```

Open files on a tab the way the Explorer context menu does:

```powershell
python -m gfglock encrypt "C:\path\to\file.txt"
python -m gfglock decrypt "C:\path\to\file.txt.gfglock"
```

In development mode, settings are kept in `gfglock\utils\settings.json` and logs in `logs\`. The installed app keeps them in `%APPDATA%\gfgLock`, and the portable exe in a `gfgLock data` folder beside itself (`gfglock\utils\paths.py`).

---

## 4. Native C++ Extension

Compiles `gfglock_native.pyd` (OpenSSL-backed AES-256 GCM and CFB, ChaCha20-Poly1305, and PBKDF2) into `gfglock\core\`, and the Explorer shell extension `gfglock_shell.dll` into `build\shell\`.

```powershell
.\scripts\build_native.ps1
```

The script fetches vcpkg into `.vcpkg\` at the commit pinned in `native\vcpkg-commit.txt` (which fixes the OpenSSL version), installs OpenSSL through it, and finishes by loading the new module the way the app does; the build fails if the app couldn't use it. Without the native module the app runs on the slower pure-Python ciphers, which read and write the same files.

---

## 5. Run Tests

```powershell
pytest
```

The tests cover the native engine and the Python fallback (every cipher, and files encrypted by one and decrypted by the other), file safety (no overwrites, no data loss on failures), the controllers, the file list model, settings, and the read size speed test. Set `QT_QPA_PLATFORM=offscreen` to run them without a display.

Check a build the way the release workflow does:

```powershell
python -m gfglock --self-test
```

---

## 6. Builds

Every script runs from the repository root, writes its output under `build\`, and runs the built app with `--self-test` before it reports success.

| Command | Output |
|---|---|
| `.\scripts\build.ps1` | Native extension, both installers, and the portable exe |
| `.\scripts\build_user_installer.ps1` | `build\installer\gfgLock_<version>_user_installer.exe` (no admin rights; installs to `%APPDATA%\gfgLock`) |
| `.\scripts\build_system_installer.ps1` | `build\installer\gfgLock_<version>_system_installer.exe` (admin; installs to `Program Files`) |
| `.\scripts\build_portable.ps1` | `build\gfgLock_<version>_portable.exe` (one file, no install) |

The PyInstaller options (hidden imports, Qt hooks, bundled data) live in `scripts\bundle.ps1`, shared by every build. The version comes from `pyproject.toml`; keep `APP_VERSION` in `gfglock\config\defaults.py` the same (a test checks it).
