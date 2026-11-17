# test_signature.py - the update manifest signature check (Windows CNG through ctypes)
#
# The vectors were made once with a throwaway key whose private half was discarded: a signature
# by KEY over MESSAGE. OTHER_KEY is an unrelated key.

import base64

import pytest

from gfglock.utils import signature

KEY = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEvH5xKAcDTn8Ok+I042bAvGWG7WJC
AJoUluXXegzRXuSwovM63dShXLoBIOEpeYzYx9USP377kg56w0g1CvmJmg==
-----END PUBLIC KEY-----
"""
OTHER_KEY = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAERBPneBHpq91VoTtVHZXsUMXkljeK
gCDW68ltOfSLinl6OOJrAMQkX53LMpygNVhOwSH9iepUDaRo92QeDpQgxQ==
-----END PUBLIC KEY-----
"""
MESSAGE = b"gfgRoyal update signature test vector\n"
SIGNATURE = "Q1O0ptfNhoWNMHkhH+5gST30pANcopuC5Y1Wr+v5Yw6k8z+y/cp+dPsZaB0ycxLtsah9Iv7/JXoU0BJi2SUung==\n"


def _raw() -> bytearray:
    return bytearray(base64.b64decode(SIGNATURE))


class TestVerify:
    def test_the_publisher_signature_verifies(self):
        assert signature.verify(MESSAGE, SIGNATURE, [KEY])

    def test_signature_file_bytes_are_accepted(self):
        assert signature.verify(MESSAGE, SIGNATURE.encode("ascii"), [KEY])

    def test_changed_data_fails(self):
        assert not signature.verify(MESSAGE + b" ", SIGNATURE, [KEY])

    def test_changed_signature_fails(self):
        raw = _raw()
        raw[10] ^= 0x01
        assert not signature.verify(MESSAGE, base64.b64encode(bytes(raw)), [KEY])

    def test_another_key_fails(self):
        assert not signature.verify(MESSAGE, SIGNATURE, [OTHER_KEY])

    def test_any_listed_key_may_sign(self):
        """A release signed with the current key can list the next one, so keys can be replaced."""
        assert signature.verify(MESSAGE, SIGNATURE, [OTHER_KEY, KEY])

    def test_no_keys_trust_nothing(self):
        assert not signature.verify(MESSAGE, SIGNATURE, [])


class TestMalformed:
    def test_truncated_signature_is_refused(self):
        with pytest.raises(signature.SignatureError):
            signature.verify(MESSAGE, base64.b64encode(bytes(_raw()[:63])), [KEY])

    def test_signature_that_is_not_base64_is_refused(self):
        with pytest.raises(signature.SignatureError):
            signature.verify(MESSAGE, "not base64!", [KEY])

    def test_key_of_another_type_is_refused(self):
        with pytest.raises(signature.SignatureError):
            signature.public_point("-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----")

    def test_key_point_is_read_from_the_pem(self):
        assert len(signature.public_point(KEY)) == 64
