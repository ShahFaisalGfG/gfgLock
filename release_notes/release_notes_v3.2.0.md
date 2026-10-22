# gfgLock v3.2.0 - Release Notes

**Released:** October 2026 · **Status:** Stable · **Platform:** Windows 10 (1809 or later) / 11 (64-bit)

---

v3.2.0 introduces a new encrypted file format with Argon2id key derivation, closes several ways a file could be lost or left readable, and makes gfgLock lighter: the installers are about 40% smaller and the portable exe is a third of its old size. Large file lists stay responsive, and Stop now ends the files in progress without touching them.

---

## Breaking Changes

- **New file format (v2) for new files.** Files encrypted with 3.2 can only be opened by gfgLock 3.2 or later. gfgLock 3.2 still opens every file made by earlier versions, and no re-encryption is needed. The extensions stay the same (`.gfglock` for AES-256 GCM, `.gfgcha` for ChaCha20-Poly1305).
- **AES-256 CFB is decrypt-only.** It can't detect a wrong password or an altered file, so it is no longer offered for new files. Existing `.gfglck` files still decrypt. A preference that chose CFB now loads as AES-256 GCM.
- The encryption method and **Hide file names** are chosen on the **Encrypt** tab, which remembers them; the separate **Encryption** page in Preferences is gone.

---

## Added

- **Argon2id key derivation.** Your password goes through Argon2id (256 MB of memory, 3 passes) once per run, and every file then gets its own key from it through HKDF-SHA256. Guessing passwords on a graphics card costs far more than with the PBKDF2 used before, while a folder of thousands of small files still costs a single derivation.
- **An authenticated header and chunked encryption.** Every file is sealed in 1 MB chunks, each checked on its own, and the file's header is part of every check. A file cut short, reordered, or edited anywhere fails to open, files larger than 64 GB work, and a wrong password is noticed at the first chunk instead of after reading the whole file.
- **Original dates come back.** Decrypting restores the file's modification time, and a file downloaded from the internet keeps its *Mark of the Web* through encrypting and decrypting, so Office Protected View and SmartScreen still apply to it.
- **Stop ends the files in progress.** Pressing Stop (or Esc) ends the files being worked on at once; they stay exactly as they were and wait for the next run.
- **Optimize for this PC** also measures **Files at a time**, so both speed settings can be tuned to your PC. The test reads its file fresh from the disk each time, so the result reflects your disk instead of the memory cache.
- **Caps Lock hint** under the focused password field.
- **Licences:** the full licence texts of every bundled component ship in `licenses`, listed in `THIRD_PARTY_NOTICES.md`.

## Changed

- **Smaller and faster to start.** Only the parts of Qt the app uses are bundled: the installers went from 58 MB to 35 MB and the portable exe from 169 MB to 50 MB.
- **Notifications** appear only when gfgLock is in the background or the run took longer than 10 seconds, and they come from gfgLock itself instead of a hidden PowerShell window. Clicking one brings gfgLock to the front.
- **Large lists stay responsive.** A run over 20,000 files used to spend about 6 minutes of the window's time on bookkeeping; it now spends about 4 seconds.
- **Clearer results:** when every failure has the same reason (a wrong password, say), the summary states it once; a stopped run lists what failed or was skipped; long runs show minutes and seconds.
- **Preferences** previews the theme as you pick it and puts the saved one back on Cancel or Esc. The window is wider, so each setting sits beside its label, and **Reset** says that it saves at once.
- **Windows** open centred on their own monitor and fit small or scaled screens; Maximize fills one monitor instead of every monitor.
- **Logs** rotate at 5 MB and keep one older copy. With **Hide file names** on, the log no longer records which hidden name belongs to which original file.
- **Installers:**
  - They ask you to close a running gfgLock instead of ending it, and they no longer restart Explorer or ask for a reboot to replace the context-menu DLL.
  - gfgLock now gets its own Start menu folder.
  - The desktop icon and the "View README" box are unticked by default.
  - The context-menu entries are no longer pinned to the top of the menu.
  - Installing on ARM64 PCs and on Windows versions before 10 1809 is refused, since the context menu can't work there.
- **The portable `.7z`** keeps its settings beside itself, like the portable exe, and now includes the licences. The two installer `.7z` copies are no longer published.
- On Windows 11 the context-menu entries are under **Show more options** (or Shift+F10); the readme now says so.

## Fixed

- **Data loss with a wrong password on CFB files:** about 1 time in 450, a wrong password produced a valid-looking file name, and the `.gfglck` file was deleted and replaced by unreadable data. A `.gfglck` file is now removed only when the restored name matches its own; otherwise it is kept and the row says why.
- **Hard-linked files** were reported as encrypted while another link to the same data stayed readable. They are skipped now, with the reason.
- **A file edited during encryption** could be deleted along with the newer content. The original is now removed only if it is still the version that was read.
- **Wrong folder from Explorer:** a folder whose name ends with an apostrophe (`Teachers'`) was opened as the folder without it. Names now arrive exactly as Explorer sends them.
- **Folders dropped while another folder was being scanned** stopped the first scan partway, so many of its files were never encrypted. Both folders are now listed in full.
- **Files sent from Explorer while gfgLock was starting** or busy could be lost, and several files opened at once could start several windows. Every launch now reaches one window.
- **System and app folders** (Windows, Program Files, ProgramData, AppData, and gfgLock's own folders) and files marked *System* are no longer encrypted, with one notice saying what was left out.
- **Programs started by name:** the notification and "Show in folder" started PowerShell and Explorer by name, which Windows could resolve to a copy placed next to gfgLock. Neither is started that way now.
- **Temporary files** left by a crash or power cut are removed at the start of the next run in that folder.
- **The bundled OpenSSL** depended on the build PC: builds made from Git Bash shipped Git's OpenSSL 3.5.7 instead of the pinned 3.6.5. The pinned version is always shipped, and the self-test checks it.
- **The context-menu DLL** needed the Visual C++ runtime, which isn't on every PC, so the entries could be missing. It no longer needs it.
- **Upgrading from 2.6.9-3.0.0** left a second entry in *Installed apps*, and uninstalling that entry deleted the new installation and its settings. The old entry is removed during the upgrade.
- **Silent installs** (winget, Intune) could hang on a question box, and the system installer deleted the settings of a per-user copy it replaced.
- Clearing the list during a folder scan brought rows back; a second launch's notice could be lost; a file name with invisible direction characters could disguise its extension; startup errors were hidden behind the splash screen and not logged.

---

## Dependencies

- OpenSSL 3.6.5 (native engine), PySide6 6.11.2, cryptography 50.0.1, pycryptodome 3.23.0, built with PyInstaller 6.22.3 and Python 3.12.
- `requirements.txt` pins every package the build and tests use, the release workflow pins Inno Setup and wingetcreate, and native builds use Visual Studio 2022, matching the runtime the app ships.
- The native engine's API version is now 5; an older `gfglock_native` module is ignored in favour of the Python fallback.

---

## Upgrading

1. Run the v3.2.0 package that fits your setup. It updates an existing installation in place, including installations of 2.6.9 to 3.0.0:
   - `gfgLock_3.2.0_system_installer.exe` - system-wide, requires administrator.
   - `gfgLock_3.2.0_user_installer.exe` - per-user, no administrator required.
   - `gfgLock_3.2.0_portable.exe` - runs without installing; settings and logs stay in a `gfgLock data` folder beside the exe.
2. No re-encryption is needed. Files encrypted with earlier versions decrypt as before. Files you encrypt with 3.2 need 3.2 or later to open, so update every PC you share files with.

---

*Stay secure. Encrypt responsibly.*
