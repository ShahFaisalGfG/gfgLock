"""gfglock: encrypt, decrypt, and check files with a password from the command line.

The same engine as the gfgLock window, with the same rules: a file is replaced only after its
encrypted (or decrypted) copy is safely written and checked, and nothing is overwritten.

Exit status: 0 when every file was done (or left alone on purpose, such as one already encrypted),
1 when some files failed, 2 when the input, the password, the folders, or the free space can't be
used, 130 when stopped with Ctrl+C (files in progress stay as they were).

With --json, stdout carries only JSON: one object for info, settings, and skill, and one object
per line for encrypt, decrypt, and verify (start, progress, file, skipped, error, warning, and a
closing done with ok and exit_code). `gfglock skill` installs the skill that teaches AI coding
agents to use gfglock.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

from gfglock.config.defaults import AlgorithmDefaults, AppInfo
from gfglock.core import batch, file_ops, passwords, reasons
from gfglock.core.batch import BatchRun, RunListener, RunOptions, RunResult
from gfglock.core.file_ops import OUTCOME_DONE, OUTCOME_FAILED, FileResult
from gfglock.core.format_v2 import FormatError, KeyRing
from gfglock.core.locks import hold_app_mutexes, release_app_mutexes
from gfglock.core.scan import ScanReport, protected_locations, scan_paths
from gfglock.utils import agent_skills, console, paths
from gfglock.utils.helpers import format_bytes, generate_encrypted_name
from gfglock.utils.logging import write_log, write_session_separator
from gfglock.utils.settings import (
    drop_invalid,
    get_default_settings,
    get_settings_file,
    load_settings,
    save_settings,
)

PROG = "gfglock"
EXIT_OK, EXIT_FAILED, EXIT_INVALID, EXIT_STOPPED = 0, 1, 2, 130
# --algorithm names -> the settings codes the app saves.
ALGORITHMS = {"aes-256-gcm": "aes256_gcm", "chacha20-poly1305": "chacha20_poly1305"}
# Seconds between progress lines (people) and progress events (--json).
_PROGRESS_EVERY = {False: 2.0, True: 1.0}
_NO_PASSWORD = ("No password was given. Pass it with --password-stdin, --password-env VAR, or --password-file FILE "
                "(never as an argument).")
_EPILOG = r"""examples:
  gfglock encrypt "D:\Taxes" --password-env GFGLOCK_PASSWORD --json
  gfglock encrypt report.docx --password-stdin --keep-originals   (the password piped in as UTF-8)
  gfglock decrypt "D:\Taxes" --password-file key.txt --output-dir "D:\Opened" --json
  gfglock verify backup.zip.gfglock --password-stdin --json
  gfglock info backup.zip.gfglock --json
  gfglock settings set advanced.encryption_mode chacha20_poly1305

safety:
  A file is replaced only after its encrypted (or decrypted) copy is written and checked, and an
  existing file is never overwritten. --keep-originals leaves the originals in place, and --dry-run
  lists what would change without changing anything. Never put a password on the command line.

agent skill (teaches AI coding agents to use gfglock):
  gfglock skill install           into ~/.agents/skills and ~/.claude/skills
  gfglock skill install --agent cursor
  gfglock skill show              print it, for agents that can't load skills
