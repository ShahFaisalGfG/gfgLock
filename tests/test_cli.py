"""The gfglock command line: every password source, JSON events, exit codes, settings, and the skill."""

import argparse
import io
import json
import os
import re
import shlex
import sys
from pathlib import Path

import pytest

from gfglock import cli
from gfglock.core import batch, file_ops, scan
from gfglock.core.format_v2 import KeyRing
from gfglock.utils import console, settings

from .conftest import FAST_KDF

PASSWORD = "Tr0ub4dor & 3 horses"
SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "gfglock"


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    """A cheap key derivation, nothing left out as protected (pytest's temp folders sit in AppData),
    and the engine's echo back on stdout after each test."""
    monkeypatch.setattr(cli, "KeyRing", lambda password: KeyRing(password, FAST_KDF))
    monkeypatch.setattr(cli, "protected_locations", frozenset)
    monkeypatch.setattr(cli, "hold_app_mutexes", lambda: None)
    monkeypatch.setattr(cli, "release_app_mutexes", lambda: None)
    yield
    console.set_sink(None)


class _Stdin(io.TextIOWrapper):
    """A piped stdin: not a terminal."""

    def isatty(self) -> bool:
        return False


def _stdin(monkeypatch, text: str = "") -> None:
    monkeypatch.setattr(sys, "stdin", _Stdin(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))


def _events(out: str) -> list[dict]:
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _files(folder: Path, *names: str) -> list[Path]:
    paths = []
    for name in names:
        path = folder / name
        path.write_bytes(name.encode("utf-8") * 50)
        paths.append(path)
    return paths


def run(monkeypatch, capsys, argv: list[str], stdin: str = "") -> tuple[int, list[dict], str]:
    """Run the command line with a piped stdin; returns (exit status, JSON events, stderr)."""
    _stdin(monkeypatch, stdin)
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, _events(captured.out) if "--json" in argv else [], captured.err


class TestRoundTrips:
    """Encrypt and decrypt through each password source, the files coming back byte for byte."""

    def test_password_from_stdin(self, monkeypatch, capsys, tmp_path):
        a, b = _files(tmp_path, "a.txt", "b.txt")
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(tmp_path), "--password-stdin", "--show-names",
                                                    "--json"], PASSWORD + "\r\n")
        assert code == 0
        assert [event["event"] for event in events][0] == "start" and events[-1]["event"] == "done"
        files = {event["path"]: event["output"] for event in events if event["event"] == "file"}
        assert files == {str(a): str(a) + ".gfglock", str(b): str(b) + ".gfglock"}
        assert events[-1] == {**events[-1], "ok": True, "exit_code": 0, "done": 2, "failed": 0}
        assert sorted(os.listdir(tmp_path)) == ["a.txt.gfglock", "b.txt.gfglock"]

        code, events, _ = run(monkeypatch, capsys, ["decrypt", str(tmp_path), "--password-stdin", "--json"],
                              PASSWORD + "\n")
        assert code == 0 and events[-1]["done"] == 2
        assert a.read_bytes() == b"a.txt" * 50 and b.read_bytes() == b"b.txt" * 50

    def test_password_from_an_environment_variable(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "notes.md")
        monkeypatch.setenv("GFGLOCK_TEST_PASSWORD", PASSWORD)
        assert run(monkeypatch, capsys, ["encrypt", str(source), "--password-env", "GFGLOCK_TEST_PASSWORD",
                                         "--show-names"])[0] == 0
        assert run(monkeypatch, capsys, ["decrypt", str(source) + ".gfglock", "--password-env",
                                         "GFGLOCK_TEST_PASSWORD"])[0] == 0
        assert source.read_bytes() == b"notes.md" * 50

    def test_password_from_a_file(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "photo.jpg")
        key = tmp_path.parent / f"{tmp_path.name}-key.txt"
        key.write_text(PASSWORD + "\n", encoding="utf-8-sig")
        assert run(monkeypatch, capsys, ["encrypt", str(source), "--password-file", str(key), "--show-names"])[0] == 0
        code, _, _ = run(monkeypatch, capsys, ["verify", str(source) + ".gfglock", "--password-file", str(key)])
        assert code == 0
        assert run(monkeypatch, capsys, ["decrypt", str(source) + ".gfglock", "--password-file", str(key)])[0] == 0
        assert source.read_bytes() == b"photo.jpg" * 50

    def test_a_non_ascii_password_from_stdin_is_read_as_utf8(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        password = "پاس ورڈ Ünïcødé"
        assert run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--show-names"], password)[0] == 0
        assert file_ops.decrypt_file(str(source) + ".gfglock", KeyRing(password, FAST_KDF)).outcome == "done"

    def test_keep_originals_and_an_output_folder(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "keep.txt")
        out = tmp_path.parent / f"{tmp_path.name}-out"
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--keep-originals",
                                                    "--output-dir", str(out), "--show-names", "--json"], PASSWORD)
        assert code == 0 and source.exists()
        assert (out / "keep.txt.gfglock").exists()
        assert events[-1]["keep_originals"] is True and events[-1]["output_dir"] == str(out)


