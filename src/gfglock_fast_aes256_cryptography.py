# gfglock_fast_aes256_cryptography.py

# install requirements using requirements.txt(pip install -r requirements.txt) or run below command in terminal.
# pip install cryptography

import hashlib
import os, time, datetime, io, sys
from multiprocessing import Pool, cpu_count, freeze_support
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from secrets import token_bytes
from typing import Optional
from gfg_helpers import get_cpu_thread_count, clamp_threads, format_duration, derive_key, safe_print

SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16


def encrypt_file(path, password, encrypt_name=False, chunk_size=8*1024*1024, AEAD=True):
    logs = []
    out_path = None
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if path.endswith(".gfglock"):
            msg = f"{path} is already encrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = int.from_bytes(token_bytes(4), "big")
            out_name = f"{now}_{rand_part}.gfglock"
        else:
            base = os.path.splitext(os.path.basename(path))[0]
            out_name = base + ".gfglock"
        out_path = os.path.join(os.path.dirname(path), out_name)

        with open(path, "rb") as fin, open(out_path, "wb") as fout:
            if AEAD:
                # GCM mode with AEAD authentication
                fout.write(b'\x01')  # Mode byte: 0x01 for GCM
                
                salt = token_bytes(SALT_SIZE)
                nonce = token_bytes(NONCE_SIZE)
                key = derive_key(password, salt)
                cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
                encryptor = cipher.encryptor()

                fout.write(salt)
                fout.write(nonce)

                name_meta = os.path.basename(path).encode("utf-8") + b"\0"
                fout.write(encryptor.update(name_meta))

                while True:
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fout.write(encryptor.update(chunk))

                fout.write(encryptor.finalize())
                fout.write(encryptor.tag)
            else:
                # CFB mode without authentication (streaming, faster)
                fout.write(b'\x00')  # Mode byte: 0x00 for CFB
                
                iv = token_bytes(16)
                key = hashlib.sha256(password.encode('utf-8')).digest()  # Simple key for CFB
                cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
                encryptor = cipher.encryptor()

                fout.write(iv)

                name_meta = os.path.basename(path).encode("utf-8") + b"\0"
                fout.write(encryptor.update(name_meta))

                while True:
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fout.write(encryptor.update(chunk))

                fout.write(encryptor.finalize())

        os.remove(path)
        msg = f"Encrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while encrypting {path}: {e}"
        logs.append(msg); safe_print(msg)
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
        if not path.endswith(".gfglock"):
            msg = f"{path} is already decrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        total_size = os.path.getsize(path)
        if total_size < 2:
            msg = f"Critical error: {path} is too small or corrupted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        with open(path, "rb") as fin:
            mode_byte = fin.read(1)
            
            if mode_byte == b'\x01':
                # GCM mode (AEAD) - requires full file in memory
                expected_min = 1 + SALT_SIZE + NONCE_SIZE + TAG_SIZE + 1
                if total_size < expected_min:
                    msg = f"Critical error: {path} is too small or corrupted"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)

                salt = fin.read(SALT_SIZE)
                nonce = fin.read(NONCE_SIZE)
                data_len = total_size - 1 - SALT_SIZE - NONCE_SIZE - TAG_SIZE

                key = derive_key(password, salt)
                encrypted_data = fin.read(data_len)
                tag = fin.read(TAG_SIZE)
                
                try:
                    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
                    decryptor = cipher.decryptor()
                    decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
                except Exception as e:
                    msg = f"Critical error while decrypting {path}: authentication failed ({e})"
                    logs.append(msg); safe_print(msg)
                    return False, "\n".join(logs)

                # Parse metadata
                idx = decrypted.find(b'\0')
                if idx == -1:
                    msg = f"Critical error while decrypting {path}: metadata not found"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)

                original_name = decrypted[:idx].decode('utf-8')
                out_path = os.path.join(os.path.dirname(path), original_name)
                file_data = decrypted[idx+1:]

                with open(out_path, "wb") as fout:
                    fout.write(file_data)

            elif mode_byte == b'\x00':
                # CFB mode (non-AEAD) - streaming decryption
                expected_min = 1 + 16 + 1  # mode + IV + at least 1 byte data
                if total_size < expected_min:
                    msg = f"Critical error: {path} is too small or corrupted"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)

                iv = fin.read(16)
                key = hashlib.sha256(password.encode('utf-8')).digest()
                cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
                decryptor = cipher.decryptor()

                meta = b""
                got_meta = False
                out_path = None
                temp_out: Optional[io.BufferedWriter] = None

                while True:
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    dec = decryptor.update(chunk)
                    
                    if not got_meta:
                        idx = dec.find(b'\0')
                        if idx != -1:
                            meta += dec[:idx]
                            original_name = meta.decode('utf-8')
                            out_path = os.path.join(os.path.dirname(path), original_name)
                            temp_out = open(out_path, 'wb')
                            rest = dec[idx+1:]
                            if rest:
                                temp_out.write(rest)
                            got_meta = True
                        else:
                            meta += dec
                    else:
                        if temp_out:
                            temp_out.write(dec)

                decryptor.finalize()

                if not got_meta:
                    msg = f"Critical error while decrypting {path}: metadata not found"
                    logs.append(msg); safe_print(msg)
                    if temp_out:
                        try: temp_out.close()
                        except Exception: pass
                    return False, "\n".join(logs)

                if temp_out:
                    try:
                        temp_out.close()
                    except Exception:
                        pass
            else:
                msg = f"Critical error while decrypting {path}: unknown file format"
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

def encrypt_folder(folder, password, encrypt_name=False, threads=1, chunk_size=8*1024*1024, AEAD=True):
    start = time.time(); count = 0
    files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs]
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            ok = encrypt_file(fp, password, encrypt_name, chunk_size=chunk_size, AEAD=AEAD)
            if isinstance(ok, tuple):
                success = ok[0]
            else:
                success = bool(ok)
            if success:
                count += 1
    else:
        args_list = [(fp, password, encrypt_name, chunk_size, AEAD) for fp in files]
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

# Use chunk Sizes between 1-64mb while on moderns SSDs & NVMes you can use upto 128mb
    s1_chunk = 1 * 1024 * 1024 # very gentle, but slower
    s8_chunk = 8*1024*1024 # balanced, recommended default
    s16_chunk = 16*1024*1024 # faster
    s18_chunk = 18*1024*1024 # faster

    total_threads = get_cpu_thread_count()
    # using half of total threads for balanced performance to avoid system overload
    optimal_threads = total_threads // 2
    threads = clamp_threads(optimal_threads)
    print(f"total threads: {total_threads}\nUsing: {threads}")

    # Example usage multiple threads:
    encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=threads, chunk_size=s18_chunk, AEAD=False)
    decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=threads, chunk_size=s18_chunk)

    # Example usage single thread & 8mb(default chunk size):
    # encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True)
    # decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123")