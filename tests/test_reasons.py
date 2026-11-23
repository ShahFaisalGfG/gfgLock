"""Plain words for what happened to a file (core/reasons.py) and the password rules (core/passwords.py)."""

import errno

import pytest

from gfglock.core import passwords, reasons


class TestCategories:
    @pytest.mark.parametrize("error,category", [
        ("wrong password, or the file is damaged", reasons.WRONG_PASSWORD),
        ("wrong password or the file was modified (authentication failed)", reasons.WRONG_PASSWORD),  # an older engine
        ("wrong password or the file is corrupted", reasons.WRONG_PASSWORD),
        ("the file is open in another program", reasons.IN_USE),
        ("the file was made by a newer gfgLock version", reasons.NEWER_VERSION),
        ("the file uses an encryption method this version doesn't know", reasons.NEWER_VERSION),
        ("not a gfgLock v2 file", reasons.DAMAGED),
        ("unsupported chunk size", reasons.DAMAGED),
        ("the file is truncated or corrupted", reasons.DAMAGED),
        ("the source file changed size while it was being read", reasons.CHANGED),
        ("could not write the output file (disk full or no access?)", reasons.DISK_FULL),
        ("could not read the source file", reasons.IO_ERROR),
        ("something nobody planned for", reasons.UNKNOWN),
    ])
    def test_engine_messages(self, error, category):
        assert reasons.categorize(error) == category

    @pytest.mark.parametrize("error,category", [
        (PermissionError(errno.EACCES, "Access is denied", None, 5), reasons.ACCESS_DENIED),
        (OSError(errno.EACCES, "The process cannot access the file", None, 32), reasons.IN_USE),
        (OSError(errno.ENOSPC, "There is not enough space on the disk", None, 112), reasons.DISK_FULL),
        (FileNotFoundError(errno.ENOENT, "The system cannot find the file specified"), reasons.NOT_FOUND),
        (OSError(errno.EIO, "A device attached to the system is not functioning"), reasons.IO_ERROR),
    ])
    def test_windows_errors(self, error, category):
        assert reasons.categorize(error) == category

    def test_every_category_has_words_without_raw_text(self):
        for category in reasons._TEXT:
            sentence = reasons.text(category)
            assert sentence[:1].isupper() and not sentence.endswith(".")
            assert "Errno" not in sentence and "WinError" not in sentence

    def test_a_full_drive_says_how_much_to_free(self):
        assert reasons.disk_full_text(1536 * 1024 * 1024) == "The drive is full. Free up 1.5 GB and try again"
        assert reasons.disk_full_text(0) == reasons.text(reasons.DISK_FULL)


class TestPasswords:
    @pytest.mark.parametrize("password,strength", [
        ("", 0), ("short", 1), ("password123", 2), ("aaaaaaaaaaaa", 2), ("abcdefgh", 2),
        ("abcdefgh12", 2), ("Abcdefgh12", 3), ("Abcdefgh1234", 4), ("Abcdefgh12!x", 5), ("correct horse battery staple", 4),
        ("Correct horse battery staple 9", 5),
    ])
    def test_strength_matches_the_meter(self, password, strength):
        assert passwords.strength(password) == strength

    @pytest.mark.parametrize("mode,password,confirm,finished,blocker", [
        ("encrypt", "", "", False, "Enter the password to encrypt with."),
        ("decrypt", "", "", False, "Enter the password to decrypt with."),
        ("encrypt", "secret12", "", False, "Type the password again to confirm it."),
        ("encrypt", "secret12", "sec", False, "Type the password again to confirm it."),  # still typing
        ("encrypt", "secret12", "sec", True, "The two passwords don't match."),           # left the box
        ("encrypt", "secret12", "secret13", False, "The two passwords don't match."),     # as long: done typing
        ("encrypt", "secret12", "secret12", False, ""),
        ("decrypt", "anything", "", False, ""),
        ("decrypt", "bad \ud800", "", False, "The password contains characters that can't be used."),
    ])
    def test_blockers(self, mode, password, confirm, finished, blocker):
        assert passwords.blocker(mode, password, confirm, finished) == blocker