"""


def positive_int(value: str) -> int:
    """Parse a whole number of 1 or more."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a whole number, 1 or more") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a whole number, 1 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    """The command line's commands and options."""
    parser = argparse.ArgumentParser(prog=PROG, description=AppInfo.APP_DESCRIPTION + ".", epilog=_EPILOG,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"{PROG} {AppInfo.APP_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true",
                        help="print JSON on stdout for scripts and AI agents (see the skill's json-events.md)")
    secret = argparse.ArgumentParser(add_help=False)
    group = secret.add_argument_group("password (never on the command line)")
    source = group.add_mutually_exclusive_group()
    source.add_argument("--password-stdin", action="store_true", help="read the password from the first line of stdin")
    source.add_argument("--password-env", metavar="VAR", help="read the password from an environment variable")
    source.add_argument("--password-file", metavar="FILE", help="read the password from the first line of a file")
    running = argparse.ArgumentParser(add_help=False)
    running.add_argument("--threads", type=positive_int, metavar="N",
                         help="files worked on at once (default: as in Preferences)")
    running.add_argument("-v", "--verbose", action="store_true", help="also print the engine's own messages on stderr")
    results = argparse.ArgumentParser(add_help=False)
    where = results.add_argument_group("where results go (default: as the app's tab was last set)")
    keep = where.add_mutually_exclusive_group()
    keep.add_argument("--keep-originals", dest="keep_originals", action="store_const", const=True,
                      help="leave each file that was read in place")
    keep.add_argument("--replace-originals", dest="keep_originals", action="store_const", const=False,
                      help="remove each file that was read once its new copy is safely saved (the app's default)")
    folder = where.add_mutually_exclusive_group()
    folder.add_argument("--output-dir", metavar="DIR", help="save the results in this folder")
    folder.add_argument("--same-folder", dest="output_dir", action="store_const", const="",
                        help="save each result next to the file it came from (the app's default)")
    results.add_argument("--dry-run", action="store_true", help="list what would change, and change nothing")

    encrypt = commands.add_parser(
        "encrypt", parents=[output, secret, running, results], help="encrypt files and folders",
        description="Encrypt files, and every file in the folders given (subfolders too). System and app "
                    "folders, links, and files already encrypted are left out. Each file is replaced by its "
                    "encrypted copy (report.docx becomes report.docx.gfglock) once the copy is safely written.")
    encrypt.add_argument("paths", nargs="+", metavar="PATH", help="files and folders to encrypt")
    encrypt.add_argument("--algorithm", choices=sorted(ALGORITHMS),
                         help="encryption method (default: as in the app, aes-256-gcm unless changed)")
    names = encrypt.add_mutually_exclusive_group()
    names.add_argument("--hide-names", dest="hide_names", action="store_const", const=True,
                       help="give encrypted files random names; the original ones come back on decrypt")
    names.add_argument("--show-names", dest="hide_names", action="store_const", const=False,
                       help="keep each name visible: report.docx.gfglock (the app's default)")

    decrypt = commands.add_parser(
        "decrypt", parents=[output, secret, running, results], help="decrypt gfgLock files and folders",
        description="Decrypt .gfglock, .gfgcha, and .gfglck files, and every one in the folders given. Each is "
                    "restored under its original name and removed once the restored copy is safely written. "
                    "With a wrong password nothing changes.")
    decrypt.add_argument("paths", nargs="+", metavar="PATH", help="encrypted files and folders")

    verify = commands.add_parser(
        "verify", parents=[output, secret, running], help="check the password and the files, writing nothing",
        description="Check that the password opens each file and that its data is intact, without writing "
                    "anything. The old .gfglck format can only have its stored name checked.")
    verify.add_argument("paths", nargs="+", metavar="PATH", help="encrypted files and folders")

    info = commands.add_parser("info", parents=[output], help="what an encrypted file's header says (no password)",
                               description="Show an encrypted file's format version, method, key derivation "
                                           "cost, and whether its name is hidden. Needs no password.")
    info.add_argument("paths", nargs="+", metavar="FILE", help="encrypted files")

    settings = commands.add_parser("settings", help="the app's preferences",
                                   description="Read and change the preferences the app uses (the same file).")
    actions = settings.add_subparsers(dest="settings_action", required=True, metavar="ACTION")
    actions.add_parser("list", parents=[output], help="every preference and its value")
    get = actions.add_parser("get", parents=[output], help="one preference")
    get.add_argument("key", help="such as advanced.encryption_mode")
    put = actions.add_parser("set", parents=[output], help="change one preference")
    put.add_argument("key", help="such as encryption.cpu_threads")
    put.add_argument("value", help="the new value: true or false, a number, or text")
    actions.add_parser("reset", parents=[output], help="every preference back to its default")

    skill = commands.add_parser("skill", help="the Agent Skill that teaches AI coding agents to use gfglock",
                                description="The Agent Skill that teaches AI coding agents to use gfglock.")
    agent_skills.add_skill_commands(skill, PROG)
    return parser


