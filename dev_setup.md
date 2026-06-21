# Developer Setup Guide

## Requirements

- Python 3.11+
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for building the Windows installer)
- Visual Studio 2022+ Build Tools with the C++ workload, CMake ≥ 3.25 (for the native C++ extension)

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

This installs: `PySide6`, `cryptography`, `pycryptodome`, `pyinstaller`, `py-cpuinfo`, `pytest`.

---

## 3. Run in Development Mode

```powershell
python -m gfglock
```

Pass a file path to pre-populate the encrypt/decrypt dialog:

```powershell
python -m gfglock "C:\path\to\file.txt"
```

---

## 4. Native C++ Extension

Compiles the `gfglock_native.pyd` extension (OpenSSL-backed AES-256-GCM, CFB, ChaCha20-Poly1305, KDF) and places it in `gfglock/core/`.

**Requirements:** Visual Studio 2022+ Build Tools (C++ workload), CMake ≥ 3.25.

```powershell
.\build_native.ps1
```

The build script bootstraps vcpkg automatically if `.vcpkg/` is missing.

---

## 5. Run Tests

```powershell
pytest
```

Runs tests covering:

- **Native acceleration** (AES-256-GCM, CFB, ChaCha20-Poly1305)
- **Python fallback** (all cipher modes with native C++ disabled)
- **Cross-path compatibility** (native-encrypted files decryptable by Python fallback and vice versa)

---

## 6. Debug Build (PyInstaller)

Produces a multi-file `dist/gfgLock/` folder - faster iteration, no compression:

```powershell
pyinstaller `
  --name gfgLock `
  --icon gfglock\assets\icons\gfgLock.ico `
  --add-data "gfglock\assets;gfglock\assets" `
  --add-data "gfglock\qml;gfglock\qml" `
  --collect-data PySide6 `
  --hidden-import PySide6.QtQml `
  --hidden-import PySide6.QtQuick `
  --hidden-import PySide6.QtQuickControls2 `
  --noconfirm `
  gfglock\__main__.py
```

Run the result:

```powershell
.\dist\gfgLock\gfgLock.exe
```

---

## 7. Release Build (PyInstaller)

Adds `--optimize 2` and `--windowed` to strip bytecode assertions and suppress the console window:

```powershell
pyinstaller `
  --name gfgLock `
  --icon gfglock\assets\icons\gfgLock.ico `
  --add-data "gfglock\assets;gfglock\assets" `
  --add-data "gfglock\qml;gfglock\qml" `
  --collect-data PySide6 `
  --hidden-import PySide6.QtQml `
  --hidden-import PySide6.QtQuick `
  --hidden-import PySide6.QtQuickControls2 `
  --windowed `
  --optimize 2 `
  --noconfirm `
  gfglock\__main__.py
```

The output directory `dist\gfgLock\` is what the Inno Setup scripts reference as `SourceDir`.

---

## 8. Windows Installer (Inno Setup)

Run either script with Inno Setup's command-line compiler (`iscc.exe`).

**System-wide installer** (requires admin, installs to `Program Files`):

```powershell
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" installer\gfglock_system_installer.iss
```

**Per-user installer** (no admin required, installs to `AppData\Local`):

```powershell
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" installer\gfglock_user_installer.iss
```

The compiled `.exe` installer is written to `installer\Output\`.

> Build the release PyInstaller bundle first (step 7) before running the installer script,
> because the `.iss` files reference `dist\gfgLock\` as the source directory.
