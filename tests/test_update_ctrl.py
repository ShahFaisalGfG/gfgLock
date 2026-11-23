# test_update_ctrl.py - the update controller's flow: check, download, install on exit (no network)

import hashlib
import os

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from gfglock.controllers import update_ctrl
from gfglock.controllers.update_ctrl import UpdateController, UpdaterConfig
from gfglock.services import update_install as install
from gfglock.services.update_feed import FeedError, FeedUnreachable, Release, UpdateFile, UpdatePackage, UpdateSource

BODY = b"installer bytes"
SHA = hashlib.sha256(BODY).hexdigest()


def release(version: str = "3.4.0", kinds=("system", "user", "portable-exe"), patch_runtime: str = "") -> Release:
    packages = [UpdatePackage(kind, "", "", (UpdateFile(f"gfgLock_{version}_{kind}.exe", len(BODY), SHA),))
                for kind in kinds]
    if patch_runtime:
        packages.append(UpdatePackage("patch", "", patch_runtime, (UpdateFile("patch.exe", len(BODY), SHA),)))
    return Release("gfgLock", version, f"v{version}", f"https://example.com/v{version}", tuple(packages),
                   b"manifest", b"good")


class SyncPool:
    """Runs workers at once on the calling thread, so their signals arrive before start() returns."""

    def start(self, worker):
        worker.run()

    def waitForDone(self, _ms):
        return True


class Run(QObject):
    busyChanged = Signal(bool)  # like EncryptController's: the new value

    def __init__(self):
        super().__init__()
        self.busy = False