class TestRefusals:
    def test_no_password_source_without_a_terminal(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(source), "--json"])
        assert code == 2 and events[-1]["exit_code"] == 2 and "--password-stdin" in events[-1]["message"]
        assert source.exists() and not (tmp_path / "a.txt.gfglock").exists()

    def test_an_empty_password(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        monkeypatch.setenv("GFGLOCK_EMPTY", "")
        assert run(monkeypatch, capsys, ["encrypt", str(source), "--password-env", "GFGLOCK_EMPTY"])[0] == 2
        assert run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin"], "\n")[0] == 2

    def test_a_password_on_the_command_line_isnt_an_option(self, monkeypatch, capsys, tmp_path):
        with pytest.raises(SystemExit) as stop:
            cli.main(["encrypt", str(tmp_path), "--password", PASSWORD])
        assert stop.value.code == 2

    def test_protected_locations_are_left_out(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "system.ini")
        monkeypatch.setattr(cli, "protected_locations", lambda: frozenset({scan._key(str(tmp_path))}))
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(tmp_path), "--password-stdin", "--json"], PASSWORD)
        assert code == 2
        assert any(event["event"] == "warning" and event["category"] == "protected" for event in events)
        assert source.exists()

    def test_files_of_the_other_kind_are_left_out(self, monkeypatch, capsys, tmp_path):
        (plain,) = _files(tmp_path, "plain.txt")
        code, events, _ = run(monkeypatch, capsys, ["decrypt", str(plain), "--password-stdin", "--json"], PASSWORD)
        assert code == 2 and events[0] == {"event": "warning", "message": "1 file not encrypted by gfgLock was left out.",
                                           "category": "not_encrypted"}

    def test_a_drive_without_room(self, monkeypatch, capsys, tmp_path):
        _files(tmp_path, "big.bin")
        monkeypatch.setattr(batch, "_free_space", lambda _folder: 0)
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(tmp_path), "--password-stdin", "--json"], PASSWORD)
        assert code == 2 and "Free up" in events[-1]["message"]

    def test_unknown_options_exit_2(self, capsys):
        with pytest.raises(SystemExit) as stop:
            cli.main(["encrypt"])
        assert stop.value.code == 2


