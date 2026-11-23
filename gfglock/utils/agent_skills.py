# agent_skills.py - install a command line's Agent Skill where AI coding agents look for skills
#
# The skill (skills/<tool>/SKILL.md and its references, in the open Agent Skills format) teaches any
# coding agent to use the command line. It ships inside the command line, and `<tool> skill install`
# copies it into the folders agents read. The same file is in each gfgRoyal app (gfgmd, gfglock,
# ccgen, gfgshield), with only the standard library; keep the copies identical.

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SKILL_FILE = "SKILL.md"
# Skills folders in the user's home, by the names --agent takes. Without --agent the skill goes to
# "agents" (~/.agents/skills: Codex, Cline, Warp, and others) and "claude" (~/.claude/skills: Claude
# Code); Cursor reads both. The rest follow the open `skills` installer's list of agents.
AGENT_FOLDERS: dict[str, str] = {
    "agents": ".agents/skills",
    "amp": ".config/agents/skills",
    "augment": ".augment/skills",
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "continue": ".continue/skills",
    "copilot": ".copilot/skills",
    "cursor": ".cursor/skills",
    "droid": ".factory/skills",
    "gemini": ".gemini/skills",
    "goose": ".config/goose/skills",
    "junie": ".junie/skills",
    "kilo": ".kilocode/skills",
    "kiro": ".kiro/skills",
    "opencode": ".config/opencode/skills",
    "openhands": ".openhands/skills",
    "qwen": ".qwen/skills",
    "roo": ".roo/skills",
    "trae": ".trae/skills",
    "windsurf": ".codeium/windsurf/skills",
}
DEFAULT_AGENTS = ("agents", "claude")
EXIT_OK, EXIT_FAILED, EXIT_INVALID = 0, 1, 2


class SkillError(Exception):
    """A skills folder that can't take the skill, or a skill that isn't there."""


def skill_source(tool: str) -> Path:
    """The tool's own skill: inside the built command line, or the repository's skills folder."""
    bundle = getattr(sys, "_MEIPASS", None)
    base = Path(bundle) if bundle else Path(__file__).resolve().parents[2]
    return base / "skills" / tool


def skill_files(source: Path) -> list[Path]:
    """The skill's files relative to its folder: SKILL.md first, then its references by name."""
    if not (source / SKILL_FILE).is_file():
        raise SkillError(f"The skill isn't in {source}; reinstall the app.")
    others = sorted(path.relative_to(source) for path in source.rglob("*")
                    if path.is_file() and path.name != SKILL_FILE)
    return [Path(SKILL_FILE), *others]


def skill_name(skill_md: Path) -> str:
    """The `name` in a SKILL.md's frontmatter, or "" when it has none."""
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        if key.strip() == "name":
            return value.strip().strip("\"'")
    return ""


def target_folders(agents: Sequence[str] = (), dirs: Sequence[Path] = ()) -> list[Path]:
    """The skills folders to use: the named agents' and the given folders, or the shared two."""
    names = list(agents) if agents or dirs else list(DEFAULT_AGENTS)
    folders = [Path.home() / AGENT_FOLDERS[name] for name in names]
    folders += [Path(folder).expanduser() for folder in dirs]
    unique: list[Path] = []
    for folder in folders:
        if all(os.path.normcase(folder.absolute()) != os.path.normcase(seen.absolute()) for seen in unique):
            unique.append(folder)
    return unique


