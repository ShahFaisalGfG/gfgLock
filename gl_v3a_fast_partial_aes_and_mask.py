# gfglock_fast_mask.py
import os
import hashlib
import datetime
import time
from multiprocessing import Pool, cpu_count
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

PARTIAL_AES_BYTES = 2 * 1024 * 1024  # 2 MB encrypted, rest masked
MASK_CHUNK = 4 * 1024 * 1024         # mask in 4 MB chunks

def clamp_threads(threads):
    try:
        max_safe = max(cpu_count() - 1, 1)
    except Exception:
        max_safe = 1
    if not isinstance(threads, int) or threads < 1:
        return 1
    return min(threads, max_safe)

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        mins, secs = divmod(seconds, 60)
        return f"{mins} mins {secs} sec"
    else:
        hours, remainder = divmod(seconds, 3600)
        mins, secs = divmod(remainder, 60)
        return f"{hours} hrs {mins} mins {secs} sec"

def derive_key(password):
    return hashlib.sha256(password.encode()).digest()

def generate_mask_stream(key: bytes, iv: bytes, length: int) -> bytes:
    # Generate a simple keystream using AES-CTR; fast and reversible
    cipher = AES.new(key, AES.MODE_CTR, nonce=iv[:8])
    return cipher.encrypt(b"\x00" * length)

def encrypt_file(path, password, encrypt_name=False):
    try:
        if not os.path.exists(path):
            print(f"Critical error: {path} not found")
            return False
        if path.endswith(".gfglock"):
            print(f"{path} is already encrypted")
            return False

        key = derive_key(password)
        iv = get_random_bytes(16)

        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = str(int.from_bytes(get_random_bytes(4), 'big'))
            out_name = f"{now}_{rand_part}.gfglock"
        else:
            base = os.path.splitext(os.path.basename(path))[0]
            out_name = base + ".gfglock"

        out_path = os.path.join(os.path.dirname(path), out_name)

        with open(path, "rb") as fin, open(out_path, "wb") as fout:
            # Write IV
            fout.write(iv)
            # Write metadata
            name_meta = os.path.basename(path).encode("utf-8") + b"\0"
            cipher_meta = AES.new(key, AES.MODE_CFB, iv=iv)
            fout.write(cipher_meta.encrypt(name_meta))

            # Encrypt first PARTIAL_AES_BYTES (or file size if smaller)
            cipher_head = AES.new(key, AES.MODE_CFB, iv=iv)
            remaining = PARTIAL_AES_BYTES
            while remaining > 0:
                chunk = fin.read(min(remaining, MASK_CHUNK))
                if not chunk:
                    break
                fout.write(cipher_head.encrypt(chunk))
                remaining -= len(chunk)

            # Mask the rest with a reversible keystream (fast)
            tail = fin.read()
            if tail:
                keystream = generate_mask_stream(key, iv, len(tail))
                masked = bytes(a ^ b for a, b in zip(tail, keystream))
                fout.write(masked)

        os.remove(path)
        print(f"Encrypted (fast): {path} -> {out_path}")
        return True

    except Exception as e:
        print(f"Critical error while encrypting {path}: {e}")
        return False

def decrypt_file(path, password):
    try:
        if not os.path.exists(path):
            print(f"Critical error: {path} not found")
            return False
        if not path.endswith(".gfglock"):
            print(f"{path} is already decrypted")
            return False

        key = derive_key(password)

        with open(path, "rb") as fin:
            iv = fin.read(16)
            # Read metadata
            meta_dec = AES.new(key, AES.MODE_CFB, iv=iv)
            meta = b""
            while True:
                b = fin.read(1)
                if not b:
                    raise ValueError("Missing metadata")
                db = meta_dec.decrypt(b)
                if db == b"\0":
                    break
                meta += db
            original_name = meta.decode("utf-8")

            out_path = os.path.join(os.path.dirname(path), original_name)
            with open(out_path, "wb") as fout:
                # Decrypt first PARTIAL_AES_BYTES
                dec_head = AES.new(key, AES.MODE_CFB, iv=iv)
                remaining = PARTIAL_AES_BYTES
                while remaining > 0:
                    chunk = fin.read(min(remaining, MASK_CHUNK))
                    if not chunk:
                        break
                    fout.write(dec_head.decrypt(chunk))
                    remaining -= len(chunk)

                # Unmask the rest
                tail = fin.read()
                if tail:
                    keystream = generate_mask_stream(key, iv, len(tail))
                    unmasked = bytes(a ^ b for a, b in zip(tail, keystream))
                    fout.write(unmasked)

        os.remove(path)
        print(f"Decrypted (fast): {path} -> {out_path}")
        return True

    except Exception as e:
        print(f"Critical error while decrypting {path}: {e}")
        return False

def _enc(args):
    return encrypt_file(*args)

def _dec(args):
    return decrypt_file(*args)

def encrypt_folder(folder, password, encrypt_name=False, threads=1):
    start = time.time()
    count = 0
    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            if encrypt_file(fp, password, encrypt_name):
                count += 1
    else:
        args_list = [(fp, password, encrypt_name) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_enc, args_list):
                if ok:
                    count += 1
    elapsed = time.time() - start
    print(f"{count} files encrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

def decrypt_folder(folder, password, threads=1):
    start = time.time()
    count = 0
    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            if decrypt_file(fp, password):
                count += 1
    else:
        args_list = [(fp, password) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_dec, args_list):
                if ok:
                    count += 1
    elapsed = time.time() - start
    print(f"{count} files decrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

# Example usage:
# encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=4)
# decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=4)