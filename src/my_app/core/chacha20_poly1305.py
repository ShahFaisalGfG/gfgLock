# chacha20_poly1305.py

# Requires: pycryptodome

import os, time, datetime, io, sys
from multiprocessing import Pool, cpu_count, freeze_support
# pycryptodome's Crypto package may not be resolvable by some linters — silence type checker
from Crypto.Cipher import ChaCha20_Poly1305 
from secrets import token_bytes
from typing import Optional
from utils.gfg_helpers import get_cpu_thread_count, clamp_threads, format_duration, derive_key, safe_print

SALT_SIZE = 16
NONCE_SIZE = 12 
TAG_SIZE = 16

def encrypt_file(path, password, encrypt_name=False, chunk_size=8*1024*1024):
    logs = []
    out_path = None
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if path.endswith('.gfgcha'):
            msg = f"{path} is already encrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        salt = token_bytes(SALT_SIZE)
        nonce = token_bytes(NONCE_SIZE)
        key = derive_key(password, salt)
        cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)

        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = int.from_bytes(token_bytes(4), "big")
            out_name = f"{now}_{rand_part}.gfgcha"
        else:
            base = os.path.splitext(os.path.basename(path))[0]
            out_name = base + ".gfgcha"
        out_path = os.path.join(os.path.dirname(path), out_name)

        with open(path, 'rb') as fin, open(out_path, 'wb') as fout:
            fout.write(salt)
            fout.write(nonce)

            name_meta = os.path.basename(path).encode('utf-8') + b"\0"
            fout.write(cipher.encrypt(name_meta))

            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                fout.write(cipher.encrypt(chunk))

            fout.write(cipher.digest())

        os.remove(path)
        msg = f"Encrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while encrypting {path}: {e}"
        logs.append(msg); safe_print(msg)
        # attempt to clean up partial output if present
        try:
            if out_path and os.path.exists(out_path):
                try: os.remove(out_path)
                except Exception: pass
        except Exception:
            pass
        return False, "\n".join(logs)

def decrypt_file(path, password, chunk_size=8*1024*1024):
    logs = []
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if not path.endswith('.gfgcha'):
            msg = f"{path} is already decrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        total_size = os.path.getsize(path)
        expected_min = SALT_SIZE + NONCE_SIZE + TAG_SIZE + 1
        if total_size < expected_min:
            msg = f"Critical error: {path} is too small or corrupted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        with open(path, 'rb') as fin:
            salt = fin.read(SALT_SIZE)
            nonce = fin.read(NONCE_SIZE)
            data_len = total_size - SALT_SIZE - NONCE_SIZE - TAG_SIZE

            key = derive_key(password, salt)
            cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)

            meta = b""
            got_meta = False
            out_path = None
            read_so_far = 0

            # create output path later after extracting metadata
            temp_out: Optional[io.BufferedWriter] = None

            while read_so_far < data_len:
                to_read = min(chunk_size, data_len - read_so_far)
                chunk = fin.read(to_read)
                if not chunk:
                    break
                read_so_far += len(chunk)
                dec = cipher.decrypt(chunk)
                if not got_meta:
                    idx = dec.find(b'\0')
                    if idx != -1:
                        meta += dec[:idx]
                        original_name = meta.decode('utf-8')
                        out_path = os.path.join(os.path.dirname(path), original_name)
                        # open output file for writing
                        temp_out = open(out_path, 'wb')
                        rest = dec[idx+1:]
                        if rest:
                            temp_out.write(rest)
                        got_meta = True
                    else:
                        meta += dec
                else:
                    assert temp_out is not None
                    temp_out.write(dec)

            tag = fin.read(TAG_SIZE)
            try:
                cipher.verify(tag)
            except Exception as e:
                msg = f"Critical error while decrypting {path}: authentication failed ({e})"
                logs.append(msg); safe_print(msg)
                if temp_out:
                    try: temp_out.close()
                    except Exception: pass
                    if out_path and os.path.exists(out_path):
                        try: os.remove(out_path)
                        except Exception: pass
                return False, "\n".join(logs)

            if temp_out:
                try:
                    temp_out.close()
                except Exception:
                    pass
            else:
                msg = f"Critical error while decrypting {path}: metadata not found"
                logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        os.remove(path)
        msg = f"Decrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while decrypting {path}: {e}"
        logs.append(msg); safe_print(msg)
        return False, "\n".join(logs)

def _enc(args):
    return encrypt_file(*args)


def _dec(args):
    return decrypt_file(*args)

def encrypt_folder(folder, password, encrypt_name=False, threads=1, chunk_size=8*1024*1024):
    start = time.time(); count = 0
    files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs]
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            ok = encrypt_file(fp, password, encrypt_name, chunk_size=chunk_size)
            if isinstance(ok, tuple):
                success = ok[0]
            else:
                success = bool(ok)
            if success:
                count += 1
    else:
        args_list = [(fp, password, encrypt_name, chunk_size) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_enc, args_list):
                if isinstance(ok, tuple):
                    success = ok[0]
                else:
                    success = bool(ok)
                if success:
                    count += 1
    elapsed = time.time() - start
    safe_print(f"{count} files encrypted successfully.\nTime elapsed: {format_duration(elapsed)}")


def decrypt_folder(folder, password, threads=1, chunk_size=8*1024*1024):
    start = time.time(); count = 0
    files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs]
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            ok = decrypt_file(fp, password, chunk_size=chunk_size)
            if isinstance(ok, tuple):
                success = ok[0]
            else:
                success = bool(ok)
            if success:
                count += 1
    else:
        args_list = [(fp, password, chunk_size) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_dec, args_list):
                if isinstance(ok, tuple):
                    success = ok[0]
                else:
                    success = bool(ok)
                if success:
                    count += 1
    elapsed = time.time() - start
    safe_print(f"{count} files decrypted successfully.\nTime elapsed: {format_duration(elapsed)}")

if __name__ == "__main__":
    freeze_support()

    s1_chunk = 1 * 1024 * 1024
    s8_chunk = 8*1024*1024
    s16_chunk = 16*1024*1024
    s18_chunk = 18*1024*1024

    total_threads = get_cpu_thread_count()
    optimal_threads = total_threads // 2
    threads = clamp_threads(optimal_threads)
    safe_print(f"total threads: {total_threads}\nUsing: {threads}")

    # Example usage multiple threads:
    encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=threads, chunk_size=s16_chunk)
    decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=threads, chunk_size=s16_chunk)

