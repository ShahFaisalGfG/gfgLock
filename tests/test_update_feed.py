# test_update_feed.py - fetching and trusting the signed update manifest (no network)

import io
import json
import urllib.error

import pytest

from gfglock.services import update_feed as feed
from gfglock.services.update_feed import FeedError, Release, UpdateFile, UpdatePackage, UpdateSource

APP = "gfgLock"
SHA = "ab" * 32
SOURCE = UpdateSource(APP, "3.3.0", "https://github.com/owner/repo", ("test key",))


def manifest(**changes) -> dict:
    data = {
        "schema": 1,
        "app": APP,
        "version": "3.4.0",
        "tag": "v3.4.0",
        "notes_url": "https://github.com/owner/repo/releases/tag/v3.4.0",
        "packages": [
            {"kind": "system", "files": [{"name": "gfgLock_3.4.0_system_installer.exe", "size": 10, "sha256": SHA}]},
            {"kind": "user", "files": [{"name": "gfgLock_3.4.0_user_installer.exe", "size": 11, "sha256": SHA}]},
            {"kind": "patch", "edition": "cuda", "runtime_id": "cd" * 32,
             "files": [{"name": "patch.exe", "size": 5, "sha256": SHA}]},
        ],
    }
    data.update(changes)
    return data


def encode(data: dict) -> bytes:
    return json.dumps(data).encode("utf-8")


class _Response(io.BytesIO):
    status = 200


class FakeServer:
    """Serves bodies by URL; a missing URL answers 404."""

    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.requests: list[str] = []

    def __call__(self, source, url, timeout, headers=None):
        self.requests.append(url)
        if url not in self.bodies:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return _Response(self.bodies[url])


@pytest.fixture
def trusted(monkeypatch):
    """Signatures are good when the .sig body is b"good" (the CNG check has tests of its own)."""
    monkeypatch.setattr(feed.signature, "verify", lambda data, sig, keys: sig.strip() == b"good")


def serve(data: bytes, sig: bytes = b"good") -> FakeServer:
    return FakeServer({SOURCE.manifest_url: data, SOURCE.manifest_url + ".sig": sig})


class TestVersions:
    @pytest.mark.parametrize("text, expected", [("3.4.0", (3, 4, 0)), ("10.0.12", (10, 0, 12))])
    def test_parse(self, text, expected):
        assert feed.parse_version(text) == expected

    @pytest.mark.parametrize("text", ["3.4", "3.4.0.1", "v3.4.0", "03.4.0", "3.4.0-beta", "", None])
    def test_anything_else_is_refused(self, text):
        with pytest.raises(ValueError):
            feed.parse_version(text)

    def test_newer_compares_numbers_not_text(self):
        assert feed.is_newer("3.10.0", "3.9.9")
        assert not feed.is_newer("3.3.0", "3.3.0")
        assert not feed.is_newer("3.2.9", "3.3.0")


class TestFetch:
    def test_signed_release_is_returned(self, trusted):
        release = feed.fetch_release(SOURCE, serve(encode(manifest())))
        assert release is not None and release.version == "3.4.0"
        assert release.manifest == encode(manifest()) and release.signature == b"good"

    def test_no_manifest_means_no_update_information(self, trusted):
        """A repository without releases (or still private) answers 404: nothing to offer, no error."""
        assert feed.fetch_release(SOURCE, FakeServer({})) is None

    def test_bad_signature_is_refused(self, trusted):
        with pytest.raises(FeedError, match="not signed"):
            feed.fetch_release(SOURCE, serve(encode(manifest()), b"forged"))

    def test_missing_signature_is_refused(self, trusted):
        server = FakeServer({SOURCE.manifest_url: encode(manifest())})
        with pytest.raises(FeedError):
            feed.fetch_release(SOURCE, server)

    def test_a_build_without_keys_trusts_nothing(self, trusted):
        keyless = UpdateSource(APP, "3.3.0", SOURCE.base_url, ())
        with pytest.raises(FeedError, match="no signing key"):
            feed.fetch_release(keyless, FakeServer({keyless.manifest_url: encode(manifest()),
                                                    keyless.manifest_url + ".sig": b"good"}))

    def test_oversized_manifest_is_refused(self, trusted):
        with pytest.raises(FeedError, match="larger"):
            feed.fetch_release(SOURCE, serve(b" " * (65 * 1024)))

    def test_server_error_is_reported(self, trusted):
        def failing(source, url, timeout, headers=None):
            raise urllib.error.HTTPError(url, 500, "Server Error", None, None)  # type: ignore[arg-type]

        with pytest.raises(FeedError, match="HTTP 500"):
            feed.fetch_release(SOURCE, failing)

    def test_offline_is_reported(self, trusted):
        def offline(source, url, timeout, headers=None):
            raise urllib.error.URLError("no route")

        with pytest.raises(FeedError, match="no route"):
            feed.fetch_release(SOURCE, offline)


