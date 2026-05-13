# Developer Setup Guide

## Requirements

- Python 3.11+
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for building the Windows installer)

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

This installs: `PySide6`, `cryptography`, `pycryptodome`, `pyinstaller`, `py-cpuinfo`.

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

## 4. Debug Build (PyInstaller)

Produces a multi-file `dist/gfgLock/` folder — faster iteration, no compression:

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

## 5. Release Build (PyInstaller)

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

## 6. Windows Installer (Inno Setup)

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

> Build the release PyInstaller bundle first (step 5) before running the installer script,
> because the `.iss` files reference `dist\gfgLock\` as the source directory.
