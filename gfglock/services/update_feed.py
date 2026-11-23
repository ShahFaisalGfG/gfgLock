# update_feed.py - finds a newer release: fetches and checks the signed update manifest (stdlib only)
#
# Shared by gfgLock, gfgShield, and CC-Gen-Ultimate: keep the copies identical apart from the
# package name in the imports. Each release publishes update.json and update.json.sig
# (scripts/make_update_manifest.py, scripts/sign_update.py). The app fetches them from the fixed
# "latest release" address, which GitHub serves without the API's hourly request limit, and trusts
# nothing in them until the signature checks out against a key built into the app.

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from gfglock.utils import signature

SCHEMA = 1
MANIFEST_NAME = "update.json"
SIGNATURE_NAME = "update.json.sig"
CHECK_TIMEOUT_S = 10
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_SIGNATURE_BYTES = 1024
_VERSION = re.compile(r"(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})")
# A release file name: letters, digits, and . _ - only, so it can't name another folder.
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KINDS = frozenset({"system", "user", "portable-exe", "patch"})
_EDITION = re.compile(r"[a-z0-9_-]{0,32}")


class FeedError(Exception):
    """The update information could not be fetched or trusted; the message suits a log line."""


class FeedUnreachable(FeedError):
    """The update information couldn't be downloaded: no connection, a server error, or a refused address."""


@dataclass(frozen=True)
class UpdateSource:
    """Where an app looks for updates and how it proves them genuine.

    base_url is the repository page (https://github.com/<owner>/<repo>); a local staging build can
    point it at http://127.0.0.1:<port> with its own test key (see allow_local_http).
    """

    app: str
    version: str
    base_url: str
    public_keys: tuple[str, ...]
    allow_local_http: bool = False

    @property
    def manifest_url(self) -> str:
        return f"{self.base_url}/releases/latest/download/{MANIFEST_NAME}"

    @property
    def releases_url(self) -> str:
        """The latest release's page, for builds that can't update themselves."""
        return f"{self.base_url}/releases/latest"

    def file_url(self, tag: str, name: str) -> str:
        return f"{self.base_url}/releases/download/{tag}/{name}"

    @property
    def user_agent(self) -> str:
        return f"{self.app}/{self.version}"


@dataclass(frozen=True)
class UpdateFile:
    """One file of a release, with the size and SHA-256 it must have."""

    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class UpdatePackage:
    """What one kind of install downloads: an installer (perhaps split into parts) or a portable exe."""

    kind: str
    edition: str
    runtime_id: str
    files: tuple[UpdateFile, ...]

    @property
    def size(self) -> int:
        return sum(item.size for item in self.files)


@dataclass(frozen=True)
class Release:
    """A signed update manifest, with the bytes it was verified from so they can be checked again."""

    app: str
    version: str
    tag: str
    notes_url: str
    packages: tuple[UpdatePackage, ...]
    manifest: bytes = field(default=b"", repr=False, compare=False)
    signature: bytes = field(default=b"", repr=False, compare=False)


def parse_version(text: str) -> tuple[int, int, int]:
    """(major, minor, patch) of "X.Y.Z"; anything else raises ValueError."""
    match = _VERSION.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"not a version: {text!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def is_newer(candidate: str, current: str) -> bool:
    """True when version `candidate` comes after `current`."""
    return parse_version(candidate) > parse_version(current)