class TestResults:
    def test_a_wrong_password_fails_with_status_1_and_changes_nothing(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--show-names"], PASSWORD)
        locked = tmp_path / "a.txt.gfglock"
        before = locked.read_bytes()
        code, events, _ = run(monkeypatch, capsys, ["decrypt", str(locked), "--password-stdin", "--json"], "nope")
        assert code == 1
        errors = [event for event in events if event["event"] == "error"]
        assert errors == [{"event": "error", "path": str(locked), "category": "wrong_password",
                           "message": "Wrong password, or the file is damaged"}]
        assert events[-1]["failures"] == {"wrong_password": 1} and events[-1]["ok"] is False
        assert events[-1]["message"].startswith("Wrong password. Nothing was changed.")
        assert locked.read_bytes() == before and not source.exists()

    def test_verify_writes_nothing(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--show-names"], PASSWORD)
        code, events, _ = run(monkeypatch, capsys, ["verify", str(tmp_path), "--password-stdin", "--json"], PASSWORD)
        assert code == 0 and os.listdir(tmp_path) == ["a.txt.gfglock"]
        assert [event["action"] for event in events if event["event"] == "file"] == ["checked"]

    def test_dry_run_lists_and_changes_nothing(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(source), "--dry-run", "--show-names", "--json"])
        assert code == 0 and os.listdir(tmp_path) == ["a.txt"]
        assert events[0] == {"event": "file", "path": str(source), "output": str(source) + ".gfglock",
                             "size": 250, "dry_run": True, "action": "would_encrypt", "removes_original": True}
        assert events[-1]["dry_run"] is True

    def test_already_encrypted_files_are_skipped_inside_a_folder_run(self, monkeypatch, capsys, tmp_path):
        """A file left as it was on purpose doesn't fail the run."""
        _files(tmp_path, "a.txt")
        monkeypatch.setattr(file_ops, "encrypt_file", lambda path, *a, **k: file_ops._skip(path, "hard_link"))
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(tmp_path), "--password-stdin", "--json"], PASSWORD)
        assert code == 0 and events[-1]["skipped"] == 1
        assert [event["category"] for event in events if event["event"] == "skipped"] == ["hard_link"]

    def test_human_output(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        code, _, err = run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--show-names"], PASSWORD)
        assert code == 0 and err == ""

    def test_the_engines_echo_never_reaches_stdout(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        _code, events, _ = run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--json"], PASSWORD)
        assert all("event" in event for event in events)  # every stdout line is a JSON event

    def test_ctrl_c_stops_with_130(self, monkeypatch, capsys, tmp_path):
        _files(tmp_path, "a.txt")

        def interrupted(run_):
            run_.cancel()
            return batch.RunResult("encrypt", 1, cancelled=True)

        monkeypatch.setattr(cli, "_run", interrupted)
        code, events, _ = run(monkeypatch, capsys, ["encrypt", str(tmp_path), "--password-stdin", "--json"], PASSWORD)
        assert code == 130 and events[-1]["exit_code"] == 130 and "not changed" in events[-1]["message"]


class TestInfo:
    def test_reads_the_header_without_a_password(self, monkeypatch, capsys, tmp_path):
        (source,) = _files(tmp_path, "a.txt")
        run(monkeypatch, capsys, ["encrypt", str(source), "--password-stdin", "--show-names"], PASSWORD)
        assert cli.main(["info", str(source) + ".gfglock", str(tmp_path / "gone.gfglock"), "--json"]) == 1
        report = json.loads(capsys.readouterr().out)
        good, missing = report["files"]
        assert (good["format"], good["algorithm"], good["kdf"], good["hidden_name"]) == (2, "aes-256-gcm", "argon2id", False)
        assert missing["error"] == "not_found" and report["exit_code"] == 1

    def test_only_missing_files_is_status_2(self, capsys, tmp_path):
        assert cli.main(["info", str(tmp_path / "gone.gfglock")]) == 2


class TestSettings:
    @pytest.fixture(autouse=True)
    def own_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "get_settings_file", lambda: str(tmp_path / "settings.json"))

    def _json(self, capsys, *argv: str) -> dict:
        assert cli.main(["settings", *argv, "--json"]) in (0, 1, 2)
        return json.loads(capsys.readouterr().out)

    def test_list_get_set_reset(self, capsys, tmp_path):
        assert self._json(capsys, "list")["settings"]["theme"] == "system"
        assert self._json(capsys, "set", "theme", "dark") == {"key": "theme", "value": "dark", "saved": True,
                                                               "ok": True, "exit_code": 0}
        assert self._json(capsys, "get", "theme") == {"key": "theme", "value": "dark"}
        assert self._json(capsys, "set", "encryption.keep_originals", "on")["value"] is True
        assert self._json(capsys, "set", "decryption.output_dir", str(tmp_path))["value"] == str(tmp_path)
        assert self._json(capsys, "reset")["reset"] is True
        assert self._json(capsys, "get", "theme")["value"] == "system"

    @pytest.mark.parametrize("key,value", [("theme", "purple"), ("encryption.cpu_threads", "abc"),
                                           ("encryption.cpu_threads", "100000"), ("nope", "1"),
                                           ("install.connections", "UpdateChecks=0"),
                                           ("advanced.encryption_mode", "aes256_cfb")])
    def test_values_the_app_couldnt_use_are_refused(self, capsys, key, value):
        report = self._json(capsys, "set", key, value)
        assert report["exit_code"] == 2 and report["ok"] is False

    def test_reset_keeps_the_installers_choice(self, capsys):
        settings.save_settings({**settings.get_default_settings(), "install": {"connections": "UpdateChecks=0"}})
        self._json(capsys, "reset")
        assert settings.load_settings()["install"]["connections"] == "UpdateChecks=0"


class TestSkill:
    def test_install_show_and_path(self, capsys, tmp_path):
        assert cli.main(["skill", "install", "--dir", str(tmp_path), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["installed"] == [str(tmp_path / "gfglock")]
        assert (tmp_path / "gfglock" / "SKILL.md").is_file()
        assert (tmp_path / "gfglock" / "references" / "commands.md").is_file()
        assert cli.main(["skill", "show", "--json"]) == 0
        assert list(json.loads(capsys.readouterr().out)["files"])[0] == "SKILL.md"
        assert cli.main(["skill", "path", "--dir", str(tmp_path)]) == 0
        assert "(installed)" in capsys.readouterr().out

    def test_the_skill_follows_the_agent_skills_format(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        fields = dict(line.split(":", 1) for line in front.splitlines() if re.match(r"^[a-z]+:", line))
        assert cli.agent_skills.skill_name(SKILL_DIR / "SKILL.md") == "gfglock" == SKILL_DIR.name
        assert 0 < len(fields["description"].strip()) <= 1024 and len(fields["compatibility"].strip()) <= 500


def skill_command_lines() -> list[list[str]]:
    """Every gfglock command in the skill's PowerShell blocks, split as a shell would."""
    lines = []
    for doc in sorted(SKILL_DIR.rglob("*.md")):
        for block in re.findall(r"```powershell\n(.*?)```", doc.read_text(encoding="utf-8"), re.DOTALL):
            for line in block.splitlines():
                command = line.split("|")[-1].strip()  # a password piped in: the command is last
                if command.startswith("gfglock "):
                    lines.append([part.strip('"') for part in shlex.split(command, posix=False)])
    return lines


def test_every_command_in_the_skill_parses():
    """The skill can't drift from the tool: each command it shows is accepted by gfglock's own parser."""
    commands = skill_command_lines()
    assert len(commands) >= 15
    parser = cli.build_parser()
    for argv in commands:
        try:
            parser.parse_args(argv[1:])
        except SystemExit as stop:
            if stop.code != 0:  # --help and --version exit 0
                raise AssertionError(f"the skill shows a command gfglock refuses: {' '.join(argv)}") from None


def test_the_skill_documents_every_option_and_no_others():
    """Each option of gfglock is in the command reference, and every option the skill names exists."""
    reference = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    options: set[str] = set()
    stack = [cli.build_parser()]
    while stack:
        parser = stack.pop()
        for action in parser._actions:
            options.update(flag for flag in action.option_strings if flag.startswith("--"))
            if isinstance(action, argparse._SubParsersAction):
                stack.extend(action.choices.values())
    named = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", "".join(
        doc.read_text(encoding="utf-8") for doc in SKILL_DIR.rglob("*.md"))))
    assert options <= set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", reference))
    assert named <= options


def test_the_skill_version_is_the_apps():
    """The skill ships inside the command line, so its version is the app's."""
    front = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
    assert f'version: "{cli.AppInfo.APP_VERSION}"' in front
