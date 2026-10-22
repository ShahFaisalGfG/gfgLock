# v1_writer.py - writes gfgLock v1 files (3.1 and older) for tests; the app can no longer write them.
#
# Layout: salt(16) | nonce(12) or iv(16) | u32 0 | E(name + NUL + data) | tag(16, AEAD only),
# keyed with PBKDF2-SHA256(password, salt, 200000). AES-GCM and AES-CFB use cryptography and
# ChaCha20-Poly1305 uses pycryptodome, as the 3.1.0 Python engine did. The name is raw bytes, so
# tests can store names the app would never write.

import hashlib
import os

from Crypto.Cipher import ChaCha20_Poly1305
from cryptography.hazmat.decrepit.ciphers.modes import CFB
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

ITERATIONS = 200_000
SALT_SIZE = 16
IV_SIZES = {"gcm": 12, "cfb": 16, "chacha": 12}
HEADER_SIZES = {algorithm: SALT_SIZE + size + 4 for algorithm, size in IV_SIZES.items()}


def v1_key(password: str, salt: bytes) -> bytes:
    """The PBKDF2-SHA256 key of a v1 file with this salt."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, dklen=32)


def v1_bytes(algorithm: str, key: bytes, salt: bytes, iv: bytes, name: bytes, data: bytes) -> bytes:
    """The bytes of a whole v1 file storing name and data under this key, salt, and iv."""
    plain = name + b"\0" + data
    if algorithm == "chacha":
        chacha = ChaCha20_Poly1305.new(key=key, nonce=iv)
        body = chacha.encrypt(plain) + chacha.digest()
    elif algorithm == "gcm":
        gcm = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
        body = gcm.update(plain) + gcm.finalize() + gcm.tag
    else:
        cfb = Cipher(algorithms.AES(key), CFB(iv)).encryptor()
        body = cfb.update(plain) + cfb.finalize()
    return salt + iv + bytes(4) + body


def write_v1(path: str, algorithm: str, password: str, name: bytes | str, data: bytes,
             salt: bytes | None = None, iv: bytes | None = None) -> str:
    """Write a v1 file at path (random salt and iv unless given) and return the path."""
    salt = salt if salt is not None else os.urandom(SALT_SIZE)
    iv = iv if iv is not None else os.urandom(IV_SIZES[algorithm])
    raw = name.encode("utf-8") if isinstance(name, str) else name
    with open(path, "wb") as fh:
        fh.write(v1_bytes(algorithm, v1_key(password, salt), salt, iv, raw, data))
    return str(path)
