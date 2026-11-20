# test_update_scripts.py - the release workflow's update manifest and signature scripts

import hashlib
import importlib.util
import json
import os

import pytest

from gfglock.services import update_feed
from gfglock.utils import signature

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS, f"{name}.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manifest_script = _load("make_update_manifest")
meta_script = _load("read_meta")


class TestVersionDetails:
    def test_every_exe_names_the_app_and_its_version(self, tmp_path):
        """Code signing requires each exe's product name and version to be the project's."""
        out = tmp_path / "gfgLock.version.txt"
        assert meta_script.main(["--version-file", str(out), "--exe", "gfgLock", "--description", "gfgLock"]) == 0
        text = out.read_text(encoding="utf-8")
        meta = meta_script.app_meta()
        for key, value in (("ProductName", meta["AppName"]), ("ProductVersion", meta["Version"]),
                           ("FileVersion", meta["Version"]), ("OriginalFilename", "gfgLock.exe"),
                           ("LegalCopyright", meta_script.copyright_line())):
            assert f"StringStruct({key!r}, {value!r})" in text
        versioninfo = pytest.importorskip("PyInstaller.utils.win32.versioninfo")
        assert type(versioninfo.load_version_info_from_text_file(str(out))).__name__ == "VSVersionInfo"

    def test_the_metadata_prints_as_json_without_options(self, capsys):
        assert meta_script.main([]) == 0
        assert json.loads(capsys.readouterr().out)["AppName"] == meta_script.app_meta()["AppName"]


@pytest.fixture
def assets(tmp_path):
    files = {"gfgLock_3.4.0_user_installer.exe": b"user", "gfgLock_3.4.0_portable.exe": b"portable"}
    for name, body in files.items():
        (tmp_path / name).write_bytes(body)
    return tmp_path


class TestManifest:
    def test_manifest_lists_each_file_with_its_size_and_hash(self, assets, tmp_path):
        out = tmp_path / "update.json"
        code = manifest_script.main([
            "--app", "gfgLock", "--version", "3.4.0", "--repo", "owner/repo", "--out", str(out),
            "--package", f"kind=user;files={assets / 'gfgLock_3.4.0_user_installer.exe'}",
            "--package", f"kind=portable-exe;files={assets / 'gfgLock_3.4.0_portable.exe'}",
        ])
        assert code == 0
        data = json.loads(out.read_bytes())
        assert data["tag"] == "v3.4.0" and data["notes_url"] == "https://github.com/owner/repo/releases/tag/v3.4.0"
        assert data["packages"][0] == {"kind": "user", "files": [{
            "name": "gfgLock_3.4.0_user_installer.exe", "size": 4, "sha256": hashlib.sha256(b"user").hexdigest()}]}
        # What the script writes is what the app accepts.
        release = update_feed.parse_manifest(out.read_bytes(), "gfgLock")
        assert update_feed.pick_package(release, "portable-exe") is not None

    def test_split_installer_and_patch_fields(self, assets):
        user = assets / "gfgLock_3.4.0_user_installer.exe"
        package = manifest_script.parse_package(f"kind=patch;edition=cuda;runtime_id={'ab' * 32};files={user},{user}")
        assert package["edition"] == "cuda" and package["runtime_id"] == "ab" * 32 and len(package["files"]) == 2

    @pytest.mark.parametrize("spec", ["kind=msi;files=a", "kind=user", "kind=patch;files=a", "kind=user;files=a;os=win"])
    def test_bad_package_specs_are_refused(self, spec):
        with pytest.raises((ValueError, OSError)):
            manifest_script.parse_package(spec)

    def test_duplicate_packages_are_refused(self):
        package = {"kind": "user", "files": []}
        with pytest.raises(ValueError, match="same kind"):
            manifest_script.build_manifest("gfgLock", "3.4.0", "owner/repo", [package, dict(package)])


class TestSigning:
    @pytest.fixture
    def signer(self):
        pytest.importorskip("cryptography")
        return _load("sign_update")

    @pytest.fixture
    def key_pem(self, signer):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        key = ec.generate_private_key(ec.SECP256R1())
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                 serialization.NoEncryption()).decode("ascii")

    def test_ci_signature_verifies_in_the_app(self, signer, key_pem, tmp_path, monkeypatch):
        """The signer (cryptography) and the app's check (Windows CNG) agree on the format."""
        target = tmp_path / "update.json"
        target.write_bytes(b'{"schema": 1}\n')
        monkeypatch.setenv("UPDATE_SIGNING_KEY", key_pem)
        assert signer.main([str(target)]) == 0
        public = signer.public_pem(signer.load_key(key_pem))
        sig = (tmp_path / "update.json.sig").read_bytes()
        assert signature.verify(target.read_bytes(), sig, [public])
        assert not signature.verify(target.read_bytes() + b" ", sig, [public])

    def test_signing_needs_the_key(self, signer, tmp_path, monkeypatch):
        target = tmp_path / "update.json"
        target.write_bytes(b"{}")
        monkeypatch.delenv("UPDATE_SIGNING_KEY", raising=False)
        assert signer.main([str(target)]) == 1
        assert not (tmp_path / "update.json.sig").exists()

    def test_a_key_the_app_does_not_carry_stops_the_release(self, signer, key_pem, tmp_path, monkeypatch):
        target, source = tmp_path / "update.json", tmp_path / "defaults.py"
        target.write_bytes(b"{}")
        source.write_text("PUBLIC_KEYS = ()\n", encoding="utf-8")
        monkeypatch.setenv("UPDATE_SIGNING_KEY", key_pem)
        assert signer.main([str(target), "--expect", str(source)]) == 1
        source.write_text(f'PUBLIC_KEYS = ("""{signer.public_pem(signer.load_key(key_pem))}""",)\n', encoding="utf-8")
        assert signer.main([str(target), "--expect", str(source)]) == 0
