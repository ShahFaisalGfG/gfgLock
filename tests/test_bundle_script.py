# test_bundle_script.py - the portable .7z from scripts/bundle.ps1: the bundle's files sit at the top, beside the marker

import os
import shutil
import subprocess

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seven_zip() -> str | None:
    """7-Zip as New-PortableArchive finds it: on PATH, else in Program Files."""
    default = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip", "7z.exe")
    return shutil.which("7z") or (default if os.path.isfile(default) else None)


@pytest.mark.skipif(shutil.which("pwsh") is None or _seven_zip() is None, reason="needs PowerShell 7 and 7-Zip")
def test_the_portable_archive_keeps_the_app_beside_its_marker(tmp_path):
    """The release workflow passes a relative bundle folder, which 7-Zip would otherwise store whole."""
    bundle = tmp_path / "dist" / "gfgLock"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "_internal").mkdir()
    (bundle / "gfgLock.exe").write_bytes(b"app")
    (bundle / "bin" / "gfglock.exe").write_bytes(b"command line")
    (bundle / "_internal" / "base_library.zip").write_bytes(b"library")
    archive = tmp_path / "portable.7z"
    script = (f". '{os.path.join(_ROOT, 'scripts', 'bundle.ps1')}'; "
              f"New-PortableArchive -BundleDir 'dist\\gfgLock' -ArchivePath '{archive}'")
    subprocess.run(["pwsh", "-NoProfile", "-Command", script], cwd=tmp_path, check=True, capture_output=True)
    listing = subprocess.run([_seven_zip() or "7z", "l", "-slt", str(archive)],
                             capture_output=True, text=True, check=True).stdout
    paths = {line[len("Path = "):] for line in listing.splitlines() if line.startswith("Path = ")} - {str(archive)}
    assert {"gfgLock.exe", "bin\\gfglock.exe", "_internal\\base_library.zip", "gfgLock-portable.txt",
            "LICENSE.txt", "THIRD_PARTY_NOTICES.md"} <= paths
    assert any(path.startswith("licenses\\") for path in paths)
    assert not any(path.startswith("dist") for path in paths)
