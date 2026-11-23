"""Named mutexes shared by the window and the command line (core/locks.py)."""

import ctypes
import subprocess
import sys
import textwrap
import uuid
from ctypes import wintypes

from gfglock.core import locks


class TestFolderClaims:
    def test_a_folder_is_free_once_and_claimed_while_held(self, tmp_path):
        with locks.claim_folders([str(tmp_path)]) as first:
            assert first == [str(tmp_path)]
            with locks.claim_folders([str(tmp_path).upper() + "\\"]) as second:
                assert second == []  # the same folder in another spelling
        with locks.claim_folders([str(tmp_path)]) as again:
            assert again == [str(tmp_path)]  # released when the first run ended

    def test_a_claim_in_another_process_protects_the_folder(self, tmp_path):
        """The window and a gfglock command (or two commands) never clear each other's temp files."""
        holder = subprocess.Popen(
            [sys.executable, "-c", textwrap.dedent(f"""
                import sys
                from gfglock.core import locks
                with locks.claim_folders([{str(tmp_path)!r}]) as free:
                    print("free" if free else "taken", flush=True)
                    sys.stdin.readline()
            """)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout is not None and holder.stdout.readline().strip() == "free"
            with locks.claim_folders([str(tmp_path)]) as free:
                assert free == []
        finally:
            holder.communicate("\n", timeout=30)
        with locks.claim_folders([str(tmp_path)]) as free:
            assert free == [str(tmp_path)]  # the other process ended, so its claim is gone

    def test_names_depend_only_on_the_folder(self, tmp_path):
        name = locks.folder_claim_name(str(tmp_path))
        assert name.startswith("Local\\gfgLock-folder-") and "\\" not in name[len("Local\\"):]
        assert name == locks.folder_claim_name(str(tmp_path) + "\\") != locks.folder_claim_name(str(tmp_path / "x"))


class TestAppMutexes:
    def test_app_mutexes_exist_for_the_installers(self, monkeypatch):
        names = (f"gfgLockTestMutex-{uuid.uuid4().hex}", f"Global\\gfgLockTestMutex-{uuid.uuid4().hex}")
        held: list[int] = []
        monkeypatch.setattr(locks, "APP_MUTEXES", names)
        monkeypatch.setattr(locks, "_app_mutexes", held)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        locks.hold_app_mutexes()
        try:
            assert held  # the Global one may be refused in some sessions; the local one never is
            handle = kernel32.OpenMutexW(0x00100000, False, names[0])  # SYNCHRONIZE
            assert handle
            kernel32.CloseHandle(handle)
        finally:
            locks.release_app_mutexes()
        assert held == []

    def test_a_second_window_opens_the_existing_mutexes(self, monkeypatch):
        """A second window, or a command line, gets a handle too, and nothing is logged as refused."""
        names = (f"gfgLockTestMutex-{uuid.uuid4().hex}",)
        held: list[int] = []
        logged: list[str] = []
        monkeypatch.setattr(locks, "APP_MUTEXES", names)
        monkeypatch.setattr(locks, "_app_mutexes", held)
        monkeypatch.setattr(locks, "write_log", lambda message, *args, **kwargs: logged.append(message))
        try:
            locks.hold_app_mutexes()
            locks.hold_app_mutexes()
            assert len(held) == 2 and all(held)
            assert logged == []
        finally:
            locks.release_app_mutexes()
