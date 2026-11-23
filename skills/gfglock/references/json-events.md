# gfglock --json output

With `--json`, stdout carries only JSON, with any non-ASCII character escaped. Messages meant for people, and the engine's own with `--verbose`, go to stderr. When the options themselves are wrong, argparse prints usage to stderr, nothing goes to stdout, and the exit status is 2.

## encrypt, decrypt, verify

One object per line, each with an `event` field. The last line is always a `done` event.

| Event | When | Fields |
|---|---|---|
| `warning` | Before the run, or a weak password | `message`, `category` (`not_found`, `access_denied`, `protected`, `already_encrypted`, `not_encrypted`, `disk_full`, `weak_password`) |
| `start` | The run begins, once the password is read | `command`, `files`, `total_bytes`, `threads`; for encrypt `algorithm` and `hide_names`; for encrypt and decrypt `keep_originals` and `output_dir` (`""` means next to each file) |
| `progress` | About every second while files are worked on | `fraction` (0 to 1), `done_bytes`, `total_bytes`, `files_done`, `files_total`, `eta` (seconds left, -1 while unknown) |
| `file` | A file was encrypted, decrypted, or checked | `path` (the file read), `output` (the file written; `""` for verify), `action` (`encrypted`, `decrypted`, `checked`), and when there is one, `note` and its `category` (`cfb_kept`: an old .gfglck file was kept; `verified`) |
| `file` with `--dry-run` | Instead of a run | `path`, `output` (the name it would get; `""` when it can't be known: hidden names, or decrypting), `size`, `dry_run` (true), `action` (`would_encrypt`, `would_decrypt`), `removes_original` |
| `skipped` | A file left as it was on purpose | `path`, `category`, `reason` |
| `error` | A file that failed; it was not changed | `path`, `category`, `message` (plain words with what to do) |
| `done` | Always last | `ok`, `exit_code`, `message`, `total`; after a run also `done`, `failed`, `skipped`, `stopped` (files Ctrl+C or a full drive ended unchanged), `failures` (category to count), `elapsed` (seconds), and the `start` event's options; `dry_run` after a dry run |

### Failure and skip categories

| Category | Meaning |
|---|---|
| `wrong_password` | Wrong password, or the file is damaged. Nothing changed. |
| `in_use` | Another program has the file open. |
| `access_denied` | Windows denied access to the file or its folder. |
| `read_only` | The file is marked read-only. |
| `disk_full` | The drive filled up; the run stops the remaining files. |
| `damaged` | The file is damaged, or gfgLock didn't make it. |
| `newer_version` | A newer gfgLock made the file; update gfgLock. |
| `not_found` | The file was moved or deleted. |
| `changed` | Another program changed the file while it was read. |
| `unsafe_name` | The name stored in the file isn't a safe Windows name. |
| `name_not_restorable` | The file's name couldn't be restored on decrypt; rename it first. |
| `name_too_long` | The encrypted name would be too long; use `--hide-names` or shorten it. |
| `too_large` | The file is too large for the format. |
| `io_error` | Windows couldn't read or write the file. |
| `unknown` | Something else; `--verbose` shows the engine's text. |
| `already_encrypted`, `not_encrypted`, `link`, `hard_link`, `temp_file` | Skipped on purpose. |
| `stopped` | Ctrl+C or a full drive ended the file before it finished; it is unchanged. |

### Example

```json
{"event": "start", "command": "decrypt", "files": 2, "total_bytes": 1048798, "threads": 4, "keep_originals": false, "output_dir": ""}
{"event": "progress", "fraction": 0.5, "done_bytes": 524399, "total_bytes": 1048798, "files_done": 1, "files_total": 2, "eta": 2}
{"event": "file", "path": "D:\\Taxes\\2025.pdf.gfglock", "output": "D:\\Taxes\\2025.pdf", "action": "decrypted"}
{"event": "error", "path": "D:\\Taxes\\notes.txt.gfglock", "category": "wrong_password", "message": "Wrong password, or the file is damaged"}
{"event": "done", "ok": false, "exit_code": 1, "message": "1 of 2 files decrypted. 1 failed: 1 wrong password.", "total": 2, "done": 1, "failed": 1, "skipped": 0, "stopped": 0, "failures": {"wrong_password": 1}, "elapsed": 3.1, "keep_originals": false, "output_dir": ""}
```

## info

One object: `{"files": [...], "ok", "exit_code"}`. Each file has `path`, `size`, `format` (1 or 2), `algorithm` (`aes-256-gcm`, `chacha20-poly1305`, `aes-256-cfb`), `kdf` (`argon2id`, or `pbkdf2-sha256` for format 1), `kdf_iterations`, for format 2 `kdf_memory_mib`, `kdf_lanes`, and `chunk_size`, `authenticated`, and `hidden_name`; or `path`, `error` (a category), and `message`.

## settings

- `list`: `{"file": path, "settings": {"theme": "system", "encryption.cpu_threads": 4, ...}}`
- `get`: `{"key", "value"}`
- `set`: `{"key", "value", "saved", "ok", "exit_code"}`
- `reset`: `{"reset": true, "saved", "ok", "exit_code"}`
- A refused key or value: `{"ok": false, "exit_code": 2, "message"}`

## skill

`{"skill": "gfglock", "installed": [paths], "failed": [{"path", "error"}]}` for install, `removed` and `not_installed` for uninstall, `folders` (`path`, `installed`) for path, and `files` (name to text) for show.