class Harness:
    """A controller for one install kind, with the network, installer, and preferences faked."""

    def __init__(self, monkeypatch, tmp_path, kind="user", latest=None, error="", error_type=FeedError,
                 metered=False, auto_check=True, auto_install=True, runtime_id=""):
        self.prefs = [auto_check, auto_install]
        self.latest = latest
        self.error = error
        self.download_error: Exception | None = None
        self.logs: list[tuple[str, bool]] = []
        self.launched: list[tuple[str, str]] = []
        self.started: list[str] = []
        self.released = 0
        self.downloads = 0
        self.exe = tmp_path / "app" / "gfgLock.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"current exe")
        self.saved: dict[str, Release] = {}

        def fetch(source):
            if self.error:
                raise error_type(self.error)
            return self.latest

        def fake_download(source, tag, package, folder, progress, cancel, target_names=()):
            self.downloads += 1
            if self.download_error is not None:
                raise self.download_error
            names = list(target_names) or [item.name for item in package.files]
            paths = []
            for name in names:
                path = os.path.join(folder, name)
                os.makedirs(folder, exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(BODY)
                paths.append(path)
            progress(package.size, package.size)
            return paths

        def save(rel, folder):
            os.makedirs(folder, exist_ok=True)
            self.saved[folder] = rel

        def load(source, folder):
            if folder not in self.saved:
                raise FeedError("the saved update information can't be read")
            return self.saved[folder]

        monkeypatch.setattr(update_ctrl, "fetch_release", fetch)
        monkeypatch.setattr(update_ctrl, "save_release", save)
        monkeypatch.setattr(update_ctrl, "load_release", load)
        monkeypatch.setattr(update_ctrl.install, "download_package", fake_download)
        monkeypatch.setattr(update_ctrl.install, "is_metered", lambda: metered)
        monkeypatch.setattr(update_ctrl.install, "detect_install_kind", lambda: kind)
        monkeypatch.setattr(update_ctrl.install, "needs_approval", lambda k: k == "system")
        monkeypatch.setattr(update_ctrl.install, "exe_path", lambda: str(self.exe))
        monkeypatch.setattr(update_ctrl.install, "launch_installer", lambda path, args: self.launched.append((path, args)))
        monkeypatch.setattr(update_ctrl.install, "start_program", lambda path: self.started.append(path))
        monkeypatch.setattr(update_ctrl.QCoreApplication, "quit", lambda: None)
        self.opened: list[str] = []
        monkeypatch.setattr(update_ctrl.QDesktopServices, "openUrl", lambda url: self.opened.append(url.toString()) or True)

        def release_locks():
            self.released += 1

        self.config = UpdaterConfig(
            source=UpdateSource("gfgLock", "3.3.0", "https://github.com/owner/repo", ("key",)),
            state_path=str(tmp_path / "data" / "updates.json"),
            downloads_dir=str(tmp_path / "updates"),
            read_prefs=lambda: (self.prefs[0], self.prefs[1]),
            log=lambda message, error: self.logs.append((message, error)),
            release_locks=release_locks,
            runtime_id=runtime_id,
        )
        self.run = Run()
        self.notices: list[str] = []
        self.ctrl = self.make()

    def make(self) -> UpdateController:
        ctrl = UpdateController(self.config)
        ctrl._pool = SyncPool()  # type: ignore[assignment]
        ctrl.set_busy_sources([self.run])
        ctrl.notice.connect(self.notices.append)
        return ctrl

    def state(self) -> install.UpdateState:
        return install.load_state(self.config.state_path)


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def harness(monkeypatch, tmp_path):
    def build(**options) -> Harness:
        return Harness(monkeypatch, tmp_path, **options)
    return build


class TestCheck:
    def test_newer_version_downloads_and_waits_for_close(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        assert h.ctrl.status == "ready"
        assert h.ctrl.message == "gfgLock 3.4.0 is ready and installs when you close gfgLock."
        assert h.ctrl.bannerVisible and h.ctrl.progress == 1.0
        state = h.state()
        assert state.pending_version == "3.4.0" and state.pending_kind == "user" and state.last_check > 0

    def test_up_to_date(self, harness):
        h = harness(latest=release("3.3.0"))
        h.ctrl.checkNow()
        assert h.ctrl.status == "upToDate" and h.notices == ["gfgLock 3.3.0 is the latest version."]
        assert not h.ctrl.bannerVisible

    def test_no_release_information_counts_as_up_to_date(self, harness):
        h = harness(latest=None)
        h.ctrl.checkNow()
        assert h.ctrl.status == "upToDate"

    def test_a_failed_daily_check_stays_quiet(self, harness):
        h = harness(error="no route")
        h.ctrl._maybe_check()
        assert h.ctrl.status == "idle" and h.notices == [] and h.state().last_check == 0
        assert h.logs == [("Update check failed: no route", False)]

    def test_a_failed_manual_check_says_what_to_do(self, harness):
        h = harness(error="https://example.com/update.json could not be read: no route", error_type=FeedUnreachable)
        h.ctrl.checkNow()
        assert h.ctrl.status == "error" and h.notices == [update_ctrl.CHECK_OFFLINE]
        assert h.logs == [("Update check failed: https://example.com/update.json could not be read: no route", True)]

    def test_untrusted_update_information_is_not_blamed_on_the_connection(self, harness):
        h = harness(error="the update information is not signed by the publisher")
        h.ctrl.checkNow()
        assert h.ctrl.status == "error" and h.ctrl.message == update_ctrl.CHECK_FAILED
        assert "signed" not in h.ctrl.message

    def test_daily_check_respects_the_switch_and_the_day(self, harness):
        h = harness(latest=release("3.3.0"), auto_check=False)
        h.ctrl._maybe_check()
        assert h.ctrl.status == "idle"
        h.prefs[0] = True
        h.ctrl._maybe_check()
        assert h.ctrl.status == "upToDate"
        h.latest = release()
        h.ctrl._maybe_check()  # checked less than a day ago
        assert h.ctrl.status == "upToDate"

    def test_skipped_version_is_offered_only_when_asked(self, harness):
        h = harness(latest=release(), auto_install=False)
        h.ctrl.checkNow()
        h.ctrl.skipVersion()
        assert h.state().skipped == "3.4.0" and not h.ctrl.bannerVisible
        h.ctrl._saved.last_check = 0
        h.ctrl._maybe_check()
        assert h.ctrl.status == "idle"
        h.ctrl.checkNow()
        assert h.ctrl.status == "available"

    def test_without_automatic_installs_the_user_starts_the_download(self, harness):
        h = harness(latest=release(), auto_install=False)
        h.ctrl.checkNow()
        assert h.ctrl.status == "available" and h.downloads == 0
        h.ctrl.download()
        assert h.ctrl.status == "ready" and h.downloads == 1

    def test_metered_connection_waits(self, harness):
        h = harness(latest=release(), metered=True)
        h.ctrl.checkNow()
        assert h.ctrl.status == "available" and h.downloads == 0
        assert "limited connection" in h.ctrl.message

    def test_turning_installs_on_starts_the_download(self, harness):
        h = harness(latest=release(), auto_install=False)
        h.ctrl.checkNow()
        h.prefs[1] = True
        h.ctrl.preferencesChanged()
        assert h.ctrl.status == "ready"


class TestDownloadFailures:
    @pytest.mark.parametrize("error, text", [
        (install.DownloadInterrupted("The download of setup.exe stopped: [WinError 10054] reset"),
         update_ctrl.DOWNLOAD_INTERRUPTED),
        (install.FileMismatch("setup.exe didn't match its published checksum, so it was deleted."),
         update_ctrl.DOWNLOAD_DAMAGED),
        (install.SaveError(r"Couldn't create C:\updates\3.4.0: Access is denied"), update_ctrl.SAVE_FAILED),
        (RuntimeError("a bug"), update_ctrl.DOWNLOAD_FAILED),
    ])
    def test_the_notice_says_what_to_do_and_the_log_keeps_the_details(self, harness, error, text):
        h = harness(latest=release())
        h.download_error = error
        h.ctrl.checkNow()
        h.ctrl.dismiss()
        h.ctrl.download()  # Try again
        assert h.ctrl.status == "error" and h.ctrl.message == text and h.ctrl.bannerVisible
        message, is_error = h.logs[-1]
        assert is_error and message.startswith("Update download failed: ") and str(error) in message
        h.download_error = None
        h.ctrl.download()
        assert h.ctrl.status == "ready"


class TestCopiesThatCantUpdateThemselves:
    @pytest.mark.parametrize("kind", [install.PORTABLE_FOLDER, install.SOURCE])
    def test_they_link_to_the_download_page(self, harness, kind):
        h = harness(kind=kind, latest=release())
        h.ctrl.checkNow()
        assert h.ctrl.status == "available" and not h.ctrl.canDownload and h.downloads == 0
        assert h.ctrl.message == "gfgLock 3.4.0 is available. Get it from the download page."
        h.ctrl.download()
        assert h.opened == ["https://github.com/owner/repo/releases/latest"]


class TestInstallOnExit:
    def test_installer_runs_silently_as_the_app_exits(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        h.ctrl.install_on_exit()
        (path, args), = h.launched
        assert path.endswith(os.path.join("3.4.0", "gfgLock_3.4.0_user.exe"))
        assert "/VERYSILENT" in args and "/relaunch=0" in args and f"/updatepid={os.getpid()}" in args
        assert h.released == 1 and h.state().attempted == "3.4.0"

    def test_restart_now_starts_the_new_version(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        h.ctrl.restartNow()
        h.ctrl.install_on_exit()
        assert "/relaunch=1" in h.launched[0][1]

    def test_restart_waits_for_a_run(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        changes = []
        h.ctrl.stateChanged.connect(lambda: changes.append(h.ctrl.canRestart))
        h.run.busy = True
        h.run.busyChanged.emit(True)
        assert changes == [False] and not h.ctrl.canRestart
        h.ctrl.restartNow()
        assert not h.ctrl._relaunch
        h.run.busy = False
        h.run.busyChanged.emit(False)
        assert changes == [False, True]

    def test_nothing_runs_without_a_download(self, harness):
        h = harness(latest=release(), auto_install=False)
        h.ctrl.checkNow()
        h.ctrl.install_on_exit()
        assert h.launched == [] and h.released == 0

    def test_a_file_changed_after_download_is_deleted_not_run(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        installer = h.state().pending_files[0]
        with open(installer, "ab") as fh:
            fh.write(b"tampered")
        h.ctrl.install_on_exit()
        assert h.launched == [] and not os.path.exists(installer) and h.state().pending_version == ""
        assert h.logs[-1][1] is True

    def test_failed_launch_is_not_retried_on_every_close(self, harness, monkeypatch):
        h = harness(latest=release(), kind="system")
        h.ctrl.checkNow()
        assert "administrator approval" in h.ctrl.message

        def declined(path, args):
            raise install.InstallError("The update was not installed: the administrator prompt was declined.")

        monkeypatch.setattr(update_ctrl.install, "launch_installer", declined)
        h.ctrl.install_on_exit()
        assert h.state().failed == "3.4.0"
        again = h.make()
        again.start()
        assert again.status == "failed" and "wasn't installed" in again.message
        assert "choose Yes when Windows asks for permission" in again.message
        again.install_on_exit()  # not on its own
        assert h.launched == []
        monkeypatch.setattr(update_ctrl.install, "launch_installer", lambda path, args: h.launched.append((path, args)))
        again.restartNow()  # Install now
        again.install_on_exit()
        assert len(h.launched) == 1

    def test_portable_exe_swaps_itself(self, harness):
        h = harness(latest=release(), kind=install.PORTABLE_EXE)
        h.ctrl.checkNow()
        assert h.ctrl.status == "ready" and os.path.exists(str(h.exe) + ".new")
        h.ctrl.restartNow()
        h.ctrl.install_on_exit()
        assert h.exe.read_bytes() == BODY and h.started == [str(h.exe)]
        assert open(str(h.exe) + ".old", "rb").read() == b"current exe"


class TestRestore:
    def test_a_download_from_last_session_is_ready_again(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        again = h.make()
        again.start()
        assert again.status == "ready" and again.latestVersion == "3.4.0"

    def test_an_installed_update_is_cleaned_up(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        installer = h.state().pending_files[0]
        h.config = UpdaterConfig(**{**h.config.__dict__, "source": UpdateSource(
            "gfgLock", "3.4.0", "https://github.com/owner/repo", ("key",))})
        again = h.make()
        again.start()
        assert again.status == "idle" and not os.path.exists(installer) and h.state().pending_version == ""

    def test_untrusted_saved_manifest_discards_the_download(self, harness):
        h = harness(latest=release())
        h.ctrl.checkNow()
        h.saved.clear()
        again = h.make()
        again.start()
        assert again.status == "idle" and h.state().pending_version == ""


class TestPatches:
    def test_a_patch_for_this_runtime_is_preferred(self, harness):
        h = harness(latest=release(patch_runtime="ab" * 32), runtime_id="ab" * 32)
        h.ctrl.checkNow()
        assert h.state().pending_kind == "patch"

    def test_another_runtime_takes_the_full_installer(self, harness):
        h = harness(latest=release(patch_runtime="ab" * 32), runtime_id="cd" * 32)
        h.ctrl.checkNow()
        assert h.state().pending_kind == "user"


def test_the_exit_word_reaches_the_window(harness):
    h = harness()
    assert h.ctrl.exitWord == "close"


def test_sizes_read_naturally():
    assert update_ctrl._size(45_600_000) == "45.6 MB"
    assert update_ctrl._size(1_840_000_000) == "1.84 GB"
