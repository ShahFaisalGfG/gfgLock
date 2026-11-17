# test_update_install.py - downloading, checking, and installing an update (no network, no installer)

import hashlib
import io
import os
import sys
import urllib.error

import pytest

from gfglock.services import update_install as install
from gfglock.services.update_feed import UpdateFile, UpdatePackage, UpdateSource

SOURCE = UpdateSource("gfgLock", "3.3.0", "https://github.com/owner/repo", ("key",))
BODY = os.urandom(3 * 1024 * 1024 + 123)  # over three read chunks


def file_for(body: bytes, name: str = "gfgLock_3.4.0_user_installer.exe") -> UpdateFile:
    return UpdateFile(name, len(body), hashlib.sha256(body).hexdigest())


class _Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status


class FakeServer:
    """Serves BODY, honouring Range like GitHub's download servers unless told not to."""

    def __init__(self, body: bytes = BODY, ranges: bool = True) -> None:
        self.body = body
        self.ranges = ranges
        self.headers: list[dict] = []

    def __call__(self, source, url, timeout, headers=None):
        headers = headers or {}
        self.headers.append(headers)
        if self.ranges and "Range" in headers:
            start = int(headers["Range"].removeprefix("bytes=").rstrip("-"))
            return _Response(self.body[start:], 206)
        return _Response(self.body)


def download(folder, server, cancel=None, body=BODY, progress=None):
    package = UpdatePackage("user", "", "", (file_for(body),))
    return install.download_package(SOURCE, "v3.4.0", package, str(folder), progress or (lambda done, total: None),
                                    cancel or install.DownloadCancel(), opener=server)


class TestDownload:
    def test_file_is_downloaded_and_checked(self, tmp_path):
        reports = []
        paths = download(tmp_path, FakeServer(), progress=lambda done, total: reports.append((done, total)))
        assert paths == [str(tmp_path / "gfgLock_3.4.0_user_installer.exe")]
        assert open(paths[0], "rb").read() == BODY
        assert reports[-1] == (len(BODY), len(BODY))
        assert not os.path.exists(paths[0] + ".part")

    def test_a_partial_download_resumes(self, tmp_path):
        (tmp_path / "gfgLock_3.4.0_user_installer.exe.part").write_bytes(BODY[:1000])
        server = FakeServer()
        paths = download(tmp_path, server)
        assert server.headers == [{"Range": "bytes=1000-"}]
        assert open(paths[0], "rb").read() == BODY

    def test_a_server_that_ignores_ranges_restarts_the_file(self, tmp_path):
        (tmp_path / "gfgLock_3.4.0_user_installer.exe.part").write_bytes(b"x" * 1000)
        paths = download(tmp_path, FakeServer(ranges=False))
        assert open(paths[0], "rb").read() == BODY

    def test_a_complete_file_is_not_fetched_again(self, tmp_path):
        (tmp_path / "gfgLock_3.4.0_user_installer.exe").write_bytes(BODY)
        server = FakeServer()
        download(tmp_path, server)
        assert server.headers == []

    def test_wrong_content_is_deleted(self, tmp_path):
        tampered = bytearray(BODY)
        tampered[5] ^= 1
        with pytest.raises(install.InstallError, match="checksum"):
            download(tmp_path, FakeServer(bytes(tampered)))
        assert list(tmp_path.iterdir()) == []

    def test_more_data_than_published_stops(self, tmp_path):
        with pytest.raises(install.InstallError, match="larger"):
            download(tmp_path, FakeServer(BODY + b"extra"))

    def test_a_short_download_keeps_its_part_for_next_time(self, tmp_path):
        with pytest.raises(install.InstallError, match="ended early"):
            download(tmp_path, FakeServer(BODY[:5000]))
        assert (tmp_path / "gfgLock_3.4.0_user_installer.exe.part").stat().st_size == 5000

    def test_network_failure_is_reported(self, tmp_path):
        def offline(source, url, timeout, headers=None):
            raise urllib.error.URLError("no route")

        with pytest.raises(install.InstallError, match="no route"):
            download(tmp_path, offline)

    def test_cancel_stops_the_download(self, tmp_path):
        cancel = install.DownloadCancel()

        def progress(done, total):
            if done > 1024 * 1024:
                cancel.cancel()

        with pytest.raises(install.UpdateCancelled):
            download(tmp_path, FakeServer(), cancel=cancel, progress=progress)

    def test_target_names_rename_the_download(self, tmp_path):
        package = UpdatePackage("portable-exe", "", "", (file_for(BODY, "gfgLock_3.4.0_portable.exe"),))
        paths = install.download_package(SOURCE, "v3.4.0", package, str(tmp_path), lambda d, t: None,
                                         install.DownloadCancel(), opener=FakeServer(),
                                         target_names=["gfgLock.exe.new"])
        assert paths == [str(tmp_path / "gfgLock.exe.new")]


