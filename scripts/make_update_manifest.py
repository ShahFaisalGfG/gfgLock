"""Write update.json, the release description the in-app updater reads (signed by sign_update.py).

Usage:
  python scripts/make_update_manifest.py --app gfgLock --version 3.3.0 --repo OWNER/REPO --out build/update.json
      --package "kind=system;files=build/installer/gfgLock_3.3.0_system_installer.exe"
      --package "kind=portable-exe;files=build/gfgLock_3.3.0_portable.exe"

Each --package names one way to update: its kind (system, user, portable-exe, or patch), its files
(comma-separated; a split installer lists the exe first, then its parts), and for CC-Gen-Ultimate
its edition and runtime_id. Sizes and SHA-256 hashes are computed from the files. The apps choose
their package from this list and never take installer arguments from it.

Shared by gfgLock, gfgShield, and CC-Gen-Ultimate; keep the copies identical.
"""

import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA = 1
KINDS = ("system", "user", "portable-exe", "patch")
_VERSION = re.compile(r"(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})")
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_EDITION = re.compile(r"[a-z0-9_-]{0,32}")
_RUNTIME_ID = re.compile(r"(|[0-9a-f]{64})")
_CHUNK = 1024 * 1024


def file_entry(path: str) -> dict:
    """{name, size, sha256} of one release file."""
    name = os.path.basename(path)
    if not _FILE_NAME.fullmatch(name) or ".." in name:
        raise ValueError(f"{name!r} is not a safe release file name")
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(_CHUNK):
            digest.update(block)
    return {"name": name, "size": os.path.getsize(path), "sha256": digest.hexdigest()}


def parse_package(spec: str) -> dict:
    """One --package value: "kind=...;files=a,b[;edition=...][;runtime_id=...]"."""
    fields = {}
    for part in spec.split(";"):
        key, sep, value = part.partition("=")
        if not sep or key.strip() not in ("kind", "files", "edition", "runtime_id"):
            raise ValueError(f"unknown package field in {spec!r}")
        fields[key.strip()] = value.strip()
    kind = fields.get("kind", "")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    edition, runtime_id = fields.get("edition", ""), fields.get("runtime_id", "")
    if not _EDITION.fullmatch(edition) or not _RUNTIME_ID.fullmatch(runtime_id):
        raise ValueError(f"unusable edition or runtime_id in {spec!r}")
    if kind == "patch" and not runtime_id:
        raise ValueError("a patch package needs the runtime_id it applies to")
    files = [path for path in fields.get("files", "").split(",") if path]
    if not files:
        raise ValueError(f"no files in {spec!r}")
    package = {"kind": kind}
    if edition:
        package["edition"] = edition
    if runtime_id:
        package["runtime_id"] = runtime_id
    package["files"] = [file_entry(path) for path in files]
    return package


def build_manifest(app: str, version: str, repo: str, packages: list[dict]) -> dict:
    if not _VERSION.fullmatch(version):
        raise ValueError(f"{version!r} is not an X.Y.Z version")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"{repo!r} is not OWNER/REPO")
    keys = [(p["kind"], p.get("edition", ""), p.get("runtime_id", "")) for p in packages]
    if len(set(keys)) != len(keys):
        raise ValueError("two packages have the same kind, edition, and runtime_id")
    return {
        "schema": SCHEMA,
        "app": app,
        "version": version,
        "tag": f"v{version}",
        "notes_url": f"https://github.com/{repo}/releases/tag/v{version}",
        "packages": packages,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write the update manifest for a release.")
    parser.add_argument("--app", required=True, help="the app name the apps check (AppInfo.APP_NAME)")
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", required=True, help="OWNER/REPO on GitHub")
    parser.add_argument("--out", required=True)
    parser.add_argument("--package", action="append", required=True, help="kind=...;files=...[;edition=...][;runtime_id=...]")
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.app, args.version, args.repo, [parse_package(spec) for spec in args.package])
    except (OSError, ValueError) as error:
        print(f"Can't write the update manifest: {error}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {args.out} for {args.app} {args.version} ({len(manifest['packages'])} packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
