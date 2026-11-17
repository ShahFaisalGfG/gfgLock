# signature.py - verifies the release signature on update manifests (stdlib and Windows CNG only)
#
# Shared by gfgLock, gfgShield, and CC-Gen-Ultimate: keep the copies identical. Each release's
# update.json is signed in CI with ECDSA P-256 over SHA-256 (scripts/sign_update.py); the signature
# file holds the raw r||s value (64 bytes) in base64. The apps carry the public key as the PEM text
# `openssl ec -pubout` prints and verify with Windows' own crypto (bcrypt.dll), so no crypto
# library has to be bundled.

import base64
import binascii
import ctypes
import hashlib
from collections.abc import Iterable
from ctypes import wintypes

# DER header of a P-256 SubjectPublicKeyInfo; the 65 bytes after it are 0x04 || X || Y.
_SPKI_P256_PREFIX = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")
_POINT_SIZE = 32
_SIGNATURE_SIZE = 2 * _POINT_SIZE
_ECDSA_P256 = "ECDSA_P256"
_ECCPUBLIC_BLOB = "ECCPUBLICBLOB"
_ECDSA_PUBLIC_P256_MAGIC = 0x31534345  # "ECS1"
_STATUS_SUCCESS = 0
_STATUS_INVALID_SIGNATURE = 0xC000A000

_bcrypt = ctypes.WinDLL("bcrypt")
_BCRYPT_HANDLE = ctypes.c_void_p
_NTSTATUS = ctypes.c_ulong


def _api(name: str, *argtypes):
    function = getattr(_bcrypt, name)
    function.restype = _NTSTATUS
    function.argtypes = list(argtypes)
    return function


_OpenAlgorithmProvider = _api("BCryptOpenAlgorithmProvider", ctypes.POINTER(_BCRYPT_HANDLE), wintypes.LPCWSTR,
                              wintypes.LPCWSTR, wintypes.ULONG)
_CloseAlgorithmProvider = _api("BCryptCloseAlgorithmProvider", _BCRYPT_HANDLE, wintypes.ULONG)
_ImportKeyPair = _api("BCryptImportKeyPair", _BCRYPT_HANDLE, _BCRYPT_HANDLE, wintypes.LPCWSTR,
                      ctypes.POINTER(_BCRYPT_HANDLE), ctypes.c_char_p, wintypes.ULONG, wintypes.ULONG)
_DestroyKey = _api("BCryptDestroyKey", _BCRYPT_HANDLE)
_VerifySignature = _api("BCryptVerifySignature", _BCRYPT_HANDLE, ctypes.c_void_p, ctypes.c_char_p, wintypes.ULONG,
                        ctypes.c_char_p, wintypes.ULONG, wintypes.ULONG)


class SignatureError(Exception):
    """A key or signature that can't be used, or Windows refused to check one."""


def public_point(pem: str) -> bytes:
    """X || Y (64 bytes) of a P-256 public key in PEM (SubjectPublicKeyInfo) form."""
    body = "".join(line.strip() for line in pem.strip().splitlines() if line.strip() and "-----" not in line)
    try:
        der = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as error:
        raise SignatureError(f"the public key is not valid base64: {error}") from error
    if len(der) != len(_SPKI_P256_PREFIX) + 1 + _SIGNATURE_SIZE or not der.startswith(_SPKI_P256_PREFIX):
        raise SignatureError("the public key is not an uncompressed P-256 key")
    point = der[len(_SPKI_P256_PREFIX):]
    if point[0] != 0x04:
        raise SignatureError("the public key is not an uncompressed P-256 key")
    return point[1:]


def decode_signature(text: bytes | str) -> bytes:
    """The raw r || s signature in a .sig file (base64 text, surrounding whitespace allowed)."""
    try:
        value = text.decode("ascii") if isinstance(text, bytes) else text
        raw = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError, UnicodeDecodeError) as error:
        raise SignatureError(f"the signature is not valid base64: {error}") from error
    if len(raw) != _SIGNATURE_SIZE:
        raise SignatureError(f"the signature has {len(raw)} bytes, not {_SIGNATURE_SIZE}")
    return raw


def verify(data: bytes, signature: bytes | str, public_keys: Iterable[str]) -> bool:
    """True when `signature` (the .sig file's text) signs `data` under one of `public_keys` (PEM).

    Several keys are accepted so a key can be replaced: a release signed with the old key ships the
    new one. A malformed signature or key raises SignatureError; a valid one that doesn't match is False.
    """
    raw = decode_signature(signature)
    digest = hashlib.sha256(data).digest()
    return any(_verify_point(digest, raw, public_point(pem)) for pem in public_keys)


def _verify_point(digest: bytes, signature: bytes, point: bytes) -> bool:
    """Check one signature against one public key with bcrypt.dll."""
    algorithm = _BCRYPT_HANDLE()
    _check(_OpenAlgorithmProvider(ctypes.byref(algorithm), _ECDSA_P256, None, 0), "open ECDSA P-256")
    try:
        blob = (_ECDSA_PUBLIC_P256_MAGIC.to_bytes(4, "little") + _POINT_SIZE.to_bytes(4, "little") + point)
        key = _BCRYPT_HANDLE()
        _check(_ImportKeyPair(algorithm, None, _ECCPUBLIC_BLOB, ctypes.byref(key), blob, len(blob), 0),
               "import the public key")
        try:
            status = _VerifySignature(key, None, digest, len(digest), signature, len(signature), 0)
        finally:
            _DestroyKey(key)
    finally:
        _CloseAlgorithmProvider(algorithm, 0)
    if status == _STATUS_INVALID_SIGNATURE:
        return False
    _check(status, "check the signature")
    return True


def _check(status: int, action: str) -> None:
    if status != _STATUS_SUCCESS:
        raise SignatureError(f"Windows could not {action} (status 0x{status:08X})")