def open_url(source: UpdateSource, url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    """Open `url` over HTTPS (or local HTTP for a staging build), refusing redirects to anything else."""
    _check_url(source, url)
    request = urllib.request.Request(url, headers={"User-Agent": source.user_agent, **(headers or {})})
    opener = urllib.request.build_opener(_SafeRedirects(source))
    return opener.open(request, timeout=timeout)


def fetch_release(source: UpdateSource, opener: Callable[..., Any] = open_url) -> Release | None:
    """The newest signed release, or None when the repository publishes no update information.

    Raises FeedError when the manifest or its signature can't be fetched, doesn't verify, or
    doesn't describe this app.
    """
    data = _read(source, source.manifest_url, _MAX_MANIFEST_BYTES, opener, missing_ok=True)
    if data is None:
        return None
    sig = _read(source, f"{source.manifest_url}.sig", _MAX_SIGNATURE_BYTES, opener)
    return verify_release(source, data, sig or b"")


def verify_release(source: UpdateSource, data: bytes, sig: bytes) -> Release:
    """The release in `data` once `sig` proves the publisher signed it; raises FeedError otherwise."""
    if not sig or not source.public_keys:
        raise FeedError("the update can't be verified: no signature or no signing key")
    try:
        trusted = signature.verify(data, sig, source.public_keys)
    except signature.SignatureError as error:
        raise FeedError(f"the update signature can't be checked: {error}") from error
    if not trusted:
        raise FeedError("the update information is not signed by the publisher")
    release = parse_manifest(data, source.app)
    return Release(release.app, release.version, release.tag, release.notes_url, release.packages, data, sig)


def save_release(release: Release, folder: str) -> None:
    """Keep the signed manifest beside a download, so the install step can verify it again offline."""
    os.makedirs(folder, exist_ok=True)
    for name, data in ((MANIFEST_NAME, release.manifest), (SIGNATURE_NAME, release.signature)):
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(data)


def load_release(source: UpdateSource, folder: str) -> Release:
    """The release saved by save_release, verified again; raises FeedError when missing or untrusted."""
    try:
        with open(os.path.join(folder, MANIFEST_NAME), "rb") as fh:
            data = fh.read(_MAX_MANIFEST_BYTES + 1)
        with open(os.path.join(folder, SIGNATURE_NAME), "rb") as fh:
            sig = fh.read(_MAX_SIGNATURE_BYTES + 1)
    except OSError as error:
        raise FeedError(f"the saved update information can't be read: {error.strerror or error}") from error
    if len(data) > _MAX_MANIFEST_BYTES or len(sig) > _MAX_SIGNATURE_BYTES:
        raise FeedError("the saved update information is too large")
    return verify_release(source, data, sig)


def parse_manifest(data: bytes, app: str) -> Release:
    """Validate a verified update.json; anything unexpected raises FeedError."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise FeedError(f"the update information is not valid JSON: {error}") from error
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise FeedError("the update information has an unknown format")
    if raw.get("app") != app:
        raise FeedError(f"the update information is for {raw.get('app')!r}, not {app}")
    version = _text(raw, "version")
    try:
        parse_version(version)
    except ValueError as error:
        raise FeedError(str(error)) from error
    tag = _text(raw, "tag")
    if tag != f"v{version}":
        raise FeedError(f"the release tag {tag!r} doesn't match version {version}")
    notes_url = _text(raw, "notes_url")
    if not notes_url.startswith("https://"):
        raise FeedError("the release notes address is not https")
    packages = raw.get("packages")
    if not isinstance(packages, list):
        raise FeedError("the update information lists no packages")
    return Release(app, version, tag, notes_url, tuple(_package(item) for item in packages))


def pick_package(release: Release, kind: str, edition: str = "", runtime_id: str = "") -> UpdatePackage | None:
    """The package for this install: its kind and edition, or for "patch" also the same runtime."""
    for package in release.packages:
        if package.kind != kind or package.edition != edition:
            continue
        if kind == "patch" and (not runtime_id or package.runtime_id != runtime_id):
            continue
        return package
    return None


def _package(raw: Any) -> UpdatePackage:
    if not isinstance(raw, dict):
        raise FeedError("a package entry is not an object")
    kind = _text(raw, "kind")
    if kind not in _KINDS:
        raise FeedError(f"unknown package kind {kind!r}")
    edition = raw.get("edition", "")
    runtime_id = raw.get("runtime_id", "")
    if not isinstance(edition, str) or not _EDITION.fullmatch(edition):
        raise FeedError(f"unusable edition {edition!r}")
    if not isinstance(runtime_id, str) or (runtime_id and not _SHA256.fullmatch(runtime_id)):
        raise FeedError(f"unusable runtime id {runtime_id!r}")
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        raise FeedError(f"the {kind} package lists no files")
    return UpdatePackage(kind, edition, runtime_id, tuple(_file(item) for item in files))


def _file(raw: Any) -> UpdateFile:
    if not isinstance(raw, dict):
        raise FeedError("a file entry is not an object")
    name, size, digest = raw.get("name"), raw.get("size"), raw.get("sha256")
    if not isinstance(name, str) or not _FILE_NAME.fullmatch(name) or ".." in name:
        raise FeedError(f"unsafe file name {name!r}")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise FeedError(f"unusable size for {name}")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise FeedError(f"unusable SHA-256 for {name}")
    return UpdateFile(name, size, digest)


def _text(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise FeedError(f"the update information has no {key}")
    return value


def _read(source: UpdateSource, url: str, limit: int, opener: Callable[..., Any],
          missing_ok: bool = False) -> bytes | None:
    """The body at url, at most `limit` bytes; None for a 404 when missing_ok."""
    try:
        with opener(source, url, CHECK_TIMEOUT_S) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise FeedUnreachable(f"{url} answered HTTP {error.code}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise FeedUnreachable(f"{url} could not be read: {getattr(error, 'reason', error)}") from error
    if len(data) > limit:
        raise FeedError(f"{url} is larger than {limit} bytes")
    return data


def _check_url(source: UpdateSource, url: str) -> None:
    """Only HTTPS, or plain HTTP to 127.0.0.1 for a staging build, may be used."""
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return
    if source.allow_local_http and parts.scheme == "http" and parts.hostname == "127.0.0.1":
        return
    raise FeedUnreachable(f"refused to open {url}: updates are only fetched over HTTPS")


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Follows GitHub's redirect to its download servers, never to plain HTTP."""

    def __init__(self, source: UpdateSource) -> None:
        super().__init__()
        self._source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102 - urllib's hook
        _check_url(self._source, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