class TestManifest:
    @pytest.mark.parametrize("changes, message", [
        ({"app": "Another app"}, f"not {APP}"),
        ({"schema": 2}, "unknown format"),
        ({"version": "3.4"}, "not a version"),
        ({"tag": "v3.5.0"}, "doesn't match"),
        ({"notes_url": "http://example.com"}, "not https"),
        ({"packages": {}}, "no packages"),
    ])
    def test_unexpected_content_is_refused(self, changes, message):
        with pytest.raises(FeedError, match=message):
            feed.parse_manifest(encode(manifest(**changes)), APP)

    @pytest.mark.parametrize("name", ["..\\evil.exe", "../evil.exe", "C:\\evil.exe", "sub/evil.exe", ".hidden", "a..exe"])
    def test_file_names_that_could_leave_the_folder_are_refused(self, name):
        data = manifest(packages=[{"kind": "user", "files": [{"name": name, "size": 1, "sha256": SHA}]}])
        with pytest.raises(FeedError, match="unsafe file name"):
            feed.parse_manifest(encode(data), APP)

    @pytest.mark.parametrize("entry", [
        {"name": "a.exe", "size": 0, "sha256": SHA},
        {"name": "a.exe", "size": True, "sha256": SHA},
        {"name": "a.exe", "size": 1, "sha256": "AB" * 32},
        {"name": "a.exe", "size": 1, "sha256": "ab"},
    ])
    def test_unusable_sizes_and_hashes_are_refused(self, entry):
        with pytest.raises(FeedError):
            feed.parse_manifest(encode(manifest(packages=[{"kind": "user", "files": [entry]}])), APP)

    def test_unknown_package_kind_is_refused(self):
        data = manifest(packages=[{"kind": "msi", "files": [{"name": "a.msi", "size": 1, "sha256": SHA}]}])
        with pytest.raises(FeedError, match="unknown package kind"):
            feed.parse_manifest(encode(data), APP)

    def test_not_json_is_refused(self):
        with pytest.raises(FeedError, match="JSON"):
            feed.parse_manifest(b"\xff{", APP)


class TestPickPackage:
    @pytest.fixture
    def release(self) -> Release:
        return feed.parse_manifest(encode(manifest()), APP)

    def test_kind_is_matched(self, release):
        package = feed.pick_package(release, "user")
        assert package is not None and package.files[0].name == "gfgLock_3.4.0_user_installer.exe"

    def test_missing_kind_gives_nothing(self, release):
        assert feed.pick_package(release, "portable-exe") is None

    def test_patch_needs_the_same_runtime_and_edition(self, release):
        assert feed.pick_package(release, "patch", "cuda", "cd" * 32) is not None
        assert feed.pick_package(release, "patch", "cuda", "ef" * 32) is None
        assert feed.pick_package(release, "patch", "xpu", "cd" * 32) is None
        assert feed.pick_package(release, "patch", "cuda", "") is None

    def test_package_size_adds_its_files(self):
        package = UpdatePackage("system", "", "", (UpdateFile("a.exe", 3, SHA), UpdateFile("a-1.bin", 4, SHA)))
        assert package.size == 7


class TestSavedRelease:
    def test_saved_release_verifies_again(self, trusted, tmp_path):
        release = feed.fetch_release(SOURCE, serve(encode(manifest())))
        assert release is not None
        feed.save_release(release, str(tmp_path))
        assert feed.load_release(SOURCE, str(tmp_path)) == release

    def test_edited_saved_manifest_is_refused(self, monkeypatch, tmp_path):
        """The install step trusts only what the signature covers, never a file edited on disk."""
        original = encode(manifest())
        monkeypatch.setattr(feed.signature, "verify", lambda data, sig, keys: data == original)
        release = feed.verify_release(SOURCE, original, b"sig")
        feed.save_release(release, str(tmp_path))
        (tmp_path / feed.MANIFEST_NAME).write_bytes(original.replace(SHA.encode(), b"cd" * 32))
        with pytest.raises(FeedError, match="not signed"):
            feed.load_release(SOURCE, str(tmp_path))

    def test_missing_saved_manifest_is_reported(self, tmp_path):
        with pytest.raises(FeedError, match="can't be read"):
            feed.load_release(SOURCE, str(tmp_path))


class TestAddresses:
    def test_urls_follow_the_github_release_layout(self):
        assert SOURCE.manifest_url == "https://github.com/owner/repo/releases/latest/download/update.json"
        assert SOURCE.file_url("v3.4.0", "a.exe") == "https://github.com/owner/repo/releases/download/v3.4.0/a.exe"
        assert SOURCE.releases_url == "https://github.com/owner/repo/releases/latest"
        assert SOURCE.user_agent == "gfgLock/3.3.0"

    @pytest.mark.parametrize("url", ["http://github.com/a", "ftp://github.com/a", "file:///C:/a", "http://127.0.0.1:8765/a"])
    def test_only_https_is_opened(self, url):
        with pytest.raises(FeedError, match="HTTPS"):
            feed.open_url(SOURCE, url, 1)

    def test_a_staging_build_may_use_local_http(self):
        staging = UpdateSource(APP, "3.3.0", "http://127.0.0.1:8765", ("k",), allow_local_http=True)
        feed._check_url(staging, "http://127.0.0.1:8765/releases/latest/download/update.json")
        with pytest.raises(FeedError):
            feed._check_url(staging, "http://example.com/update.json")

    def test_redirect_to_plain_http_is_refused(self):
        handler = feed._SafeRedirects(SOURCE)
        with pytest.raises(FeedError):
            handler.redirect_request(None, None, 302, "Found", {}, "http://example.com/file")