# ── Output ────────────────────────────────────────────────────────────────────

class Console:
    """Where the command line's words go: lines for people (results on stdout, problems on stderr),
    or with --json one JSON object per line on stdout and nothing else there."""

    def __init__(self, as_json: bool) -> None:
        self.json = as_json

    def emit(self, event: str, **fields: Any) -> None:
        """One JSON event line (non-ASCII escaped, so no console code page can change it)."""
        print(json.dumps({"event": event, **fields}), flush=True)

    def say(self, text: str) -> None:
        """A line for people: stdout without --json, stderr with it."""
        print(text, file=sys.stderr if self.json else sys.stdout, flush=True)

    def warn(self, text: str, **fields: Any) -> None:
        """Something to know that doesn't stop the command."""
        if self.json:
            self.emit("warning", message=text, **fields)
        else:
            print(text, file=sys.stderr, flush=True)

    def done(self, code: int, message: str, **fields: Any) -> int:
        """The command's last word; returns `code`."""
        if self.json:
            self.emit("done", ok=code == EXIT_OK, exit_code=code, message=message, **fields)
        else:
            print(message, file=sys.stdout if code == EXIT_OK else sys.stderr, flush=True)
        return code


class _Reporter(RunListener):
    """Reports a run's files as they end and its progress at most every second or two."""

    def __init__(self, out: Console, mode: str, total_files: int) -> None:
        self._out = out
        self._mode = mode
        self._total_files = total_files
        self._files_done = 0
        self._last = 0.0
        self._lock = threading.Lock()

    def progress(self, done: int, total: int, eta: float) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._last < _PROGRESS_EVERY[self._out.json] or done >= total:
                return
            self._last = now
            files_done = self._files_done
        if self._out.json:
            self._out.emit("progress", fraction=round(done / total, 4) if total else 0.0, done_bytes=done,
                           total_bytes=total, files_done=files_done, files_total=self._total_files,
                           eta=round(eta) if eta >= 0 else -1)
        else:
            left = batch.format_time_left(eta)
            print(f"{done * 100 // max(total, 1)}%  {files_done} of {batch.plural(self._total_files, 'file')}"
                  + (f"  {left}" if left else ""), file=sys.stderr, flush=True)

    def file_result(self, path: str, result: FileResult) -> None:
        with self._lock:
            self._files_done += 1
        report_file(self._out, self._mode, path, result)


def report_file(out: Console, mode: str, path: str, result: FileResult) -> None:
    """One file's result: a file event, a skipped event, or an error event."""
    if result.outcome == OUTCOME_DONE:
        if out.json:
            out.emit("file", path=path, output=result.output, action=batch.DONE_WORDS[mode],
                     **({"note": result.reason, "category": result.category} if result.reason else {}))
        else:
            target = f" -> {result.output}" if result.output else ""
            out.say(f"{batch.DONE_WORDS[mode].capitalize()}: {path}{target}" + (f" ({result.reason})" if result.reason else ""))
    elif result.outcome == OUTCOME_FAILED:
        if out.json:
            out.emit("error", path=path, category=result.category or reasons.UNKNOWN, message=result.reason)
        else:
            print(f"Failed: {path}: {result.reason}", file=sys.stderr, flush=True)
    elif out.json:
        out.emit("skipped", path=path, category=result.category, reason=result.reason)
    else:
        print(f"Skipped: {path}: {result.reason}", file=sys.stderr, flush=True)


# ── Passwords ─────────────────────────────────────────────────────────────────

class InputError(Exception):
    """Input the command can't use; its message says what to do instead (exit status 2)."""


