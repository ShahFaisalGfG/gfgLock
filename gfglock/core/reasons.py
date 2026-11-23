# reasons.py - what happened to a file, in plain words with a next step (stdlib only).
#
# The engines, the file format, and Windows each describe a failure in their own terms
# ("authentication failed", "unsupported chunk size", "[WinError 32] The process cannot access the
# file"). file_ops turns every one of them into a category below and its sentence, which the file
# list, the run summary, and the command line show; the original text goes to the log.

from __future__ import annotations

import errno

from gfglock.utils.helpers import format_bytes

WRONG_PASSWORD = "wrong_password"
IN_USE = "in_use"
ACCESS_DENIED = "access_denied"
DISK_FULL = "disk_full"
DAMAGED = "damaged"
NEWER_VERSION = "newer_version"
NOT_FOUND = "not_found"
READ_ONLY = "read_only"
CHANGED = "changed"
UNSAFE_NAME = "unsafe_name"
NAME_NOT_RESTORABLE = "name_not_restorable"
NAME_TOO_LONG = "name_too_long"
TOO_LARGE = "too_large"
IO_ERROR = "io_error"
UNKNOWN = "unknown"
# Skips: the file was left as it was on purpose.
LINK = "link"
HARD_LINK = "hard_link"
TEMP_FILE = "temp_file"
ALREADY_ENCRYPTED = "already_encrypted"
NOT_ENCRYPTED = "not_encrypted"
STOPPED = "stopped"
# Notes on a finished file.
CFB_KEPT = "cfb_kept"
VERIFIED = "verified"

# category -> (short label for a run summary, the sentence for the file)
_TEXT: dict[str, tuple[str, str]] = {
    WRONG_PASSWORD: ("wrong password", "Wrong password, or the file is damaged"),
    IN_USE: ("in use", "The file is open in another program. Close it and try again"),
    ACCESS_DENIED: ("access denied", "Windows denied access to the file or its folder. "
                                     "Check its permissions, or work on a copy in a folder of your own"),
    DISK_FULL: ("drive full", "The drive is full. Free up some space and try again"),
    DAMAGED: ("damaged", "The file is damaged, or it wasn't made by gfgLock"),
    NEWER_VERSION: ("from a newer gfgLock", "The file was made by a newer gfgLock. "
                                            "Update gfgLock from About, then try again"),
    NOT_FOUND: ("not found", "File not found; it may have been moved or deleted"),
    READ_ONLY: ("read-only", "The file is read-only. Clear Read-only in its Properties and try again"),
    CHANGED: ("changed while reading", "The file changed while gfgLock was reading it, so nothing was changed. "
                                       "Try again once no other program is using it"),
    UNSAFE_NAME: ("unsafe name", "The name stored in the file isn't a safe Windows file name, so it wasn't restored"),
    NAME_NOT_RESTORABLE: ("name can't be restored", "The file name couldn't be restored safely when decrypting. "
                                                    "Rename the file and try again"),
    NAME_TOO_LONG: ("name too long", "The name is too long to add the encrypted extension. "
                                     "Turn on Hide file names or shorten the name"),
    TOO_LARGE: ("too large", "The file is too large for gfgLock"),
    IO_ERROR: ("read or write error", "Windows couldn't read or write the file. Check the drive and try again"),
    UNKNOWN: ("unexpected error", "Something unexpected went wrong with this file. Turn on logs to see the details"),
    LINK: ("link", "Links are skipped; add the file the link points to"),
    HARD_LINK: ("hard link", "Other hard links to this file would stay readable"),
    TEMP_FILE: ("temporary file", "Temporary file left by an unfinished job"),
    ALREADY_ENCRYPTED: ("already encrypted", "Already encrypted"),
    NOT_ENCRYPTED: ("not encrypted", "Not an encrypted gfgLock file"),
    STOPPED: ("stopped", "Stopped before it finished; the file was not changed"),
    CFB_KEPT: ("kept", "The .gfglck file was kept: its old format can't confirm the password. "
                       "Delete it once the decrypted file opens"),
    VERIFIED: ("checked", "The password is right and the file is intact"),
}

# Windows error codes (OSError.winerror) and what they mean for a file.
_WINERRORS = {
    2: NOT_FOUND, 3: NOT_FOUND,            # file or path not found
    5: ACCESS_DENIED, 19: ACCESS_DENIED,   # access denied, write-protected media
    32: IN_USE, 33: IN_USE,                # sharing and lock violations
    39: DISK_FULL, 112: DISK_FULL,         # handle disk full, disk full
    1784: IO_ERROR, 23: IO_ERROR,          # invalid user buffer, CRC error (bad sector)
}
_ERRNOS = {errno.ENOSPC: DISK_FULL, errno.EACCES: ACCESS_DENIED, errno.EPERM: ACCESS_DENIED,
           errno.ENOENT: NOT_FOUND, errno.EROFS: ACCESS_DENIED}
# Words in the engines' and the format's own messages, checked in this order.
_PHRASES = (
    ("wrong password", WRONG_PASSWORD),
    ("authentication failed", WRONG_PASSWORD),
    ("open in another program", IN_USE),
    ("newer gfglock", NEWER_VERSION),
    ("disk full", DISK_FULL),
    ("changed size while it was being read", CHANGED),
    ("too large", TOO_LARGE),
    ("truncated", DAMAGED),
    ("corrupted", DAMAGED),
    ("too small to be a valid", DAMAGED),
    ("not a gfglock", DAMAGED),
    ("unsupported", DAMAGED),
    ("doesn't know", NEWER_VERSION),
    ("decryption failed", DAMAGED),
    ("could not read", IO_ERROR),
    ("could not write", IO_ERROR),
    ("could not finish writing", IO_ERROR),
    ("could not create", IO_ERROR),
)


def label(category: str) -> str:
    """A few words for a run summary: '6 wrong password, 3 in use'."""
    return _TEXT.get(category, _TEXT[UNKNOWN])[0]


def text(category: str) -> str:
    """The sentence shown for a file, without a closing period."""
    return _TEXT.get(category, _TEXT[UNKNOWN])[1]


def disk_full_text(needed: int) -> str:
    """The drive-full sentence with the space still needed, such as 'Free up 1.2 GB'."""
    if needed <= 0:
        return text(DISK_FULL)
    return f"The drive is full. Free up {format_bytes(needed, strip_zeros=True)} and try again"


def categorize(error: BaseException | str) -> str:
    """The category of an engine message, a file format error, or an OSError."""
    if isinstance(error, OSError):
        winerror = getattr(error, "winerror", None)
        if winerror in _WINERRORS:
            return _WINERRORS[winerror]
        if error.errno in _ERRNOS:
            return _ERRNOS[error.errno]
        return IO_ERROR
    lowered = str(error).lower()
    for phrase, category in _PHRASES:
        if phrase in lowered:
            return category
    return UNKNOWN

