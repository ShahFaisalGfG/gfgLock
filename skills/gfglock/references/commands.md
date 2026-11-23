# gfglock command reference

```text
gfglock encrypt PATH... [options]
gfglock decrypt PATH... [options]
gfglock verify PATH... [options]
gfglock info FILE... [--json]
gfglock settings {list,get,set,reset} [--json]
gfglock skill {install,uninstall,path,show} [options]
gfglock --version
gfglock --help
```

Every command takes `--help`. PATH is a file or a folder; folders are walked with their subfolders.

## encrypt

Replaces each file with an encrypted copy once the copy is written and checked: `report.docx` becomes `report.docx.gfglock` (AES-256-GCM) or `report.docx.gfgcha` (ChaCha20-Poly1305), with " (2)" added when that name is taken. Windows, program, and app folders (and gfgLock's own), files marked System, links, hard-linked files, and files already encrypted are left out.

| Option | Default | What it does |
|---|---|---|
| `--password-stdin` | | Read the password from the first line of stdin, as UTF-8 |
| `--password-env VAR` | | Read the password from the environment variable VAR |
| `--password-file FILE` | | Read the password from the first line of FILE (UTF-8) |
| `--algorithm aes-256-gcm\|chacha20-poly1305` | as in the app (`aes-256-gcm`) | The encryption method |
| `--hide-names` | as in the app (off) | Give encrypted files random names; decrypting restores the original ones |
| `--show-names` | | Keep each name visible, as `report.docx.gfglock` |
| `--keep-originals` | as in the app (off) | Leave each original in place beside its encrypted copy |
| `--replace-originals` | | Remove each original once its encrypted copy is safely saved |
| `--output-dir DIR` | as in the app (next to each file) | Save the encrypted files in DIR (made if missing) |
| `--same-folder` | | Save each encrypted file next to its original |
| `--threads N` | as in the app's Preferences | Files worked on at once (at most the PC's processor threads) |
| `--dry-run` | | List what would change, and change nothing (no password needed) |
| `--json` | | One JSON object per line on stdout (see json-events.md) |
| `-v`, `--verbose` | | Also print the engine's own messages on stderr |

Choose one password option; with none, gfglock asks on a terminal (twice when encrypting) and exits with status 2 without one. A weak password (short, common, or of one kind of character) gets a `warning` event but is allowed.

## decrypt

Restores each file under its original name (stored inside it) and removes the encrypted file once the restored one is written and checked. An existing file is never overwritten: the restored copy gets " (2)" instead. With a wrong password nothing changes. An old `.gfglck` file (gfgLock 3.1 and earlier) is kept unless its restored name matches its own, since that format can't confirm the password.

Options: `--password-stdin`, `--password-env VAR`, `--password-file FILE`, `--keep-originals` (keep the encrypted files), `--replace-originals`, `--output-dir DIR`, `--same-folder`, `--threads N`, `--dry-run`, `--json`, `-v`/`--verbose`, as for encrypt.

## verify

Checks that the password opens each file and that its data is intact, writing nothing. AES-256-GCM and ChaCha20-Poly1305 authenticate every part of the file, so a `checked` file decrypts. The old `.gfglck` format can only have its stored name checked.

Options: `--password-stdin`, `--password-env VAR`, `--password-file FILE`, `--threads N`, `--json`, `-v`/`--verbose`.

## info

Reads each file's plaintext header, without a password: format version (1 is gfgLock 3.1 and earlier, 2 is current), method, key derivation and its cost, chunk size, and whether its name is hidden.

## settings

The same preferences file and rules as the app's Preferences window.

| Command | What it does |
|---|---|
| `gfglock settings list` | Every preference as `key = value` |
| `gfglock settings get KEY` | One preference |
| `gfglock settings set KEY VALUE` | Change one preference; a value the app couldn't use is refused with status 2 |
| `gfglock settings reset` | Every preference back to its default (the installer's choices stay) |

| Key | Values |
|---|---|
| `theme` | `system`, `light`, `dark` |
| `encryption.cpu_threads`, `decryption.cpu_threads` | 1 to the PC's processor threads |
| `encryption.read_size`, `decryption.read_size` | `0` (4 MB), `1048576`, `8388608`, `16777216`, `33554432`, `67108864` |
| `encryption.encrypt_filenames` | `true` or `false` (hide names) |
| `encryption.keep_originals`, `decryption.keep_originals` | `true` or `false` |
| `encryption.output_dir`, `decryption.output_dir` | a full folder path, or `""` for next to each file |
| `advanced.encryption_mode` | `aes256_gcm`, `chacha20_poly1305` |
| `advanced.enable_logs` | `true` or `false` |
| `advanced.log_level` | `critical` (errors only) or `all` |
| `advanced.clamp_cpu_threads` | `true` keeps one processor thread free |
| `advanced.operation_notifications` | `true` or `false` |
| `advanced.auto_check_updates`, `advanced.auto_install_updates` | `true` or `false` |

## The skill command

| Command | What it does |
|---|---|
| `gfglock skill install` | Copy this skill into `~/.agents/skills/gfglock` and `~/.claude/skills/gfglock` |
| `gfglock skill install --agent AGENT` | Into one agent's own folder (repeatable): `agents`, `amp`, `augment`, `claude`, `codex`, `continue`, `copilot`, `cursor`, `droid`, `gemini`, `goose`, `junie`, `kilo`, `kiro`, `opencode`, `openhands`, `qwen`, `roo`, `trae`, `windsurf` |
| `gfglock skill install --dir FOLDER` | Into a skills folder of your own (the skill goes in `FOLDER\gfglock`) |
| `gfglock skill uninstall` | Remove it again (same `--agent` and `--dir` choices) |
| `gfglock skill path` | List the folders it goes in and whether it is there |
| `gfglock skill show` | Print the skill and its references |

Each takes `--json`.

## Examples

```powershell
gfglock --version
gfglock encrypt "D:\Taxes" --dry-run --json
gfglock encrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --json
gfglock encrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --show-names --replace-originals --same-folder --json
gfglock encrypt notes.txt --password-file "C:\Users\me\key.txt" --threads 2 --verbose
gfglock decrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --dry-run --json
gfglock decrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --keep-originals --output-dir "D:\Opened" --json
$env:GFGLOCK_PASSWORD | gfglock verify "D:\Taxes" --password-stdin --json
gfglock info "D:\Taxes\2025.pdf.gfglock" --json
gfglock settings set encryption.keep_originals true --json
gfglock settings set decryption.output_dir "D:\Opened" --json
gfglock skill install --dir "C:\Users\me\.config\agent\skills" --json
gfglock skill uninstall --agent codex
gfglock skill path --json
```