def read_password(args: argparse.Namespace, confirm: bool) -> str:
    """The password from the chosen source, or a prompt on a terminal. Never from the command line."""
    if args.password_stdin:
        # As UTF-8 bytes: a piped stdin is otherwise decoded with the console's code page, which
        # would turn a password with accents or other scripts into a different key.
        stream = getattr(sys.stdin, "buffer", None)
        try:
            line = stream.readline().decode("utf-8-sig") if stream is not None else sys.stdin.readline()
        except UnicodeDecodeError as error:
            raise InputError("The password piped in isn't UTF-8 text.") from error
        password = line.rstrip("\r\n")
        if not password:
            raise InputError("--password-stdin read an empty line. Pipe the password into the command.")
        return password
    if args.password_env:
        password = os.environ.get(args.password_env, "")
        if not password:
            raise InputError(f"The environment variable {args.password_env} is empty or not set.")
        return password
    if args.password_file:
        try:
            with open(args.password_file, encoding="utf-8-sig") as fh:
                password = fh.readline().rstrip("\r\n")
        except (OSError, UnicodeError) as error:
            raise InputError(f"Couldn't read the password file {args.password_file}: "
                             f"{getattr(error, 'strerror', None) or error}.") from error
        if not password:
            raise InputError(f"The password file {args.password_file} starts with an empty line.")
        return password
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        raise InputError(_NO_PASSWORD)
    password = getpass.getpass("Password: ")
    if confirm and getpass.getpass("Type it again: ") != password:
        raise InputError("The two passwords don't match. Nothing was changed.")
    return password


# ── encrypt, decrypt, verify ──────────────────────────────────────────────────

def _options(mode: str, args: argparse.Namespace) -> RunOptions:
    """The run's options: the app's saved choices, with the ones given on the command line in place."""
    output_dir = getattr(args, "output_dir", None)
    return batch.options_from_settings(
        mode, load_settings(),
        algorithm=ALGORITHMS.get(getattr(args, "algorithm", None) or "", ""),
        hide_names=getattr(args, "hide_names", None),
        threads=args.threads,
        keep_originals=getattr(args, "keep_originals", None),
        output_dir=os.path.abspath(output_dir) if output_dir else output_dir,
    )


def _scan_notes(report: ScanReport, mode: str) -> list[tuple[str, str]]:
    """(category, sentence) for what the scan left out."""
    notes = []
    if report.missing:
        notes.append(("not_found", f"{batch.plural(report.missing, 'path')} given {_were(report.missing)} not found."))
    if report.failed_roots:
        notes.append(("access_denied", f"{batch.plural(report.failed_roots, 'folder')} couldn't be opened."))
    if report.unreadable:
        notes.append(("access_denied", f"{batch.plural(report.unreadable, 'folder')} inside couldn't be opened "
                                       f"and {_were(report.unreadable)} skipped."))
    protected = report.protected_folders + report.protected_files
    if protected:
        notes.append(("protected", f"{batch.plural(protected, 'system or app location')} "
                                   f"{_were(protected)} left out; gfglock doesn't encrypt Windows, program, "
                                   "or app folders."))
    if report.other_type:
        notes.append(("already_encrypted" if mode == batch.MODE_ENCRYPT else "not_encrypted",
                      f"{batch.plural(report.other_type, 'file')} "
                      + ("already encrypted" if mode == batch.MODE_ENCRYPT else "not encrypted by gfgLock")
                      + f" {_were(report.other_type)} left out."))
    return notes


def _were(count: int) -> str:
    return "was" if count == 1 else "were"


def _algorithm_name(options: RunOptions) -> str:
    return file_ops.ALGORITHM_LABELS.get(options.algorithm, options.algorithm)


