# Developer Setup Guide

## Requirements

- Windows 10 version 1809 or later, x64
- Python 3.12 (x64) from python.org, with its default `include` and `libs` folders (the native build links against them)
- PowerShell 7.2 or later (`pwsh`) for the build scripts; Windows PowerShell 5.1 can't run them
- Visual Studio 2022 (17.x) Build Tools with the C++ workload and the "C++ CMake tools for Windows" component (for the native extension; the build script uses the CMake and Ninja that come with it)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php), 6.7 or later (for the installers; the release workflow uses 6.7.1)

---

## 1. Virtual Environment

Run these from the repository root in `pwsh`:

```powershell
# Create
python -m venv .venv

# Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate (CMD)
.venv\Scripts\activate.bat
```

The build scripts activate `.venv` themselves, so it only needs to exist.

---

## 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs the exact versions every build uses: `PySide6`, `cryptography`, `pycryptodome`, `pyinstaller`, `pybind11`, and `pytest`, plus the packages they depend on. `pyproject.toml` lists the looser version ranges the code supports.

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

In development mode, settings are kept in `gfglock\utils\settings.json` and logs in `logs\`. The installed app keeps them in `%APPDATA%\gfgLock`, and the portable builds in a `gfgLock data` folder beside the exe (`gfglock\utils\paths.py`).

---

## 4. Native C++ Extension

Compiles `gfglock_native.pyd` (the OpenSSL-backed native engine) into `gfglock\core\`, and the Explorer shell extension `gfglock_shell.dll` into `build\shell\`.

```powershell
.\scripts\build_native.ps1
```

The script downloads a source archive of vcpkg at the commit pinned in `native\vcpkg-commit.txt` into `.vcpkg\` (no git clone; the commit fixes the OpenSSL version), installs OpenSSL through it, takes pybind11 from the venv (installed by `pip` in step 2), and finishes by loading the new module the way the app does; the build fails if the app couldn't use it. Without the native module the app runs on the slower pure-Python ciphers, which read and write the same files.

---

## 5. Run Tests

```powershell
pytest
```

The tests cover the native engine and the Python fallback (every cipher, and files encrypted by one and decrypted by the other), files made by gfgLock 3.1.0 and older (`tests\fixtures\v1`, which both engines must keep opening), file safety (no overwrites, no data loss on failures), the controllers, the file list model, settings, and the read size speed test. Set `QT_QPA_PLATFORM=offscreen` to run them without a display.

Check the types the way CI does (pyright is an npm package):

```powershell
pyright --pythonpath .venv\Scripts\python.exe gfglock
```

Check a build the way the release workflow does:

```powershell
python -m gfglock --self-test
```

---

## 6. Builds

Every script runs from the repository root, writes its output under `build\` (the one-folder app bundle goes to `dist\gfgLock\`), and runs the built app with `--self-test` before it reports success.

| Command | Output |
|---|---|
| `.\scripts\build.ps1` | Native extension, both installers, and the portable exe |
| `.\scripts\build_installer.ps1 -Kind User` | `build\installer\gfgLock_<version>_user_installer.exe` (no admin rights; installs to `%APPDATA%\gfgLock`) |
| `.\scripts\build_installer.ps1 -Kind System` | `build\installer\gfgLock_<version>_system_installer.exe` (admin; installs to `Program Files`) |
| `.\scripts\build_portable.ps1` | `build\gfgLock_<version>_portable.exe` (one file, no install; uses the native module last built) |

The release workflow also packs the one-folder bundle as `gfgLock_<version>_portable.7z` with `New-PortableArchive` in `scripts\bundle.ps1`.

- `scripts\common.ps1` holds the helpers every script shares (the venv, app metadata, the native build, Inno Setup).
- `scripts\bundle.ps1` holds the PyInstaller options, the self-test run, and the portable archive. The hooks in `hooks\` keep only the Qt modules, plugins, and QML modules the app uses, and PyInstaller runs with PATH folders that hold another OpenSSL build hidden, so the bundle gets the pinned one.
- `installer\common.iss` holds what both installer scripts share; `gfglock_system_installer.iss` and `gfglock_user_installer.iss` add what differs.

The version comes from `pyproject.toml`; keep `APP_VERSION` in `gfglock\config\defaults.py` the same (a test checks it).

Every icon size and `gfgLock.ico` are drawn by `scripts\make_icons.py`; after changing it, run `python scripts\make_icons.py` to regenerate them.

The `licenses` folder holds the full licence text of every bundled component, and `THIRD_PARTY_NOTICES.md` lists the components and every bundled DLL. When a bundled component changes, copy its licence from the package's `*.dist-info` folder (or `native\vcpkg_installed\x64-windows\share\<port>\copyright` for vcpkg ports) and update both.

---

## 7. Contributing

Branch from `dev` and open pull requests against `dev`. The Tests workflow runs pytest (with and without the native engine), pyright, and qmllint on every push and pull request.
