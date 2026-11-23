# update_ctrl.py - checks for, downloads, and installs app updates; drives the update banner
#
# Shared by gfgLock, gfgShield, and CC-Gen-Ultimate: keep the copies identical apart from the
# package name in the imports. Everything app-specific (where the state lives, the preferences,
# logging, the mutexes the installer waits for) comes in through UpdaterConfig.
#
# Flow: a check at most once a day fetches the signed manifest. With automatic installs on, a newer
# version downloads in the background (not on a metered connection) and installs when the app
# closes; "Restart now" installs it at once and starts the new version. Before anything runs, the
# saved manifest's signature and every file's SHA-256 are checked again, through a lock that keeps
# the files from changing until the installer has started.

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Property, QCoreApplication, QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from gfglock.services import update_install as install
from gfglock.services.update_feed import (
    MANIFEST_NAME,
    SIGNATURE_NAME,
    FeedError,
    FeedUnreachable,
    Release,
    UpdatePackage,
    UpdateSource,
    fetch_release,
    is_newer,
    load_release,
    pick_package,
    save_release,
)

FIRST_CHECK_DELAY_MS = 30_000
CHECK_INTERVAL_S = 24 * 60 * 60
POLL_MS = 60 * 60 * 1000  # how often a running app asks whether the daily check is due
_SHUTDOWN_WAIT_MS = 3000
_PROGRESS_STEP_S = 0.25
_INSTALL_LOG = "install.log"

IDLE = "idle"
CHECKING = "checking"
UP_TO_DATE = "upToDate"
AVAILABLE = "available"
DOWNLOADING = "downloading"
READY = "ready"
FAILED = "failed"
ERROR = "error"
_BANNER_STATES = frozenset({AVAILABLE, DOWNLOADING, READY, FAILED, ERROR})

# What the window says when a step fails; the error itself goes to the log.
CHECK_OFFLINE = "Couldn't check for updates. Check your internet connection and try again."
CHECK_FAILED = "Couldn't check for updates right now. Try again later."
DOWNLOAD_INTERRUPTED = "The update download was interrupted. Click Try again; it continues where it stopped."
DOWNLOAD_DAMAGED = "The update file was damaged, so it was deleted. Click Try again."
DOWNLOAD_FAILED = "The update couldn't be downloaded. Click Try again."
SAVE_FAILED = "The update couldn't be saved. Check that the drive has free space, then click Try again."


@dataclass(frozen=True)
class UpdaterConfig:
    """What the updater needs from the app it updates."""

    source: UpdateSource
    state_path: str                                   # updates.json in the app's data folder
    downloads_dir: str                                # each version downloads into a folder here
    read_prefs: Callable[[], tuple[bool, bool]]       # (check automatically, install automatically)
    log: Callable[[str, bool], object]                # (message, True for an error worth keeping)
    release_locks: Callable[[], None]                 # drop the mutexes the installer waits for
    edition: str = ""                                 # CC-Gen-Ultimate's GPU edition
    runtime_id: str = ""                              # CC-Gen-Ultimate's bundled runtime, for patches
    # Installer arguments a package needs besides the silent-update ones, by (install kind, package).
    extra_args: Callable[[str, UpdatePackage], Sequence[str]] = lambda kind, package: ()
    # How the user ends the app, as the messages say it: "quit" where closing the window keeps it
    # running in the tray (gfgShield).
    exit_word: str = "close"


class _Signals(QObject):
    # (Release or None, what went wrong for the log, what the window says, metered connection)
    checked = Signal(object, str, str, bool)
    progress = Signal("qlonglong", "qlonglong")  # type: ignore[arg-type]  # (done, all); 64-bit for large installers
    # (file paths or None, what went wrong for the log, what the window says, cancelled)
    downloaded = Signal(object, str, str, bool)


