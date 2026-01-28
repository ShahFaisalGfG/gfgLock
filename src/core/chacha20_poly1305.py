# chacha20_poly1305.py

# Requires: pycryptodome

import datetime
import io
import os
import time
from multiprocessing import Pool, freeze_support
from secrets import token_bytes
import struct
from typing import Optional

# pycryptodome's Crypto package may not be resolvable by some linters — silence type checker
from Crypto.Cipher import ChaCha20_Poly1305
from utils import get_cpu_thread_count, clamp_threads, format_duration, derive_key, safe_print
from utils.gfg_helpers import generate_encrypted_name
from core.chunk_processing import FileChunker

SALT_SIZE = 16
NONCE_SIZE = 12 
TAG_SIZE = 16
CHUNK_FIELD_SIZE = 4
BUFFER_SIZE = 512 * 1024  # 512KB buffer for I/O operations (optimized for modern SSDs and parallel throughput)
SMALL_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB threshold: use non-chunked for small files regardless
PROGRESS_UPDATE_INTERVAL = 100 * 1024 * 1024  # Batch progress updates: emit every 100MB instead of per-buffer

def encrypt_file(path, password, encrypt_name=False, chunk_size=None, progress_callback=None):
    logs = []
    out_path = None
    chunker = None
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if path.endswith('.gfgcha'):
            msg = f"{path} is already encrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        # Optimization: for small files, use non-chunked even if chunk_size specified
        file_size = os.path.getsize(path)
        if file_size < SMALL_FILE_THRESHOLD:
            chunk_size = None

        salt = token_bytes(SALT_SIZE)
        nonce = token_bytes(NONCE_SIZE)
        key = derive_key(password, salt)
        cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)

        ext = ".gfgcha"
        out_name = generate_encrypted_name(path, encrypt_name, ext)
        out_path = os.path.join(os.path.dirname(path), out_name)
        chunker = FileChunker()

        with open(path, 'rb', buffering=BUFFER_SIZE) as fin, open(out_path, 'wb', buffering=BUFFER_SIZE) as fout:
            fout.write(salt)
            fout.write(nonce)
            cs = 0 if chunk_size is None else int(chunk_size)
            fout.write(struct.pack('>I', cs))

            name_meta = os.path.basename(path).encode('utf-8') + b"\0"
            fout.write(cipher.encrypt(name_meta))
            if progress_callback:
                progress_callback(float(len(name_meta)))

            if chunk_size is None:
                # Non-chunked: load entire file into memory
                file_data = fin.read()
                fout.write(cipher.encrypt(file_data))
                if progress_callback:
                    progress_callback(float(len(file_data)))
            else:
                effective_chunk = max(chunk_size, BUFFER_SIZE)
                chunks = chunker.split_file(path, effective_chunk)
                for cpath in chunks:
                    with open(cpath, 'rb') as cf:
                        progress_batch = 0.0
                        while True:
                            data = cf.read(BUFFER_SIZE)
                            if not data:
                                break
                            fout.write(cipher.encrypt(data))
                            # Batch progress updates to reduce callback overhead
                            progress_batch += len(data)
                            if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                                progress_callback(float(progress_batch))
                                progress_batch = 0.0
                        # Emit any remaining progress from this chunk
                        if progress_batch > 0 and progress_callback:
                            progress_callback(float(progress_batch))
                    try:
                        os.remove(cpath)
                    except Exception:
                        pass

            fout.write(cipher.digest())

        os.remove(path)
        msg = f"Encrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        # Clean up isolated temp directory
        try:
            chunker.cleanup_temp_dir()
        except Exception:
            pass
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
        # Clean up isolated temp directory
        if chunker:
            try:
                chunker.cleanup_temp_dir()
            except Exception:
                pass
        return False, "\n".join(logs)