def run_files(mode: str, args: argparse.Namespace, out: Console) -> int:
    """encrypt, decrypt, or verify: scan the paths, check what's needed, and run."""
    console.set_sink((lambda text: print(text, file=sys.stderr, flush=True)) if args.verbose else (lambda _text: None))
    options = _options(mode, args)
    report = ScanReport()
    protected = protected_locations() if mode == batch.MODE_ENCRYPT else None
    roots = [os.path.abspath(path) for path in args.paths]  # results name full paths
    files = list(scan_paths(roots, mode != batch.MODE_ENCRYPT, report, protected))
    for category, note in _scan_notes(report, mode):
        out.warn(note, category=category)
    if not files:
        verb = {"encrypt": "encrypt", "decrypt": "decrypt", "verify": "check"}[mode]
        return out.done(EXIT_INVALID, f"There are no files to {verb} in what was given.", total=0)
    if options.output_dir and not getattr(args, "dry_run", False):
        try:
            os.makedirs(options.output_dir, exist_ok=True)
        except OSError as error:
            return out.done(EXIT_INVALID, f"Couldn't use the folder {options.output_dir} to save into: "
                                          f"{error.strerror or error}. Choose another with --output-dir.")
    shortages = batch.space_shortages(files, options)
    if getattr(args, "dry_run", False):
        return dry_run(mode, files, options, shortages, out)
    if shortages:
        return out.done(EXIT_INVALID, " ".join(shortage.text() for shortage in shortages), total=len(files))

    password = read_password(args, confirm=mode == batch.MODE_ENCRYPT)
    problem = passwords.unusable(password)
    if problem:
        raise InputError(problem)
    if mode == batch.MODE_ENCRYPT and passwords.strength(password) <= 2:
        out.warn("The password is weak. " + passwords.WEAK_HINT, category="weak_password")
    keys = KeyRing(password)

    total_bytes = sum(size for _path, size in files)
    if out.json:
        out.emit("start", command=mode, files=len(files), total_bytes=total_bytes, threads=options.threads,
                 **_where(mode, options))
    else:
        out.say(f"{mode.capitalize()}ing {batch.plural(len(files), 'file')} ({format_bytes(total_bytes, True)})..."
                if mode != batch.MODE_VERIFY else
                f"Checking {batch.plural(len(files), 'file')} ({format_bytes(total_bytes, True)})...")
    write_log(f"[{mode.upper()}] {batch.plural(len(files), 'file')} | command line | "
              f"{_algorithm_name(options) if mode == batch.MODE_ENCRYPT else 'auto-detect'} | "
              f"{batch.plural(options.threads, 'thread')}", "general")
    result = _run(BatchRun([path for path, _size in files], keys, options, _Reporter(out, mode, len(files))))
    summary = batch.summarize(result, "run the command")
    write_log(f"[{mode.upper()}] {summary}", "critical" if result.failed else "general")
    write_session_separator()
    code = EXIT_OK if result.ok else EXIT_FAILED
    if result.cancelled and not result.halt:  # Ctrl+C; a full drive stops a run by itself (status 1)
        code = EXIT_STOPPED
    elif batch.wrong_password_only(result):
        summary += " Run it again with the right password."
    return out.done(code, summary, **_counts(result), **_where(mode, options))


def _run(run: BatchRun) -> RunResult:
    """Run the batch on a thread of its own, so Ctrl+C can stop it the way the app's Cancel does:
    files in progress stop and stay as they were, and no new file starts."""
    holder: list[RunResult] = []
    worker = threading.Thread(target=lambda: holder.append(run.run()), name="gfglock-run", daemon=True)
    hold_app_mutexes()  # the installers wait while a run is going
    try:
        worker.start()
        while worker.is_alive():
            try:
                worker.join(0.2)
            except KeyboardInterrupt:
                run.cancel()
    finally:
        release_app_mutexes()
    return holder[0]


def _counts(result: RunResult) -> dict[str, Any]:
    return {"total": result.total, "done": result.done, "failed": result.failed, "skipped": result.skipped,
            "stopped": result.stopped, "failures": dict(result.failures), "elapsed": round(result.elapsed, 2)}


def _where(mode: str, options: RunOptions) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if mode == batch.MODE_ENCRYPT:
        fields.update(algorithm=_algorithm_name(options), hide_names=options.hide_names)
    if mode != batch.MODE_VERIFY:
        fields.update(keep_originals=options.keep_originals, output_dir=options.output_dir)
    return fields


