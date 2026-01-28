import os
import hashlib
import time
from secrets import token_bytes
from pathlib import Path

from core.aes256_gcm_cfb import encrypt_file, decrypt_file
from core import chacha20_poly1305 as chacha_mod

TMP_DIR = Path("src/tests/tmp_test_dir")
TMP_DIR.mkdir(parents=True, exist_ok=True)

PASSWORD = "testpassword123"
CHUNK = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(64 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def make_file(path: Path, size: int):
    with open(path, "wb") as f:
        f.write(token_bytes(size))


def find_new(before, after):
    added = after - before
    if not added:
        return None
    return list(added)[0]


def run_roundtrip(test_name, create_size, encrypt_fn, decrypt_fn, ae=False):
    print(f"\n=== {test_name} ===")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    orig = TMP_DIR / f"orig_{test_name}.bin"
    make_file(orig, create_size)
    orig_hash = sha256(orig)

    before = set(p for p in TMP_DIR.iterdir())

    ok, logs = encrypt_fn(str(orig), PASSWORD, encrypt_name=False, chunk_size=CHUNK, AEAD=ae) if encrypt_fn.__name__ == 'encrypt_file' and encrypt_fn.__module__.endswith('aes256_gcm_cfb') else encrypt_fn(str(orig), PASSWORD, encrypt_name=False, chunk_size=CHUNK)
    print("encrypt ->", ok)
    print(logs)

    after = set(p for p in TMP_DIR.iterdir())
    enc = find_new(before, after)
    if enc is None:
        print("Encrypted file not found; aborting")
        return False

    ok2, logs2 = decrypt_fn(str(enc), PASSWORD, chunk_size=None) if decrypt_fn.__name__ == 'decrypt_file' and decrypt_fn.__module__.endswith('aes256_gcm_cfb') else decrypt_fn(str(enc), PASSWORD, chunk_size=None)
    print("decrypt ->", ok2)
    print(logs2)

    # decrypted file should be recreated with the original name
    dec = orig
    if not dec.exists():
        print("Decrypted file not found; aborting")
        return False
    dec_hash = sha256(dec)
    print(f"orig_hash={orig_hash}\ndec_hash ={dec_hash}")
    result = orig_hash == dec_hash
    print("MATCH:" , result)

    # cleanup
    try:
        for p in [orig, enc, dec]:
            if p.exists():
                p.unlink()
    except Exception:
        pass
    return result


if __name__ == '__main__':
    all_ok = True
    # small file for speed: 1 MB
    size = 1 * 1024 * 1024

    # AES-GCM
    ok = run_roundtrip('aes_gcm', size, encrypt_file, decrypt_file, ae=True)
    all_ok = all_ok and ok

    # AES-CFB
    # encrypt_file (same module) with AEAD=False
    ok = run_roundtrip('aes_cfb', size, encrypt_file, decrypt_file, ae=False)
    all_ok = all_ok and ok

    # ChaCha20-Poly1305
    ok = run_roundtrip('chacha', size, chacha_mod.encrypt_file, chacha_mod.decrypt_file, ae=True)
    all_ok = all_ok and ok

    print('\nALL OK:' , all_ok)
    if not all_ok:
        raise SystemExit(1)