def decrypt_file(path, password, chunk_size=None, progress_callback=None):
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

        # Optimization: for small files, use non-chunked even if chunk_size specified
        if total_size < SMALL_FILE_THRESHOLD:
            chunk_size = None

        with open(path, 'rb', buffering=BUFFER_SIZE) as fin:
            salt = fin.read(SALT_SIZE)
            nonce = fin.read(NONCE_SIZE)
            cs_bytes = fin.read(CHUNK_FIELD_SIZE)
            try:
                file_chunk_size = struct.unpack('>I', cs_bytes)[0]
                if file_chunk_size == 0:
                    file_chunk_size = None
            except Exception:
                file_chunk_size = None
            data_len = total_size - SALT_SIZE - NONCE_SIZE - CHUNK_FIELD_SIZE - TAG_SIZE

            key = derive_key(password, salt)
            cipher = ChaCha20_Poly1305.new(key=key, nonce=nonce)

            meta = b""
            got_meta = False
            out_path = None
            temp_out: Optional[io.BufferedWriter] = None

            # prefer chunk size embedded in file header when present
            chunk_size = file_chunk_size

            if chunk_size is None:
                # Non-chunked: load all encrypted data and decrypt at once
                encrypted_data = fin.read(data_len)
                tag = fin.read(TAG_SIZE)
                if progress_callback:
                    progress_callback(float(len(encrypted_data)))
                try:
                    # Prefer decrypt_and_verify when available
                    dec = cipher.decrypt_and_verify(encrypted_data, tag)  # type: ignore[attr-defined]
                except AttributeError:
                    # Fallback if decrypt_and_verify isn't provided by the library
                    dec = cipher.decrypt(encrypted_data)
                    try:
                        cipher.verify(tag)
                    except Exception as e:
                        msg = f"Critical error while decrypting {path}: authentication failed ({e})"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                except Exception as e:
                    msg = f"Critical error while decrypting {path}: authentication failed ({e})"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)

                idx = dec.find(b'\0')
                if idx != -1:
                    try:
                        original_name = dec[:idx].decode('utf-8')
                    except Exception as e:
                        msg = f"Critical error while decrypting {path}: failed to decode metadata ({e})"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                    out_path = os.path.join(os.path.dirname(path), original_name)
                    file_data = dec[idx+1:]
                    with open(out_path, 'wb', buffering=BUFFER_SIZE) as fout:
                        fout.write(file_data)
                    got_meta = True
                else:
                    msg = f"Critical error while decrypting {path}: metadata not found"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)
            else:
                # Chunked: process in blocks, using max(chunk_size, BUFFER_SIZE) for optimal I/O
                effective_chunk = max(chunk_size, BUFFER_SIZE)
                # Stream the encrypted payload directly from the open file
                remaining = data_len
                progress_batch = 0.0
                while remaining > 0:
                    to_read = min(remaining, effective_chunk)
                    chunk = fin.read(to_read)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    # Batch progress updates to reduce callback overhead
                    progress_batch += len(chunk)
                    dec = cipher.decrypt(chunk)
                    if not got_meta:
                        idx = dec.find(b'\0')
                        if idx != -1:
                            meta += dec[:idx]
                            try:
                                original_name = meta.decode('utf-8')
                            except Exception as e:
                                msg = f"Critical error while decrypting {path}: failed to decode metadata ({e})"
                                logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                            out_path = os.path.join(os.path.dirname(path), original_name)
                            # open output file for writing
                            temp_out = open(out_path, 'wb', buffering=BUFFER_SIZE) # type: ignore
                            rest = dec[idx+1:]
                            if rest:
                                temp_out.write(rest) # type: ignore
                            got_meta = True
                        else:
                            meta += dec
                    else:
                        assert temp_out is not None
                        temp_out.write(dec)
                    # Emit batched progress
                    if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                        progress_callback(float(progress_batch))
                        progress_batch = 0.0
                # Emit any remaining progress
                if progress_batch > 0 and progress_callback:
                    progress_callback(float(progress_batch))

                if not got_meta:
                    msg = f"Critical error while decrypting {path}: metadata not found"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)

                # Read and verify authentication tag
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

def encrypt_folder(folder, password, encrypt_name=False, threads=1, chunk_size=None):
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


def decrypt_folder(folder, password, threads=1, chunk_size=None):
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

    s8_chunk = 8*1024*1024 # balanced, recommended default
    s16_chunk = 16*1024*1024 # faster
    s32_chunk = 32*1024*1024 # faster
    s64_chunk = 64*1024*1024 # max for most systems
    s128_chunk = 128*1024*1024 # only for high end systems

    total_threads = get_cpu_thread_count()
    optimal_threads = total_threads // 2
    threads = clamp_threads(optimal_threads)
    safe_print(f"total threads: {total_threads}\nUsing: {threads}")

    # Example usage multiple threads:
    encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=threads, chunk_size=s32_chunk)
    decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=threads, chunk_size=s128_chunk)