class _CheckWorker(QRunnable):
    """Fetch and verify the update manifest off the GUI thread."""

    def __init__(self, source: UpdateSource) -> None:
        super().__init__()
        self.setAutoDelete(False)  # the controller holds it until its result arrives
        self.signals = _Signals()
        self._source = source

    @Slot()
    def run(self) -> None:
        release: Release | None = None
        error = text = ""
        metered = False
        try:
            release = fetch_release(self._source)
            metered = install.is_metered()
        except FeedUnreachable as failure:
            error, text = str(failure), CHECK_OFFLINE
        except FeedError as failure:
            error, text = str(failure), CHECK_FAILED
        except Exception as failure:  # the thread boundary: any error must still end the check
            error, text = f"unexpected error: {failure!r}", CHECK_FAILED
        try:
            self.signals.checked.emit(release, error, text, metered)
        except RuntimeError:
            pass  # the app is shutting down and the signal object is already gone


class _DownloadWorker(QRunnable):
    """Download a package at background priority, reporting progress a few times a second."""

    def __init__(self, source: UpdateSource, release: Release, package: UpdatePackage, folder: str,
                 names: Sequence[str]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _Signals()
        self.stop = install.DownloadCancel()
        self._source = source
        self._release = release
        self._package = package
        self._folder = folder
        self._names = list(names)
        self._reported = 0.0

    @Slot()
    def run(self) -> None:
        paths: list[str] | None = None
        error = text = ""
        cancelled = False
        try:
            with install.background_priority():
                paths = install.download_package(self._source, self._release.tag, self._package, self._folder,
                                                 self._report, self.stop, target_names=self._names)
        except install.UpdateCancelled:
            cancelled = True
        except install.InstallError as failure:
            error, text = str(failure), _download_text(failure)
        except Exception as failure:  # the thread boundary
            error, text = f"unexpected error: {failure!r}", DOWNLOAD_FAILED
        try:
            self.signals.downloaded.emit(paths, error, text, cancelled)
        except RuntimeError:
            pass

    def _report(self, done: int, total: int) -> None:
        now = time.monotonic()
        if done >= total or now - self._reported >= _PROGRESS_STEP_S:
            self._reported = now
            try:
                self.signals.progress.emit(done, total)
            except RuntimeError:
                pass


class UpdateController(QObject):
    """Exposes the update state to QML: the banner, the Preferences card, and the About dialog."""

    stateChanged = Signal()
    progressChanged = Signal()
    # A result the user asked for (Check now) or should hear about; the window shows it as a toast.
    notice = Signal(str)

    def __init__(self, config: UpdaterConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._source = config.source
        self._app = config.source.app
        self._exit = config.exit_word
        self._kind = install.detect_install_kind()
        self._needs_approval = install.needs_approval(self._kind)
        self._exe = install.exe_path()
        self._saved = install.load_state(config.state_path)
        self._status = IDLE
        self._message = ""
        self._release: Release | None = None
        self._package: UpdatePackage | None = None
        self._done = 0
        self._total = 0
        self._metered = False
        self._manual = False
        self._dismissed = False
        self._relaunch = False
        self._busy_sources: list[Any] = []
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._check_worker: _CheckWorker | None = None
        self._download_worker: _DownloadWorker | None = None
        self._first_check = QTimer(self)
        self._first_check.setSingleShot(True)
        self._first_check.setInterval(FIRST_CHECK_DELAY_MS)
        self._first_check.timeout.connect(self._maybe_check)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._maybe_check)

    # ── Properties ────────────────────────────────────────────────────────

    @Property(str, notify=stateChanged)
    def status(self) -> str:
        """idle, checking, upToDate, available, downloading, ready, failed, or error."""
        return self._status

    @Property(str, notify=stateChanged)
    def message(self) -> str:
        """What the banner and Preferences say about the current state."""
        return self._message

    @Property(str, notify=stateChanged)
    def latestVersion(self) -> str:
        return self._release.version if self._release else ""

    @Property(bool, notify=stateChanged)
    def bannerVisible(self) -> bool:
        return self._status in _BANNER_STATES and self._release is not None and not self._dismissed

    @Property(bool, notify=stateChanged)
    def canDownload(self) -> bool:
        """True when this copy can update itself; other copies get a link to the releases page."""
        return self._kind in install.SELF_UPDATING and self._package is not None

    @Property(bool, constant=True)
    def canSelfUpdate(self) -> bool:
        """True for installed copies and the portable exe; False for the portable folder and source."""
        return self._kind in install.SELF_UPDATING

    @Property(bool, constant=True)
    def needsApproval(self) -> bool:
        """True when installing asks for administrator approval (a copy installed for all users)."""
        return self._needs_approval

    @Property(str, constant=True)
    def exitWord(self) -> str:
        """How the user ends the app, as the window says it: "close", or "quit" for an app that stays in the tray."""
        return self._exit

    @Property(bool, notify=stateChanged)
    def canRestart(self) -> bool:
        """True when a downloaded update can install now: no run or job would be cut short."""
        return self._status in (READY, FAILED) and not self._is_busy()

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        """Fraction (0-1) of the download done."""
        return self._done / self._total if self._total else 0.0

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:
        return f"{_size(self._done)} of {_size(self._total)}" if self._total else ""

    @Property(float, notify=stateChanged)
    def lastCheckedMs(self) -> float:
        """When the last check reached the server, in ms since 1970; 0 when never."""
        return self._saved.last_check * 1000.0

    # ── Slots ─────────────────────────────────────────────────────────────

    @Slot()
    def checkNow(self) -> None:
        """Check at once (Preferences, About), even for a version the user skipped."""
        if self._status not in (CHECKING, DOWNLOADING):
            self._check(manual=True)

    @Slot()
    def download(self) -> None:
        """Download the available update, or open the releases page for a copy that can't update itself."""
        if self._release is None or self._status not in (AVAILABLE, ERROR):
            return
        if not self.canDownload:
            self.openDownloadPage()
            return
        self._start_download()

    @Slot()
    def cancel(self) -> None:
        """Stop the download; the part already downloaded is kept and resumes next time."""
        if self._download_worker is not None:
            self._download_worker.stop.cancel()

    @Slot()
    def restartNow(self) -> None:
        """Close the app, install the downloaded update, and start the new version."""
        if not self.canRestart:
            return
        self._relaunch = True
        QCoreApplication.quit()

    @Slot()
    def skipVersion(self) -> None:
        """Stop offering this version; a later version is offered as usual."""
        if self._release is None:
            return
        self._saved.skipped = self._release.version
        self._save()
        self._release, self._package = None, None
        self._set_status(IDLE, "")

    @Slot()
    def dismiss(self) -> None:
        """Hide the banner until the update's state changes (it still installs on close when ready)."""
        self._dismissed = True
        self.stateChanged.emit()

    @Slot()
    def openReleaseNotes(self) -> None:
        url = self._release.notes_url if self._release else self._source.releases_url
        self._open(url)

    @Slot()
    def openDownloadPage(self) -> None:
        self._open(self._source.releases_url)

    @Slot()
    def preferencesChanged(self) -> None:
        """Apply new update preferences: check when checks were just turned on, download when installs were."""
        auto_check, auto_install = self._config.read_prefs()
        if auto_check and self._status in (IDLE, UP_TO_DATE, ERROR):
            self._first_check.start()
        if auto_install and self._status == AVAILABLE and self.canDownload and not self._metered:
            self._start_download()

    # ── Lifecycle (called from app.py) ────────────────────────────────────

    def start(self) -> None:
        """Forget an installed update, restore a downloaded one, and schedule the daily check."""
        if self._kind == install.PORTABLE_EXE:
            install.remove_leftovers(self._exe)
        try:
            changed = install.settle_pending(self._saved, self._source.version)
        except ValueError:  # a hand-edited version in updates.json
            self._saved = install.UpdateState()
            changed = True
        if changed:
            self._save()
        self._restore_pending()
        self._first_check.start()
        self._poll.start()

    def set_busy_sources(self, sources: Sequence[Any]) -> None:
        """Objects with a `busy` property and `busyChanged` signal; Restart now waits while any is busy."""
        self._busy_sources = list(sources)
        for source in self._busy_sources:
            source.busyChanged.connect(self._on_busy_changed)

    def shutdown(self) -> None:
        """Stop the timers and any download before the app exits."""
        self._first_check.stop()
        self._poll.stop()
        self.cancel()
        self._pool.waitForDone(_SHUTDOWN_WAIT_MS)

    def install_on_exit(self) -> None:
        """Install a downloaded update as the app exits; after Restart now, the new version starts too.

        An install that failed before is not tried again on its own, so a declined administrator
        prompt doesn't come back at every close; Install now retries it.
        """
        if self._status not in (READY, FAILED) or self._release is None:
            return
        if self._status == FAILED and not self._relaunch:
            return
        version = self._release.version
        folder = self._folder(version)
        try:
            release = load_release(self._source, folder)  # its signature, checked again offline
            package = self._choose_package(release)
            if release.version != version or package is None:
                raise install.InstallError("The saved update information doesn't match the download.")
            paths = self._package_paths(folder, package)
            if self._kind == install.PORTABLE_EXE:
                self._swap(version, paths, package)
            else:
                self._run_installer(version, folder, paths, package)
        except install.FileMismatch as error:
            self._config.log(f"The update to {version} was deleted: {error}", True)
            install.remove_files(self._saved.pending_files)
            self._saved.clear_pending()
            self._save()
        except (FeedError, install.InstallError, OSError) as error:
            self._config.log(f"The update to {version} was not installed: {error}", True)
            self._saved.attempted = ""
            self._saved.failed = version
            self._save()

    # ── Checking ──────────────────────────────────────────────────────────

    def _maybe_check(self) -> None:
        auto_check, _ = self._config.read_prefs()
        if not auto_check or self._status in (CHECKING, DOWNLOADING, READY, FAILED):
            return
        if self._saved.check_due(CHECK_INTERVAL_S):
            self._check(manual=False)

    def _check(self, manual: bool) -> None:
        self._manual = manual
        worker = _CheckWorker(self._source)
        worker.signals.checked.connect(self._on_checked)
        self._check_worker = worker
        self._set_status(CHECKING, "Checking for updates...")
        self._pool.start(worker)

    def _on_checked(self, release: Release | None, error: str, text: str, metered: bool) -> None:
        self._check_worker = None
        manual = self._manual
        if error:
            # A daily check that fails offline is routine; one the user asked for is worth keeping.
            self._config.log(f"Update check failed: {error}", manual)
            if manual:
                self._set_status(ERROR, text)
                self.notice.emit(self._message)
            else:
                self._restore_after_check()
            return
        self._saved.last_check = time.time()
        self._save()
        self._metered = metered
        current = self._source.version
        if release is None or not is_newer(release.version, current):
            if not self._restore_after_check():
                self._set_status(UP_TO_DATE, f"{self._app} {current} is the latest version.")
            if manual:
                self.notice.emit(self._message)
            return
        if self._saved.pending_version == release.version and self._restore_after_check():
            if manual:
                self.notice.emit(self._message)
            return
        if release.version == self._saved.skipped and not manual:
            self._release, self._package = None, None
            self._set_status(IDLE, "")
            return
        if self._saved.pending_version:  # an older download a newer release has replaced
            install.remove_files(self._saved.pending_files)
            self._saved.clear_pending()
            self._save()
        self._release = release
        self._package = self._choose_package(release)
        self._dismissed = False
        self._set_status(AVAILABLE, self._available_message())
        if manual:
            self.notice.emit(self._message)
        _, auto_install = self._config.read_prefs()
        if auto_install and self.canDownload and not metered:
            self._start_download()

    def _restore_after_check(self) -> bool:
        """Go back to the state a check interrupted; True when a downloaded update is waiting."""
        if self._release is not None and self._saved.pending_version == self._release.version:
            failed = self._saved.failed == self._release.version
            self._set_status(FAILED if failed else READY, self._failed_message() if failed else self._ready_message())
            return True
        if self._release is not None and is_newer(self._release.version, self._source.version):
            self._set_status(AVAILABLE, self._available_message())
            return False
        self._set_status(IDLE, "")
        return False

    # ── Downloading ───────────────────────────────────────────────────────

    def _start_download(self) -> None:
        release, package = self._release, self._package
        if release is None or package is None or self._download_worker is not None:
            return
        folder = self._folder(release.version)
        try:
            save_release(release, folder)
        except OSError as error:
            self._config.log(f"Couldn't save the update information for {release.version}: {error}", True)
            self._dismissed = False
            self._set_status(ERROR, SAVE_FAILED)
            return
        if self._kind == install.PORTABLE_EXE:
            target, names = os.path.dirname(self._exe), [os.path.basename(self._exe) + ".new"]
        else:
            target, names = folder, []
        worker = _DownloadWorker(self._source, release, package, target, names)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.downloaded.connect(self._on_downloaded)
        self._download_worker = worker
        self._done, self._total = 0, package.size
        self.progressChanged.emit()
        self._set_status(DOWNLOADING, f"Downloading {self._app} {release.version}...")
        self._pool.start(worker)

    def _on_progress(self, done: int, total: int) -> None:
        self._done, self._total = done, total
        self.progressChanged.emit()

    def _on_downloaded(self, paths: list[str] | None, error: str, text: str, cancelled: bool) -> None:
        self._download_worker = None
        release = self._release
        if release is None:
            return
        if cancelled:
            self._set_status(AVAILABLE, self._available_message())
            return
        if error or not paths:
            self._config.log(f"Update download failed: {error or 'no files were downloaded'}", True)
            self._dismissed = False  # the user has to act, so the notice comes back
            self._set_status(ERROR, text or DOWNLOAD_FAILED)
            return
        folder = self._folder(release.version)
        self._saved.pending_version = release.version
        self._saved.pending_kind = self._package.kind if self._package else ""
        self._saved.pending_files = [*paths, *(os.path.join(folder, name)
                                               for name in (MANIFEST_NAME, SIGNATURE_NAME, _INSTALL_LOG))]
        self._saved.failed = ""
        self._save()
        self._dismissed = False
        self._set_status(READY, self._ready_message())

    def _restore_pending(self) -> None:
        """Pick up an update downloaded in an earlier session, verified again from its saved manifest."""
        version = self._saved.pending_version
        if not version or self._kind not in install.SELF_UPDATING:
            return
        try:
            release = load_release(self._source, self._folder(version))
        except FeedError as error:
            self._config.log(f"Discarded the downloaded update {version}: {error}", True)
            install.remove_files(self._saved.pending_files)
            self._saved.clear_pending()
            self._save()
            return
        package = self._choose_package(release)
        if package is None or package.kind != self._saved.pending_kind or not all(
                os.path.isfile(path) for path in self._package_paths(self._folder(version), package)):
            return  # a check finds it again and resumes the download
        self._release, self._package = release, package
        failed = self._saved.failed == version
        self._set_status(FAILED if failed else READY, self._failed_message() if failed else self._ready_message())

    # ── Installing ────────────────────────────────────────────────────────

    def _run_installer(self, version: str, folder: str, paths: list[str], package: UpdatePackage) -> None:
        locks = install.lock_verified(paths, package.files)
        try:
            self._saved.attempted = version
            self._save()
            self._config.release_locks()
            arguments = install.installer_arguments(self._relaunch, os.path.join(folder, _INSTALL_LOG),
                                                    self._config.extra_args(self._kind, package))
            install.launch_installer(paths[0], arguments)
        finally:
            for lock in locks:
                lock.close()

    def _swap(self, version: str, paths: list[str], package: UpdatePackage) -> None:
        locks = install.lock_verified(paths, package.files, allow_rename=True)
        try:
            self._saved.attempted = version
            self._save()
            install.swap_portable_exe(paths[0], self._exe)
        finally:
            for lock in locks:
                lock.close()
        if self._relaunch:
            install.start_program(self._exe)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _choose_package(self, release: Release) -> UpdatePackage | None:
        """A patch for this runtime when the release has one, else this kind's full package."""
        if self._kind not in install.SELF_UPDATING:
            return None
        if self._kind != install.PORTABLE_EXE and self._config.runtime_id:
            patch = pick_package(release, "patch", self._config.edition, self._config.runtime_id)
            if patch is not None:
                return patch
        return pick_package(release, self._kind, self._config.edition)

    def _package_paths(self, folder: str, package: UpdatePackage) -> list[str]:
        if self._kind == install.PORTABLE_EXE:
            return [self._exe + ".new"]
        return [os.path.join(folder, item.name) for item in package.files]

    def _folder(self, version: str) -> str:
        return os.path.join(self._config.downloads_dir, version)

    def _available_message(self) -> str:
        version = self._release.version if self._release else ""
        if not self.canDownload:
            return f"{self._app} {version} is available. Get it from the download page."
        _, auto_install = self._config.read_prefs()
        if auto_install and self._metered:
            return (f"{self._app} {version} is available. It downloads on its own once you're off mobile data "
                    "or another limited connection.")
        return f"{self._app} {version} is available."

    def _ready_message(self) -> str:
        version = self._release.version if self._release else ""
        if self._kind == install.PORTABLE_EXE:
            return f"{self._app} {version} is downloaded and replaces this copy when you {self._exit} {self._app}."
        if self._needs_approval:
            return (f"{self._app} {version} is ready and installs when you {self._exit} {self._app}, "
                    "after Windows asks for administrator approval.")
        return f"{self._app} {version} is ready and installs when you {self._exit} {self._app}."

    def _failed_message(self) -> str:
        version = self._release.version if self._release else ""
        # A copy installed for all users most often fails here because the permission prompt was turned down.
        approval = " and choose Yes when Windows asks for permission" if self._needs_approval else ""
        return (f"{self._app} {version} wasn't installed the last time the app closed. "
                f"Click Install now{approval}, or get it from the download page.")

    def _set_status(self, status: str, message: str) -> None:
        if (status, message) != (self._status, self._message):
            self._status, self._message = status, message
            self.stateChanged.emit()

    def _save(self) -> None:
        if not install.save_state(self._config.state_path, self._saved):
            self._config.log(f"Could not save {self._config.state_path}", True)

    def _is_busy(self) -> bool:
        return any(bool(source.busy) for source in self._busy_sources)

    def _on_busy_changed(self, _busy: bool) -> None:
        """A run started or finished (its busyChanged carries the new value); Restart now may change."""
        self.stateChanged.emit()

    def _open(self, url: str) -> None:
        if not QDesktopServices.openUrl(QUrl(url)):
            self._config.log(f"Could not open {url}", True)


def _download_text(error: install.InstallError) -> str:
    """What the window says about a failed update download."""
    if isinstance(error, install.DownloadInterrupted):
        return DOWNLOAD_INTERRUPTED
    if isinstance(error, install.FileMismatch):
        return DOWNLOAD_DAMAGED
    if isinstance(error, install.SaveError):
        return SAVE_FAILED
    return DOWNLOAD_FAILED


def _size(count: int) -> str:
    """'45.6 MB' or '1.84 GB'."""
    if count >= 1000 ** 3:
        return f"{count / 1000 ** 3:.2f} GB"
    return f"{count / 1000 ** 2:.1f} MB"