def dry_run(mode: str, files: list[tuple[str, int]], options: RunOptions, shortages: list, out: Console) -> int:
    """List what a run would do to each file, changing nothing."""
    for path, size in files:
        folder = file_ops.output_folder(path, options.output_dir)
        output = ""  # a hidden name is random, and a decrypted file's name is stored inside it
        if mode == batch.MODE_ENCRYPT and not options.hide_names:
            output = os.path.join(folder, generate_encrypted_name(path, False, file_ops.EXTENSIONS[options.algorithm]))
        if out.json:
            out.emit("file", path=path, output=output, size=size, dry_run=True, action="would_" + mode,
                     removes_original=options.replaces)
        else:
            target = output or ("a randomly named file in " + folder if mode == batch.MODE_ENCRYPT
                                else "its original name in " + folder)
            out.say(f"Would {mode}: {path} -> {target}" + (" (the original is removed)" if options.replaces else ""))
    for shortage in shortages:
        out.warn(shortage.text(), category=reasons.DISK_FULL)
    return out.done(EXIT_OK, f"Dry run: {batch.plural(len(files), 'file')} would be "
                             f"{batch.DONE_WORDS[mode]}. Nothing was changed.", total=len(files), dry_run=True,
                    **_where(mode, options))


# ── info ──────────────────────────────────────────────────────────────────────

def run_info(args: argparse.Namespace, out: Console) -> int:
    """Read each file's plaintext header."""
    rows: list[dict[str, Any]] = []
    for path in args.paths:
        try:
            rows.append(file_ops.describe_file(path))
        except FileNotFoundError:
            rows.append({"path": os.path.abspath(path), "error": "not_found", "message": reasons.text(reasons.NOT_FOUND)})
        except OSError as error:
            category = reasons.categorize(error)
            rows.append({"path": os.path.abspath(path), "error": category, "message": reasons.text(category)})
        except FormatError as error:
            category = reasons.categorize(error)
            category = reasons.NEWER_VERSION if category == reasons.NEWER_VERSION else reasons.NOT_ENCRYPTED
            rows.append({"path": os.path.abspath(path), "error": category, "message": reasons.text(category)})
    failed = [row for row in rows if "error" in row]
    code = EXIT_INVALID if all(row.get("error") == "not_found" for row in failed) and len(failed) == len(rows) \
        else EXIT_FAILED if failed else EXIT_OK
    if out.json:
        print(json.dumps({"files": rows, "ok": code == EXIT_OK, "exit_code": code}), flush=True)
        return code
    for row in rows:
        if "error" in row:
            print(f"{row['path']}: {row['message']}", file=sys.stderr)
        elif row["format"] == 1:
            print(f"{row['path']}: gfgLock 3.1 format, {row['algorithm']}, PBKDF2-SHA256 "
                  f"{row['kdf_iterations']:,} iterations" + (", not authenticated" if not row["authenticated"] else ""))
        else:
            print(f"{row['path']}: gfgLock format {row['format']}, {row['algorithm']}, Argon2id "
                  f"{row['kdf_memory_mib']} MiB x {row['kdf_iterations']} passes x {row['kdf_lanes']} lanes, "
                  f"{'name hidden' if row['hidden_name'] else 'name shown'}")
    return code


# ── settings ──────────────────────────────────────────────────────────────────

def _flatten(settings: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in settings.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, name + "."))
        else:
            flat[name] = value
    return flat


def _parse_value(text: str, default: Any) -> Any:
    """A command-line value as the type of the setting's default."""
    if isinstance(default, bool):
        lowered = text.strip().lower()
        if lowered in ("true", "on", "yes", "1"):
            return True
        if lowered in ("false", "off", "no", "0"):
            return False
        raise InputError("Use true or false.")
    if isinstance(default, int):
        try:
            return int(text)
        except ValueError as error:
            raise InputError("Use a whole number.") from error
    return text


_CHOICES = {
    "theme": "system, light, or dark",
    "advanced.encryption_mode": ", ".join(AlgorithmDefaults.SUPPORTED_ALGORITHMS),
    "advanced.log_level": "critical (errors only) or all",
    "encryption.read_size": "0 (the default, 4 MB), 1048576, 8388608, 16777216, 33554432, or 67108864",
    "decryption.read_size": "0 (the default, 4 MB), 1048576, 8388608, 16777216, 33554432, or 67108864",
    "encryption.cpu_threads": f"1 to {os.cpu_count() or 1}",
    "decryption.cpu_threads": f"1 to {os.cpu_count() or 1}",
    "encryption.output_dir": "a full folder path, or an empty value for next to each file",
    "decryption.output_dir": "a full folder path, or an empty value for next to each file",
}