class TestLockedVerification:
    def test_matching_files_stay_locked_against_changes(self, tmp_path):
        path = tmp_path / "setup.exe"
        path.write_bytes(BODY)
        locks = install.lock_verified([str(path)], [file_for(BODY)])
        try:
            with pytest.raises(PermissionError):
                open(path, "ab")
            with pytest.raises(PermissionError):
                os.replace(path, tmp_path / "moved.exe")
            assert open(path, "rb").read(4) == BODY[:4]  # reading (the installer reads itself) still works
        finally:
            for lock in locks:
                lock.close()
        os.replace(path, tmp_path / "moved.exe")  # free again once unlocked

    def test_allow_rename_lets_the_swap_move_it(self, tmp_path):
        path = tmp_path / "app.exe.new"
        path.write_bytes(BODY)
        locks = install.lock_verified([str(path)], [file_for(BODY)], allow_rename=True)
        try:
            os.replace(path, tmp_path / "app.exe")
            with pytest.raises(PermissionError):
                open(tmp_path / "app.exe", "ab")
        finally:
            for lock in locks:
                lock.close()

    def test_a_changed_file_is_a_mismatch(self, tmp_path):
        path = tmp_path / "setup.exe"
        path.write_bytes(BODY[:-1] + b"!")
        with pytest.raises(install.FileMismatch):
            install.lock_verified([str(path)], [file_for(BODY)])
        os.remove(path)  # the failed check left nothing locked

    def test_file_count_must_match(self, tmp_path):
        with pytest.raises(install.InstallError):
            install.lock_verified([], [file_for(BODY)])


class TestInstall:
    def test_silent_update_arguments(self):
        args = install.installer_arguments(True, r"C:\Temp\install.log", ["/CURRENTUSER"])
        assert args.split()[:3] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        assert f"/updatepid={os.getpid()}" in args and "/relaunch=1" in args
        assert '/LOG="C:\\Temp\\install.log"' in args and args.endswith("/CURRENTUSER")
        assert "/relaunch=0" in install.installer_arguments(False, "x.log")

    def test_installer_starts_through_the_shell(self, monkeypatch):
        calls = []
        monkeypatch.setattr(install.os, "startfile", lambda *args: calls.append(args), raising=False)
        install.launch_installer("setup.exe", "/VERYSILENT")
        assert calls == [("setup.exe", "open", "/VERYSILENT")]

    def test_declined_administrator_prompt_is_reported(self, monkeypatch):
        def declined(*args):
            error = OSError("cancelled")
            error.winerror = 1223  # type: ignore[attr-defined]
            raise error

        monkeypatch.setattr(install.os, "startfile", declined, raising=False)
        with pytest.raises(install.InstallError, match="declined"):
            install.launch_installer("setup.exe", "")

    def test_portable_exe_swaps_and_keeps_its_name(self, tmp_path):
        exe, new = tmp_path / "gfgLock_3.3.0_portable.exe", tmp_path / "gfgLock_3.3.0_portable.exe.new"
        exe.write_bytes(b"old")
        new.write_bytes(b"new")
        install.swap_portable_exe(str(new), str(exe))
        assert exe.read_bytes() == b"new" and (tmp_path / "gfgLock_3.3.0_portable.exe.old").read_bytes() == b"old"
        install.remove_leftovers(str(exe))
        assert not (tmp_path / "gfgLock_3.3.0_portable.exe.old").exists()

    def test_failed_swap_puts_the_original_back(self, tmp_path):
        exe = tmp_path / "app.exe"
        exe.write_bytes(b"old")
        with pytest.raises(install.InstallError):
            install.swap_portable_exe(str(tmp_path / "missing.new"), str(exe))
        assert exe.read_bytes() == b"old"

    def test_remove_files_takes_parts_and_empty_folders(self, tmp_path):
        folder = tmp_path / "3.4.0"
        folder.mkdir()
        (folder / "a.exe").write_bytes(b"a")
        (folder / "b.bin.part").write_bytes(b"b")
        install.remove_files([str(folder / "a.exe"), str(folder / "b.bin")])
        assert not folder.exists()


