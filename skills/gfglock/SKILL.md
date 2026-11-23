---
name: gfglock
description: Encrypt, decrypt, and check files and folders with a password using gfglock, the command line of gfgLock (AES-256-GCM or ChaCha20-Poly1305 with Argon2id). Use it when the user asks to lock, protect, encrypt, or password-protect files or folders, to open or decrypt .gfglock, .gfgcha, or .gfglck files, to check a password against encrypted files, or to change gfgLock's preferences.
license: MIT
compatibility: Windows 10 or 11 with gfgLock installed (or its portable 7z); elsewhere from source with Python 3.12.
metadata:
  version: "3.2.1"
  homepage: https://github.com/ShahFaisalGfG/gfgLock
---

# gfglock

`gfglock` is the command line of gfgLock. It encrypts files and whole folders with a password, decrypts them again under their original names, and checks a password without changing anything. It uses the same engine, rules, and preferences as the gfgLock window.

Encrypting replaces each file with its encrypted copy (`report.docx` becomes `report.docx.gfglock`), and decrypting replaces the encrypted file with the restored one. A file is replaced only after its new copy is written and checked, and an existing file is never overwritten. If the password is lost, nobody can open the files.

## Find the command

1. `gfglock --version`: the installers can add it to PATH.
2. Otherwise run it from the install folder:
   - `%APPDATA%\gfgLock\bin\gfglock.exe` (installed for one user)
   - `%ProgramFiles%\gfgLock\bin\gfglock.exe` (installed for all users)
   - `bin\gfglock.exe` in the folder unpacked from the portable `.7z`
3. From a clone of the repository: `python -m gfglock.cli` (Python 3.12).

If none is there, tell the user to install gfgLock from https://github.com/ShahFaisalGfG/gfgLock/releases.

## The password

Never put a password on the command line or in a file inside a project, and never print it. Give it to gfglock in one of three ways:

- `--password-env NAME`: an environment variable the user set (best for agents).
- `--password-file FILE`: the first line of a file the user made, outside the project.
- `--password-stdin`: the first line piped in, read as UTF-8. Windows PowerShell 5.1 pipes non-ASCII text as `?`, so prefer `--password-env` there.

Without one of these, gfglock asks on a terminal, and exits with status 2 when there is no terminal.

## Common tasks

Always add `--json`. Try a folder with `--dry-run` first: it lists what would change and changes nothing.

```powershell
gfglock encrypt "D:\Taxes" --dry-run --json
gfglock encrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --json
gfglock encrypt report.docx budget.xlsx --password-env GFGLOCK_PASSWORD --keep-originals --json
gfglock encrypt "D:\Photos" --password-file "C:\Users\me\gfglock-key.txt" --output-dir "E:\Backup" --json
gfglock encrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --hide-names --algorithm chacha20-poly1305 --json
gfglock verify "D:\Taxes" --password-env GFGLOCK_PASSWORD --json
gfglock decrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --json
gfglock decrypt backup.zip.gfglock --password-env GFGLOCK_PASSWORD --output-dir "D:\Opened" --keep-originals --json
gfglock info backup.zip.gfglock --json
```

- Folders are walked with their subfolders. Encrypting leaves out Windows, program, and app folders, links, and files already encrypted; decrypting takes only gfgLock's files.
- `--keep-originals` leaves the files that were read in place; `--output-dir DIR` saves the results in another folder. Without them gfglock does what the app's tab was last set to, which is replace in place unless the user changed it (the `start` event says what applies).
- `--hide-names` gives encrypted files random names; decrypting restores the original ones.
- `verify` checks the password and that each file is intact, writing nothing. Use it before `decrypt` when the password is uncertain.
- `info` reads a file's header without a password: format, method, key derivation cost, and whether the name is hidden.

## Preferences

The command line reads and writes the same preferences as the app's Preferences window.

```powershell
gfglock settings list --json
gfglock settings get advanced.encryption_mode --json
gfglock settings set encryption.cpu_threads 4 --json
gfglock settings reset --json
```

Every command and option is in [references/commands.md](references/commands.md).

## Read the result

With `--json`, stdout carries only JSON. `encrypt`, `decrypt`, and `verify` print one object per line: read the `file` events for the files written, `error` events for files that failed, and the last line, the `done` event, for the outcome:

```json
{"event": "file", "path": "D:\\Taxes\\2025.pdf", "output": "D:\\Taxes\\2025.pdf.gfglock", "action": "encrypted"}
{"event": "error", "path": "D:\\Taxes\\open.xlsx", "category": "in_use", "message": "The file is open in another program. Close it and try again"}
{"event": "done", "ok": false, "exit_code": 1, "message": "1 of 2 files encrypted. 1 failed: 1 in use.", "total": 2, "done": 1, "failed": 1, "skipped": 0, "stopped": 0, "failures": {"in_use": 1}, "elapsed": 1.2, "algorithm": "aes-256-gcm", "hide_names": false, "keep_originals": false, "output_dir": ""}
```

`info`, `settings`, and `skill` print a single object. Every event, field, and failure category is in [references/json-events.md](references/json-events.md).

## Exit status

| Code | Meaning |
|---|---|
| `0` | Every file was done, or left alone on purpose (already encrypted, a link). |
| `1` | Some files failed (a wrong password, a file in use, a full drive). The others are done. |
| `2` | Nothing to do, or the input can't be used: no password source, a path that doesn't exist, not enough free space, an option gfglock doesn't know. Nothing was changed. |
| `130` | Stopped with Ctrl+C. Files in progress were left unchanged; the same command finishes the rest. |

## Rules for agents

- Ask the user before encrypting or decrypting in place: the originals are replaced. When in doubt, use `--dry-run`, then `--keep-originals` or `--output-dir`.
- Never choose a password for the user, and never store, print, or repeat one. Ask the user to set it in an environment variable or a file and pass its name.
- A `wrong_password` failure changes nothing. Ask the user for the right password instead of retrying variations.
- Don't encrypt a project's source files, the user's whole profile, or system folders unless the user asked for exactly that.
- Turning the password into a key (Argon2id) takes a few seconds before the first file starts, and large folders can take minutes. Use a long timeout, and don't stop and restart a run that is making progress.
- Losing the password means losing the files. Say so when the user encrypts something for the first time.

## The skill itself

```powershell
gfglock skill install
gfglock skill install --agent cursor
gfglock skill show
```

`gfglock skill install` copies this skill into `~/.agents/skills` and `~/.claude/skills`; `--agent NAME` or `--dir FOLDER` choose other folders, and `gfglock skill show` prints it for agents that can't load skills.