def run_settings(args: argparse.Namespace, out: Console) -> int:
    """settings list, get, set, and reset: the same file and rules as the app's Preferences."""
    defaults = _flatten(get_default_settings())
    action = args.settings_action
    if action == "list":
        values = _flatten(load_settings())
        if out.json:
            print(json.dumps({"file": get_settings_file(), "settings": values}), flush=True)
        else:
            for key, value in values.items():
                print(f"{key} = {json.dumps(value)}")
        return EXIT_OK
    if action == "reset":
        install = load_settings().get("install", {})
        fresh = get_default_settings()
        fresh["install"] = install  # what the installer was told stays, as the app's Reset keeps it
        return _saved(out, fresh, {"reset": True}, "Every preference is back to its default.")
    key = args.key
    if key not in defaults or key.startswith("install."):
        raise InputError(f"There is no preference called {key}. See `gfglock settings list`.")
    if action == "get":
        value = _flatten(load_settings())[key]
        if out.json:
            print(json.dumps({"key": key, "value": value}), flush=True)
        else:
            print(json.dumps(value) if not isinstance(value, str) else value)
        return EXIT_OK
    value = _parse_value(args.value, defaults[key])
    if key.endswith("output_dir") and value:
        value = os.path.abspath(value)
    section, _, name = key.rpartition(".")
    candidate = {section: {name: value}} if section else {name: value}
    if _flatten(drop_invalid(candidate, get_default_settings())) != {key: value}:
        raise InputError(f"{json.dumps(value)} isn't a value {key} can take. Use {_CHOICES.get(key, 'a value of its type')}.")
    settings = load_settings()
    node = settings
    for part in key.split(".")[:-1]:
        node = node.setdefault(part, {})
    node[name] = value
    return _saved(out, settings, {"key": key, "value": value}, f"{key} = {json.dumps(value)}")


def _saved(out: Console, settings: dict[str, Any], fields: dict[str, Any], text: str) -> int:
    if not save_settings(settings):
        if out.json:
            print(json.dumps({**fields, "saved": False, "ok": False, "exit_code": EXIT_FAILED,
                              "message": f"Couldn't save {get_settings_file()}."}), flush=True)
        else:
            print(f"Couldn't save {get_settings_file()}.", file=sys.stderr)
        return EXIT_FAILED
    if out.json:
        print(json.dumps({**fields, "saved": True, "ok": True, "exit_code": EXIT_OK}), flush=True)
    else:
        print(text)
    return EXIT_OK


# ── Entry point ───────────────────────────────────────────────────────────────

def run(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and carry it out; returns the exit status."""
    args = build_parser().parse_args(argv)
    if args.command == "skill":
        return agent_skills.run_skill_command(args, PROG)
    out = Console(getattr(args, "json", False))
    try:
        if args.command in ("encrypt", "decrypt", "verify"):
            return run_files(args.command, args, out)
        if args.command == "info":
            return run_info(args, out)
        return run_settings(args, out)
    except InputError as error:
        if args.command in ("encrypt", "decrypt", "verify"):
            return out.done(EXIT_INVALID, str(error))
        if out.json:
            print(json.dumps({"ok": False, "exit_code": EXIT_INVALID, "message": str(error)}), flush=True)
        else:
            print(str(error), file=sys.stderr)
        return EXIT_INVALID


def console_safe() -> None:
    """Let any file name print: characters the console's code page lacks become "?" instead of an error."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    """gfglock's entry point: the same settings and logs as the app, Ctrl+C as a clean stop."""
    if getattr(sys, "frozen", False):
        paths.use_app_folder(1)  # bin\gfglock.exe sits one folder below gfgLock.exe
    console_safe()
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        out = Console("--json" in args)
        return out.done(EXIT_STOPPED, "Stopped. Nothing was changed.")


if __name__ == "__main__":
    raise SystemExit(main())
