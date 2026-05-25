# gfgLock v2.7.5 — Release Notes

**Released:** May 2026 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v2.7.5 is a major release delivering a complete UI framework rewrite from PyQt6 widgets to PySide6 + QML, a proper MVC package structure, CLI-aware launch, Windows toast notifications, and a range of targeted UX improvements.

---

## Breaking Changes

- **Encrypted file format changed.** True chunk processing was introduced for decryption, aligning it with the encryption path. **Files encrypted with v2.7.0 or earlier cannot be decrypted with v2.7.5 or later.** Re-encrypt any such files before deleting the originals.
- **Launch command changed.** The application is now run as `python -m gfglock`. The previous entry point (`python src/gui.py`) no longer exists. Update any custom scripts or shortcuts accordingly.

---

## Added

- **PySide6 + QML UI** — the entire interface has been rewritten using PySide6 and QML with the Material style, bringing hardware-accelerated Qt Quick rendering and a clean separation between UI (QML) and logic (Python controllers).
- **MVC package layout** — the flat `src/` directory is replaced with a structured `gfglock/` Python package: `controllers/`, `core/`, `models/`, `qml/`, `services/`, `utils/`, `config/`.
- **True chunk decryption** — decryption now uses the same streaming chunk pipeline as encryption, resolving memory pressure on large files and ensuring correct per-chunk MAC validation.
- **CLI-aware launch** — gfgLock accepts files and an optional mode (`encrypt` / `decrypt`) as command-line arguments. Mode is auto-detected from the first argument or from file extensions when not supplied; handles Windows Explorer paths containing spaces.
- **Windows toast notifications** — a new notifier service posts a native OS notification when an operation completes. Configurable under **Preferences → Advanced → Notifications**.
- **Live remaining time estimate** — the progress dialog shows an ETA (e.g. *"~12 s remaining"*) updated after each file completes.
- **Continuous progress bar** — the bar now updates smoothly and continuously during multi-file operations instead of advancing in discrete per-file jumps.
- **Enhanced completion state** — on finish the progress header changes to *"Encryption/Decryption Complete"* (green) or *"… Completed with Errors"* (amber); the summary line uses natural language (*"All 5 files encrypted successfully in 2.3 s."*).
- **Right-click context menu on log panels** — both the main Activity Log and the in-dialog progress log expose Copy (selection-aware) and Select All actions.
- **Log panel text wrap toggle** — **Preferences → Appearance → Logs Panel → Text Wrap** controls whether long log lines wrap or scroll horizontally.
- **Activity log placeholder** — a *"No activity yet…"* hint is displayed when the log area is empty.
- **Silent user installer** — `gfgLock_2.7.5_silent_user_installer.exe` supports unattended per-user installation for scripted or managed deployment.
- **Animated password field label** — the placeholder animates to the top border as a fieldset-legend on focus.
- **Smart Enter key flow** — no files → opens file picker; files loaded with a valid password → starts operation; after completion → closes the dialog.
- **Delete key removes files** — pressing Delete in the file panel removes selected entries, mirroring the Remove button.
- **Auto-focus password field** — receives focus when files are added or the dialog opens with pre-loaded files.

## Fixed

- **Space key triggering repeated operations** — pressing Space in the progress dialog repeatedly triggered new operations. Fixed by guarding the key handler correctly.
- **`chunk_size` type mismatch** — the setting was stored as a string but passed directly to the crypto core expecting an int, causing a runtime error on non-default values. Now cast correctly on read.
- **Duplicate encrypt-filenames setting** — the preference was split across two independent keys, causing the dialog and Preferences to disagree. Consolidated to a single authoritative key.
- **CLI mode not propagated to dialog** — when files were passed via CLI the mode was detected for file loading but the dialog still defaulted to Encrypt. `enc_ctrl.setMode()` is now called to align the dialog to the detected mode.
- **Log routing** — critical and full log levels were not correctly separated. Fixed so each level writes only to its intended file.

---

## Build & Tooling

Three dedicated PowerShell build scripts replace the previous single `build.ps1`:

| Script | Output |
| --- | --- |
| `build_system_installer.ps1` | `gfgLock_2.7.5_system_installer.exe` |
| `build_user_installer.ps1` | `gfgLock_2.7.5_user_installer.exe` |
| `build_silent_user_installer.ps1` | `gfgLock_2.7.5_silent_user_installer.exe` |
| `build_portable.ps1` | `gfgLock_2.7.5_portable.exe` |

Each script activates the virtual environment, validates prerequisites (Python, PyInstaller, Inno Setup 6), cleans previous artifacts, runs PyInstaller, compiles the Inno Setup installer, and reports output sizes.

---

## Dependencies

| Package | Version |
| --- | --- |
| PySide6 | 6.7+ |
| cryptography | 3.4+ |
| pycryptodome | 3.4+ |
| py-cpuinfo | 9.0+ |

---

## Upgrading

1. Uninstall the previous version via **Add/Remove Programs** (or delete the portable folder).
2. Install the appropriate v2.7.5 package:
   - `gfgLock_2.7.5_system_installer.exe` — system-wide, requires administrator.
   - `gfgLock_2.7.5_user_installer.exe` — per-user, no administrator required.
   - `gfgLock_2.7.5_portable.exe` — portable, no installation required.
3. **Re-encrypt any files encrypted with v2.7.0 or earlier** before discarding the originals — those files are not compatible with v2.7.5.

---

*Stay secure. Encrypt responsibly.*
