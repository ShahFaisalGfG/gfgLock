# gfgLock v3.1.0 - Release Notes

**Released:** October 2026 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v3.1.0 redesigns gfgLock around one window with **Encrypt** and **Decrypt** tabs, in the same design as CC-Gen-Ultimate, and makes every file operation safe against data loss. Large files now encrypt at about the speed of the disk, and Preferences can measure the fastest read size for your PC.

---

## Breaking Changes

None for your files. Everything encrypted with earlier versions decrypts unchanged, and no re-encryption is needed.

- Encrypted files now keep the full original name (`report.docx` becomes `report.docx.gfglock`, not `report.gfglock`), so two files that differ only by extension can no longer collide.
- The **Read size** preference now offers **Automatic** (4 MB) and 1 MB to 64 MB. A size picked in an earlier version is kept (128 MB becomes 64 MB); the old defaults (16 MB encrypting, 32 MB decrypting) become Automatic.
- Options that no longer exist are removed from `settings.json` when the app starts.

---

## Added

- **One window, two tabs.** The launcher and its pop-up dialogs are replaced by **Encrypt** and **Decrypt** tabs. Each keeps its own file list, and every file shows its progress and its result: *Done* with the name it was saved as, *Skipped*, or *Failed* with the reason. Failed files stay in the list to run again; finished ones can be removed. The right-click menu offers **Show in folder** and copying names or paths.
- **Guided form.** Each tab says what is still missing before it can start, shows password strength in words and as a bar, flags mismatched passwords, and explains what will happen to the files before anything changes.
- **Drop anywhere.** Dropped files go to the tab they belong on: encrypted files to Decrypt, everything else to Encrypt. Files sent from the Explorer context menu while gfgLock is open join that window.
- **Run speed test** (Preferences → Speed) encrypts and decrypts a 256 MB test file with every read size and selects the fastest for this PC, separately for encrypting and decrypting.
- **Keyboard shortcuts:** Ctrl+1 / Ctrl+2 tabs, Ctrl+O add files, Ctrl+Shift+O add folder, Ctrl+Enter or F5 start, Esc stop, Ctrl+, preferences, F1 about; in the list Ctrl+A, Space, Ctrl+C, Delete, and Shift+F10 or the Menu key. Every control can be reached with Tab and shows a focus outline.
- **Large folders** are scanned in the background, with a live count and a Stop button.
- **Release checks:** every build runs the app with `--self-test` (native engine, every algorithm on the native and Python paths, every QML screen, and every image the app shows) before it is published.

## Changed

- **Faster encryption.** Reading, encrypting, and writing a file now overlap instead of taking turns: a 1 GB file encrypts in about 3.8 s instead of 5.5 s on a SATA SSD, about the disk's own copy speed. Without the disk in the way, AES-256 GCM now runs at about 1.4 GB/s on one core, up from about 300 MB/s.
- **Read size** defaults to **Automatic** (4 MB) and now applies to decrypting too; it used to be ignored there.
- **AES-256 CFB** is labelled *legacy*. Measured on current PCs it is the slowest of the three methods (about 580 MB/s against 1.4 GB/s for GCM), and it can't detect a damaged or altered file. GCM remains the default.
- Files can be added while a job runs; they wait for the next run, and a notice says so.
- Closing gfgLock during a job asks first, then lets the files in progress finish.
- Dialogs dim the window with a dark layer in both themes.
- The installers ship `THIRD_PARTY_NOTICES.md` and the offline readme under `docs`, and Explorer refreshes file icons after installing.

## Fixed

- **Data loss:** files with the same name but different extensions (`report.docx`, `report.pdf`) were both encrypted to `report.gfglock`, losing one original. No operation ever overwrites an existing file now.
- **Unsafe decryption names:** the file name stored inside an encrypted file is validated, so a tampered file can't write outside its folder, to a device name such as `NUL`, or into an NTFS stream.
- **A file in both forms:** a read-only file, or one open in another program, could end up both encrypted and unencrypted. It now fails with the reason, and nothing changes.
- **Links:** encrypting a symbolic link removed the link and left the file it points to readable. Links are skipped, and folder scans no longer follow junctions, which could loop forever.
- **Leftover temporary files** after an unexpected error.
- Turning **Keep the PC responsive** on or off reset **Files at a time** to 1.
- Files with non-ASCII names (`résumé.txt`) failed to encrypt on the native path, and names like `café.txt` were restored garbled.
- Encrypting a file named like `A.GFGLOCK` could delete it; dropping a folder added the folder itself instead of its files.
- A damaged or hand-edited settings file could stop Start from working.
- **System-wide uninstall** deleted every user's `%APPDATA%\gfgLock` folder, including other users' per-user installs and settings. Uninstalling also never deletes other files in the install folder now.
- In the dark theme, an open dialog faded the window to a pale grey that looked like a frozen app.

---

## Dependencies

- OpenSSL 3.6 (native engine), PySide6 6.7 or later, cryptography 46 or later, pycryptodome 3.20 or later.
- Removed the unused `py-cpuinfo`.
- The native engine's API version is now 4; an older `gfglock_native` module is ignored in favour of the Python fallback.

---

## Upgrading

1. Run the v3.1.0 package that fits your setup. It updates an existing installation in place:
   - `gfgLock_3.1.0_system_installer.exe` - system-wide, requires administrator.
   - `gfgLock_3.1.0_user_installer.exe` - per-user, no administrator required.
   - `gfgLock_3.1.0_portable.exe` - runs without installing; settings are kept in `%APPDATA%\gfgLock`.
2. No re-encryption is needed. Files encrypted with earlier versions decrypt as before.

---

*Stay secure. Encrypt responsibly.*
