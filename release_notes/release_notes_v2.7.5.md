# gfgLock v2.7.5 — Release Notes

**Released:** May 2026

---

## Overview

v2.7.5 is a major release delivering a complete UI framework rewrite, a clean MVC package restructure, CLI-aware launch, Windows OS notifications, an enhanced progress dialog, and a range of targeted UX improvements and bug fixes.

---

## Breaking Changes

- **Python package layout changed.** The application is now run as `python -m gfglock` (previously `python src/gui.py`). Update any scripts or shortcuts accordingly.
- **Files encrypted with v2.7.0 or earlier cannot be decrypted with v2.7.5.** True chunk processing was introduced for decryption, which changed the encrypted file format. Re-encrypt any v2.7.0 files before deleting the originals.

---

## What's New

### Framework — PySide6 + QML

The entire UI has been rewritten from PyQt6 widgets to **PySide6 + QML** with the Material style. This brings:

- Crisp, hardware-accelerated (UI) rendering via Qt Quick
- Consistent Material Design language across all screens
- Cleaner separation between UI (QML) and logic (Python controllers)

### Package Structure — MVC Layout

The flat `src/` directory has been replaced with a proper Python package at `gfglock/`:

```text
gfglock/
├── controllers/   — app, encrypt, preferences logic
├── core/          — AES-256 GCM/CFB, ChaCha20-Poly1305, chunk processing
├── models/        — file list model (QAbstractListModel)
├── qml/           — all QML UI files and components
├── services/      — multi-threaded worker, OS notifier
├── utils/         — logging, settings, helpers
└── config/        — defaults and UI configuration constants
```

### True Chunk Processing

Decryption now uses true streaming chunk processing, matching the encryption path. This resolves memory pressure on large files and ensures correct MAC validation per chunk. This change required a file-format update; see Breaking Changes above.

### CLI-Aware Launch

gfgLock can now be invoked from the command line or from Windows Explorer shell extensions with files pre-loaded:

```powershell
# Explicit mode
python -m gfglock encrypt file1.txt file2.docx

# Auto-detect decrypt from encrypted extensions
python -m gfglock archive.gfglock photo.gfglck
```

- Detects `encrypt` or `decrypt` mode from the first argument or from file extensions (`.gfglock`, `.gfglck`, `.gfgcha`).
- Sets the dialog mode automatically so the correct operation is pre-selected when the window opens.
- Handles Windows Explorer path reconstruction for paths containing spaces.

### Windows OS Notifications

A new `notifier` service posts a native Windows toast notification when an encryption or decryption session completes. Configurable via **Preferences → Advanced → Notifications → Operation Completed Notifications**.

### Log Panel Text Wrap

A new **Preferences → Appearance → Logs Panel → Text Wrap** toggle controls whether long log lines wrap or scroll horizontally. Defaults to on.

### Enhanced Progress Dialog

The completion state of the progress dialog has been significantly improved:

- The header title changes to **"Encryption/Decryption Complete"** (green) or **"… Completed with Errors"** (amber) on finish.
- The summary line uses natural language: *"All 5 files encrypted successfully in 2.3s."*, *"3 of 4 files encrypted · 1 failed · 1.8s."*, etc.
- Progress bar snaps to 100 % on completion.

### Continuous Progress Bar

The progress bar now updates smoothly and continuously during multi-file operations, rather than advancing in discrete per-file jumps.

### Remaining Time Estimation

The progress dialog shows a live ETA (e.g. *"~12 s remaining"*) during active operations, updated each time a file completes.

### Right-Click Context Menu — Log Panels

Both the main Activity Log and the in-dialog progress log now expose a right-click menu with **Copy** (enabled only when text is selected) and **Select All** actions.

### Silent User Installer

A new **silent** installer variant (`gfglock_silent_user_installer.iss`) allows unattended per-user installation with no UI. Useful for managed deployment or scripted environments.

```powershell
.\build_silent_user_installer.ps1
# Output: build\installer\gfgLock_2.7.5_silent_user_installer.exe
```

### UX Improvements

- **Animated floating labels** — password fields show a centered placeholder; on focus the label animates to the top border as a fieldset-legend.
- **Smart Enter key flow** — empty panel → opens file picker; files loaded + valid password → starts operation; after completion → closes dialog.
- **Delete key** — removes selected files from the file panel (same as the Remove button).
- **Auto-focus** — password field receives focus when files are added or the dialog opens with files pre-loaded.
- **Compact checkboxes** — "Show password" and "Encrypt file names" checkboxes now have the correct compact height.
- **Consistent log padding** — the progress log inside the Encrypt/Decrypt dialog matches the padding of the main Activity Log.
- **Activity log placeholder** — a *"No activity yet…"* hint is shown inside the log area when empty.

---

## Bug Fixes

- **Space keypress sending multiple requests** — pressing Space in the progress dialog repeatedly triggered new encrypt/decrypt operations. Fixed by properly guarding the key handler.
- **`chunk_size` type mismatch** — the setting was stored as a string but passed directly to the crypto core expecting an int, causing a runtime error on non-default values. Now correctly cast on read.
- **Unified encrypt-filenames setting** — the "Encrypt file names" preference was duplicated across two independent settings keys. Consolidated to a single authoritative key so Preferences and the dialog always agree.
- **CLI mode not propagated to dialog** — when files were passed via CLI, the mode was detected for file loading but the dialog still defaulted to Encrypt. Now `enc_ctrl.setMode()` is called to align the dialog to the detected mode.

---

## Build & Tooling

### Separate Installer Build Scripts

Three dedicated PowerShell build scripts replace the single `build.ps1`:

| Script | Output |
| --- | --- |
| `build_system_installer.ps1` | `gfgLock_2.7.5_system_installer.exe` |
| `build_user_installer.ps1` | `gfgLock_2.7.5_user_installer.exe` |
| `build_silent_user_installer.ps1` | `gfgLock_2.7.5_silent_user_installer.exe` |
| `build_portable.ps1` | `gfgLock_2.7.5_portable.exe` |

Each script activates the virtual environment, validates prerequisites (Python, PyInstaller, Inno Setup 6), cleans previous artifacts, runs PyInstaller (`--onedir`, bundles QML and assets), compiles the Inno Setup installer, and reports bundle and installer sizes.

---

## Dependencies

| Package      | Version |
| ------------ | ------- |
| PySide6      | 6.7+    |
| cryptography | 3.4+    |
| pycryptodome | 3.4+    |
| py-cpuinfo   | 9.0+    |

---

## Upgrading

1. Uninstall the previous version via Add/Remove Programs (or delete the portable folder).
2. Install the appropriate installer:
   - `gfgLock_2.7.5_system_installer.exe` — system-wide, requires administrator.
   - `gfgLock_2.7.5_user_installer.exe` — per-user, no administrator required.
   - `gfgLock_2.7.5_portable.exe` — portable, no install required
3. **Re-encrypt any files that were encrypted with v2.7.0 or earlier** before deleting the originals, as those cannot be decrypted by v2.7.5.

---

**Stay Secure. Encrypt Responsibly.**
