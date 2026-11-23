# passwords.py - the rules a password meets before a run starts, and how strong it looks (stdlib only).
#
# The window's password boxes and the command line ask the same things: a password at all, the
# same one typed twice when encrypting, and nothing that can't be turned into a key. The strength
# meter is advice only; a weak password is allowed.

from __future__ import annotations

import re
import unicodedata

MIN_LENGTH = 8
STRENGTH_NAMES = ("", "Very weak", "Weak", "Fair", "Good", "Strong")
WEAK_HINT = "Longer is stronger: try 12 or more characters, or a few unrelated words."
_COMMON = ("password", "123456", "qwerty", "letmein", "iloveyou", "admin", "welcome", "abc123", "111111")
_KINDS = (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"[0-9]"), re.compile(r"[^A-Za-z0-9]"))


def strength(password: str) -> int:
    """0 empty, 1 very weak (under 8 characters), 2 weak, 3 fair, 4 good, 5 strong."""
    if not password:
        return 0
    if len(password) < MIN_LENGTH:
        return 1
    lowered = password.lower()
    if any(word in lowered for word in _COMMON) or len(set(password)) == 1:
        return 2
    kinds = sum(1 for kind in _KINDS if kind.search(password))
    score = (2 if len(password) >= 12 else 1) + (1 if len(password) >= 16 else 0) + max(0, kinds - 1)
    return 2 if score <= 2 else 3 if score <= 3 else 4 if score <= 4 else 5


def unusable(password: str) -> str:
    """Why a password can't be turned into a key ("" when it can): a lone surrogate, say."""
    try:
        unicodedata.normalize("NFC", password).encode("utf-8")
    except UnicodeEncodeError:
        return "The password contains characters that can't be used."
    return ""


def blocker(mode: str, password: str, confirm: str = "", confirm_finished: bool = True) -> str:
    """What is still wrong with the password before a run, or "" when it is ready.

    Encrypting needs the password typed twice. A mismatch shows once the second copy is as long as
    the first, or after Enter or leaving the box, not while it is still being typed.
    """
    if not password:
        return f"Enter the password to {'encrypt' if mode == 'encrypt' else 'decrypt'} with."
    problem = unusable(password)
    if problem:
        return problem
    if mode != "encrypt":
        return ""
    if mismatch(password, confirm, confirm_finished):
        return "The two passwords don't match."
    if confirm != password:
        return "Type the password again to confirm it."
    return ""


def mismatch(password: str, confirm: str, confirm_finished: bool = True) -> bool:
    """True when the confirmation is complete enough to tell, and differs from the password."""
    return bool(confirm) and confirm != password and (confirm_finished or len(confirm) >= len(password))