class TestInstallKind:
    @pytest.fixture
    def frozen(self, monkeypatch, tmp_path):
        """A frozen one-folder build in tmp_path\\app; returns the folder."""
        app = tmp_path / "app"
        (app / "_internal").mkdir(parents=True)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(app / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(app / "gfgLock.exe"))
        return app

    def test_source(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert install.detect_install_kind() == install.SOURCE

    def test_one_file_exe_is_portable(self, frozen, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "temp" / "_MEI123"))
        assert install.detect_install_kind() == install.PORTABLE_EXE

    @pytest.mark.parametrize("kind", ["system", "user"])
    def test_installers_record_their_kind(self, frozen, kind):
        (frozen / "install.ini").write_text(f"[install]\nkind={kind}\n", encoding="utf-8")
        assert install.detect_install_kind() == kind

    def test_unpacked_folder_without_a_record_is_portable(self, frozen):
        assert install.detect_install_kind() == install.PORTABLE_FOLDER

    def test_unknown_record_is_portable(self, frozen):
        (frozen / "install.ini").write_text("[install]\nkind=msi\n", encoding="utf-8")
        assert install.detect_install_kind() == install.PORTABLE_FOLDER

    def test_only_a_system_install_asks_for_approval(self, monkeypatch):
        monkeypatch.setattr(install, "is_elevated", lambda: False)
        assert install.needs_approval(install.SYSTEM)
        assert not install.needs_approval(install.USER)
        monkeypatch.setattr(install, "is_elevated", lambda: True)
        assert not install.needs_approval(install.SYSTEM)

    def test_windows_hints_answer(self):
        assert isinstance(install.is_metered(), bool)
        with install.background_priority():
            pass


class TestState:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "updates.json")
        state = install.UpdateState(last_check=12.5, skipped="3.5.0", pending_version="3.4.0",
                                    pending_kind="user", pending_files=["a"], attempted="3.4.0")
        assert install.save_state(path, state)
        assert install.load_state(path) == state

    @pytest.mark.parametrize("text", ["{", "[]", '{"last_check": "soon", "pending_files": [1]}'])
    def test_unusable_file_gives_defaults(self, tmp_path, text):
        path = tmp_path / "updates.json"
        path.write_text(text, encoding="utf-8")
        assert install.load_state(str(path)) == install.UpdateState()

    def test_check_is_due_once_a_day(self):
        state = install.UpdateState(last_check=1000.0)
        assert not state.check_due(86400, now=1000.0 + 3600)
        assert state.check_due(86400, now=1000.0 + 86400)
        assert state.check_due(86400, now=500.0)  # a clock set back doesn't block checks

    def test_installed_update_is_forgotten(self, tmp_path):
        leftover = tmp_path / "3.4.0" / "setup.exe"
        leftover.parent.mkdir()
        leftover.write_bytes(b"x")
        state = install.UpdateState(pending_version="3.4.0", pending_kind="user", pending_files=[str(leftover)],
                                    attempted="3.4.0")
        assert install.settle_pending(state, "3.4.0")
        assert state == install.UpdateState() and not leftover.exists()

    def test_an_install_that_did_not_take_is_marked_failed(self):
        state = install.UpdateState(pending_version="3.4.0", pending_kind="user", attempted="3.4.0")
        assert install.settle_pending(state, "3.3.0")
        assert state.failed == "3.4.0" and state.attempted == "" and state.pending_version == "3.4.0"
