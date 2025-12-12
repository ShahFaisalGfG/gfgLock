# gfgLock - setup v1.0.0

**Release date:** 2025-12-11

**Release page:** [gfgLock - GitHub Releases](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock)

## Binaries included

- `gfgLock_Setup_1.0.0.exe` — Windows installer (Inno Setup)
- `gfgLock_Setup_1.0.0.rar` — Archive containing installer and extras

## Overview

This release introduces the first packaged Windows GUI build of gfgLock (v1.0.0).
The GUI is a user-friendly wrapper around the high-performance `gfglock_fast_aes256_cryptography.py` backend (AES‑256 CFB via the `cryptography` library / OpenSSL).

## Highlights

- Standalone Windows installer built with Inno Setup — no separate Python install needed for the shipped build.
- Modern GUI with drag & drop support for files and folders.
- Batch processing: enqueue multiple files/folders and process them in one run.
- Progress dialog with live per-file logs and summary counts for succeeded / failed / skipped items.
- Optional filename randomization for encrypted outputs and context‑menu integration.
- File extension used by the GUI: `.gfglock` (compatible with the Python Cryptography backend).

## Installation

1. Download `gfgLock_Setup_1.0.0.exe` from the [release page](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock).
2. Run the installer and follow the setup wizard.
3. Launch `gfgLock` from the Start Menu or desktop shortcut.

If you prefer to inspect or archive the installer manually, download `gfgLock_Setup_1.0.0.rar` and extract it with your archive tool.

## Quick Usage (GUI)

1. Launch the application.
2. Drag & drop files or folders, or use the "Add Files" / "Add Folders" buttons.
3. Enter a strong password (and confirm it when encrypting).
4. Optionally adjust CPU threads and chunk size for performance.
5. Click "Start Encryption" or "Start Decryption".
6. Use the progress dialog to monitor per-file messages and to copy the log to the main window after completion.

## Command-line / Developer Notes

- The GUI is a frontend for the `gfglock_fast_aes256_cryptography.py` backend; that Python module remains available for CLI use and scripting.
- CLI users can still call `encrypt_folder` / `decrypt_folder` directly from Python; see the repository scripts for examples.

## Security & Verification

- The application uses AES‑256 in CFB mode with a SHA‑256 derived key from the provided password. Use strong, unique passwords (12+ chars recommended).
- Always decrypt files with the same tool that encrypted them (the GUI and the Cryptography backend are compatible; other backends use different extensions).

## Checksums (recommended)

It is recommended to verify the downloaded installer. You can compute a SHA‑256 checksum locally, for example on Windows (PowerShell):

```powershell
Get-FileHash -Path .\gfgLock_Setup_1.0.0.exe -Algorithm SHA256 | Format-List
```

## Known issues & limitations

- The installer currently targets 64‑bit Windows only.
- The GUI uses `.gfglock` for files encrypted by the Cryptography backend; other backends in this repository create different file extensions (`.gfgpcd`, `.gfgssl`) and are not cross-compatible.
- Drag & drop and context‑menu integration require Explorer and may need elevated privileges to register file associations during install.

## Credits & Contact

Developed by Shah Faisal — gfgRoyal

Report issues or request features via the GitHub repository: [Issues · gfgLock](https://github.com/ShahFaisalGfG/gfgLock/issues)

## License

MIT License