def _is_link(path: Path) -> bool:
    """True for a symbolic link or a Windows junction (Python 3.11 has no Path.is_junction); other
    reparse points, such as OneDrive's placeholders, are ordinary folders."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    tag = getattr(info, "st_reparse_tag", 0)
    return stat.S_ISLNK(info.st_mode) or tag in (stat.IO_REPARSE_TAG_SYMLINK, stat.IO_REPARSE_TAG_MOUNT_POINT)


def _check_ours(target: Path, name: str) -> None:
    """Refuse to touch a folder that holds anything but this skill (or nothing)."""
    if not target.exists() and not _is_link(target):
        return
    if target.is_dir() and (skill_name(target / SKILL_FILE) == name or not any(target.iterdir())):
        return
    raise SkillError(f"{target} holds something other than the {name} skill, so it was left alone.")


def _remove(target: Path) -> None:
    """Remove an installed copy: only the link when it is one (the `skills` installer links)."""
    if _is_link(target):
        try:
            os.unlink(target)
        except OSError:
            os.rmdir(target)  # a link to a folder on Windows
        return
    for path in target.rglob("*"):
        if path.is_file() and not path.is_symlink():
            os.chmod(path, path.stat().st_mode | stat.S_IWRITE)  # a read-only file left by a copy
    shutil.rmtree(target)


def install(source: Path, folder: Path) -> Path:
    """Copy the skill into `folder`, replacing an earlier copy of it; returns the skill's new folder."""
    skill_files(source)
    target = folder / source.name
    _check_ours(target, source.name)
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob(f".{source.name}-*"):  # an install that was cut off, which agents could load
        if stale.is_dir() and not _is_link(stale):
            shutil.rmtree(stale, ignore_errors=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{source.name}-", dir=folder))
    try:
        fresh = staging / source.name
        shutil.copytree(source, fresh, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if target.exists() or _is_link(target):
            _remove(target)
        os.replace(fresh, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


def uninstall(name: str, folder: Path) -> bool:
    """Remove the skill from `folder`; False when it wasn't there."""
    target = folder / name
    if not target.exists() and not _is_link(target):
        return False
    _check_ours(target, name)
    _remove(target)
    return True


def show(source: Path) -> dict[str, str]:
    """The skill's files and their text, SKILL.md first."""
    return {path.as_posix(): (source / path).read_text(encoding="utf-8") for path in skill_files(source)}


def add_skill_commands(parser: argparse.ArgumentParser, tool: str) -> None:
    """Give a `skill` parser its actions: install, uninstall, show, and path."""
    actions = parser.add_subparsers(dest="skill_action", required=True, metavar="ACTION")
    folders = (f"agents' skills folders (default: {', '.join(DEFAULT_AGENTS)}, which Codex, Claude Code, "
               "Cursor, Cline, and others read)")
    for name, text in (("install", f"copy the {tool} skill into {folders}"),
                       ("uninstall", f"remove the {tool} skill from {folders}"),
                       ("path", f"list the folders the {tool} skill goes in, and whether it is there")):
        action = actions.add_parser(name, help=text, description=text[0].upper() + text[1:] + ".")
        action.add_argument("--agent", action="append", default=[], choices=sorted(AGENT_FOLDERS),
                            metavar="AGENT", help=f"an agent's own folder: {', '.join(sorted(AGENT_FOLDERS))}")
        action.add_argument("--dir", action="append", default=[], type=Path, metavar="FOLDER",
                            help=f"a skills folder of your own (the skill goes in FOLDER\\{tool})")
        action.add_argument("--json", action="store_true", help="print the result as JSON")
    shown = actions.add_parser("show", help="print the skill and its references, for agents without skill support",
                               description="Print the skill and its references, to paste into an agent's "
                                           "instructions (AGENTS.md, rules) when it can't load skills.")
    shown.add_argument("--json", action="store_true", help="print the files as one JSON object")


def run_skill_command(args: argparse.Namespace, tool: str, source: Path | None = None) -> int:
    """Carry out a parsed `skill` command; returns the exit status."""
    source = source or skill_source(tool)
    try:
        if args.skill_action == "show":
            return _show(source, tool, args.json)
        folders = target_folders(args.agent, args.dir)
        if args.skill_action == "path":
            return _paths(tool, folders, args.json)
        if args.skill_action == "install":
            skill_files(source)
        return _change(source, tool, folders, args.skill_action == "install", args.json)
    except SkillError as exc:
        print(json.dumps({"skill": tool, "error": str(exc)}) if args.json else str(exc),
              file=sys.stdout if args.json else sys.stderr)
        return EXIT_INVALID


def _show(source: Path, tool: str, as_json: bool) -> int:
    files = show(source)
    if as_json:
        print(json.dumps({"skill": tool, "files": files}))
        return EXIT_OK
    parts = [files.pop(SKILL_FILE).rstrip()]
    parts += [f"<!-- {path} -->\n\n{text.rstrip()}" for path, text in files.items()]
    print("\n\n---\n\n".join(parts))
    return EXIT_OK


def _paths(tool: str, folders: list[Path], as_json: bool) -> int:
    rows = [{"path": str(folder / tool), "installed": skill_name(folder / tool / SKILL_FILE) == tool}
            for folder in folders]
    if as_json:
        print(json.dumps({"skill": tool, "folders": rows}))
    else:
        for row in rows:
            print(f"{row['path']}  ({'installed' if row['installed'] else 'not installed'})")
    return EXIT_OK


def _change(source: Path, tool: str, folders: list[Path], adding: bool, as_json: bool) -> int:
    done: list[str] = []
    absent: list[str] = []
    failed: list[dict[str, str]] = []
    for folder in folders:
        try:
            if adding:
                done.append(str(install(source, folder)))
            elif uninstall(tool, folder):
                done.append(str(folder / tool))
            else:
                absent.append(str(folder / tool))
        except (SkillError, OSError) as exc:
            failed.append({"path": str(folder / tool), "error": str(exc)})
    if as_json:
        key = "installed" if adding else "removed"
        report: dict[str, Any] = {"skill": tool, key: done, "failed": failed}
        if not adding:
            report["not_installed"] = absent
        print(json.dumps(report))
    else:
        verb = "Installed" if adding else "Removed"
        for path in done:
            print(f"{verb} the {tool} skill: {path}")
        for path in absent:
            print(f"Not installed: {path}")
        for failure in failed:
            print(f"Couldn't change {failure['path']}: {failure['error']}", file=sys.stderr)
    return EXIT_FAILED if failed else EXIT_OK
