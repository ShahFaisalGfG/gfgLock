"""Sign a release file for the in-app updater: ECDSA P-256 over SHA-256, saved as base64 raw r||s.

Usage: python scripts/sign_update.py FILE [--expect SOURCE]

The private key (PEM, SEC1 or PKCS8) comes from the UPDATE_SIGNING_KEY environment variable, a
repository secret in CI. The signature goes to FILE.sig. The script checks its own output with the
matching public key and prints that key, so the release log shows which key signed the file.

--expect names the source file that embeds the app's public keys. Signing stops when the key's
public half is not in it: a release the app can't verify would leave every copy unable to update.

Shared by every gfgRoyal repository that publishes signed updates; keep the copies identical.
Needs the `cryptography` package (the release workflow installs it).
"""

import base64
import os
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

KEY_VARIABLE = "UPDATE_SIGNING_KEY"
_POINT_SIZE = 32


def load_key(pem: str) -> ec.EllipticCurvePrivateKey:
    """The P-256 private key in `pem`; anything else raises ValueError."""
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("the key is not an ECDSA P-256 (prime256v1) private key")
    return key


def sign(data: bytes, key: ec.EllipticCurvePrivateKey) -> str:
    """Base64 of the raw r||s signature (64 bytes) of `data`."""
    r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
    return base64.b64encode(r.to_bytes(_POINT_SIZE, "big") + s.to_bytes(_POINT_SIZE, "big")).decode("ascii")


def verify(data: bytes, signature: str, public_key: ec.EllipticCurvePublicKey) -> bool:
    """True when `signature` (as sign() writes it) signs `data` under `public_key`."""
    raw = base64.b64decode(signature, validate=True)
    if len(raw) != 2 * _POINT_SIZE:
        return False
    der = encode_dss_signature(int.from_bytes(raw[:_POINT_SIZE], "big"), int.from_bytes(raw[_POINT_SIZE:], "big"))
    try:
        public_key.verify(der, data, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def public_pem(key: ec.EllipticCurvePrivateKey) -> str:
    """The public key as `openssl ec -pubout` prints it: the form the apps embed."""
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def embedded(public: str, source_text: str) -> bool:
    """True when every base64 line of the `public` PEM appears in `source_text`."""
    lines = [line.strip() for line in public.strip().splitlines() if line.strip() and "-----" not in line]
    return bool(lines) and all(line in source_text for line in lines)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--expect":
        target, expect = argv[0], argv[2]
    elif len(argv) == 1:
        target, expect = argv[0], ""
    else:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    pem = os.environ.get(KEY_VARIABLE, "").strip()
    if not pem:
        print(f"{KEY_VARIABLE} is not set, so the release can't be signed.", file=sys.stderr)
        return 1
    try:
        key = load_key(pem)
        with open(target, "rb") as fh:
            data = fh.read()
        source_text = ""
        if expect:
            with open(expect, encoding="utf-8") as fh:
                source_text = fh.read()
    except (OSError, ValueError, TypeError) as error:
        print(f"Can't sign {target}: {error}", file=sys.stderr)
        return 1
    if expect and not embedded(public_pem(key), source_text):
        print(f"The signing key's public half is not in {expect}; add it there before releasing:\n"
              f"{public_pem(key)}", file=sys.stderr)
        return 1
    signature = sign(data, key)
    if not verify(data, signature, key.public_key()):
        print("The new signature did not verify; nothing was written.", file=sys.stderr)
        return 1
    with open(target + ".sig", "w", encoding="ascii", newline="\n") as fh:
        fh.write(signature + "\n")
    print(f"Signed {target} with:\n{public_pem(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
