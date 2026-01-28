import os
import sys
import hashlib

# ensure package imports from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core import aes256_gcm_cfb as aes

TEST_FILE = 'tmp_test_large.bin'
PASS = 'strongpassword123'
CHUNK = 1024 * 1024  # 1MB to force chunked processing

# create ~12MB test file
size = 12 * 1024 * 1024
with open(TEST_FILE, 'wb') as f:
    f.write(b'ABCD' * (size // 4))

print('Created test file', TEST_FILE, os.path.getsize(TEST_FILE))

ok, msg = aes.encrypt_file(TEST_FILE, PASS, encrypt_name=False, chunk_size=CHUNK, AEAD=True)
print('Encrypt:', ok)
print(msg)
if not ok:
    sys.exit(2)

enc_path = os.path.splitext(TEST_FILE)[0] + '.gfglock'
if not os.path.exists(enc_path):
    print('Encrypted file not found:', enc_path)
    sys.exit(2)

ok2, msg2 = aes.decrypt_file(enc_path, PASS, chunk_size=CHUNK)
print('Decrypt:', ok2)
print(msg2)
if not ok2:
    sys.exit(3)

# verify contents
if not os.path.exists(TEST_FILE):
    print('Decrypted file missing')
    sys.exit(4)

with open(TEST_FILE, 'rb') as f:
    data = f.read()

expected_hash = hashlib.sha256(b'ABCD' * (size // 4)).hexdigest()
actual_hash = hashlib.sha256(data).hexdigest()
print('Expected SHA256:', expected_hash)
print('Actual   SHA256:', actual_hash)

if expected_hash == actual_hash:
    print('SUCCESS: roundtrip matched')
    # cleanup
    try:
        os.remove(TEST_FILE)
    except Exception:
        pass
    sys.exit(0)
else:
    print('FAIL: mismatch')
    sys.exit(5)
