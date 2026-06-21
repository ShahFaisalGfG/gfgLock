# aes256_gcm_cfb.py - AES-256 GCM and CFB encryption/decryption.
# Native C++ path (via native_bridge) is used when the .pyd is present;
# the Python/cryptography fallback is used otherwise.

import os
import time
from functools import partial
from multiprocessing import Pool, freeze_support
from typing import Callable, Optional

from gfglock.core import native_bridge
from gfglock.utils.helpers import (
    clamp_threads,
    format_duration,
    safe_print,
)


def encrypt_file(
    path: str,
    password: str,
    encrypt_name: bool = False,
    chunk_size=None,
    AEAD: bool = True,
    progress_callback: Optional[Callable] = None,
) -> tuple[bool, str]:
    """Encrypt a single file using AES-256 GCM (AEAD) or CFB."""
    cs = 0 if chunk_size is None else int(chunk_size)
    mode = "GCM" if AEAD else "CFB"
    if native_bridge.NATIVE_AVAILABLE:
        safe_print(f"[AES-{mode}] Encrypt: native C++ path  →  {os.path.basename(path)}")
        fn = native_bridge.encrypt_gcm if AEAD else native_bridge.encrypt_cfb
        ok, msg = fn(path, password, encrypt_name, cs, progress_callback)
        if msg:
            safe_print(msg)
        return ok, msg
    safe_print(f"[AES-{mode}] Encrypt: Python fallback path  →  {os.path.basename(path)}")
    return _encrypt_file_py(path, password, encrypt_name, chunk_size, AEAD, progress_callback)


def decrypt_file(
    path: str,
    password: str,
    chunk_size=None,
    progress_callback: Optional[Callable] = None,
) -> tuple[bool, str]:
    """Decrypt a single AES-256 GCM or CFB encrypted file."""
    if native_bridge.NATIVE_AVAILABLE:
        is_gcm = path.lower().endswith(".gfglock")
        mode = "GCM" if is_gcm else "CFB"
        safe_print(f"[AES-{mode}] Decrypt: native C++ path  →  {os.path.basename(path)}")
        fn = native_bridge.decrypt_gcm if is_gcm else native_bridge.decrypt_cfb
        ok, msg = fn(path, password, progress_callback)
        if msg:
            safe_print(msg)
        return ok, msg
    safe_print(f"[AES] Decrypt: Python fallback path  →  {os.path.basename(path)}")
    return _decrypt_file_py(path, password, chunk_size, progress_callback)


# ── Python fallback (used when .pyd is not available) ────────────────────────

import io
import struct
from secrets import token_bytes
from typing import cast

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from gfglock.core.chunk_processing import FileChunker
from gfglock.utils.helpers import (
    derive_key,
    generate_encrypted_name,
    get_cpu_thread_count,
)

SALT_SIZE = 16
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_FIELD_SIZE = 4
BUFFER_SIZE = 512 * 1024
SMALL_FILE_THRESHOLD = 10 * 1024 * 1024
PROGRESS_UPDATE_INTERVAL = 100 * 1024 * 1024


def _encrypt_file_py(path, password, encrypt_name, chunk_size, AEAD, progress_callback):
    """Python-level AES-256-GCM/CFB encrypt (fallback when native is unavailable)."""
    logs = []
    out_path = None
    chunker = None
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if path.endswith(".gfglock") or path.endswith(".gfglck"):
            msg = f"{path} is already encrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        file_size = os.path.getsize(path)
        if file_size < SMALL_FILE_THRESHOLD:
            chunk_size = None

        ext = ".gfglock" if AEAD else ".gfglck"
        out_name = generate_encrypted_name(path, encrypt_name, ext)
        out_path = os.path.join(os.path.dirname(path), out_name)

        with open(path, "rb", buffering=BUFFER_SIZE) as fin, open(out_path, "wb", buffering=BUFFER_SIZE) as fout:
            chunker = FileChunker()
            if AEAD:
                salt = token_bytes(SALT_SIZE); nonce = token_bytes(NONCE_SIZE)
                key = derive_key(password, salt)
                cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
                encryptor = cipher.encryptor()
                fout.write(salt); fout.write(nonce)
                cs = 0 if chunk_size is None else int(chunk_size)
                fout.write(struct.pack(">I", cs))
                name_meta = os.path.basename(path).encode("utf-8") + b"\0"
                fout.write(encryptor.update(name_meta))
                if progress_callback:
                    progress_callback(float(len(name_meta)))
                if chunk_size is None:
                    file_data = fin.read()
                    fout.write(encryptor.update(file_data))
                    if progress_callback:
                        progress_callback(float(len(file_data)))
                else:
                    effective_chunk = max(chunk_size, BUFFER_SIZE)
                    progress_batch = 0.0
                    for data in chunker.stream_chunks(fin, None, effective_chunk):
                        fout.write(encryptor.update(data))
                        progress_batch += len(data)
                        if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                            progress_callback(float(progress_batch)); progress_batch = 0.0
                    if progress_batch > 0 and progress_callback:
                        progress_callback(float(progress_batch))
                fout.write(encryptor.finalize()); fout.write(encryptor.tag)
            else:
                salt = token_bytes(SALT_SIZE); iv = token_bytes(16)
                key = derive_key(password, salt)
                cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
                encryptor = cipher.encryptor()
                fout.write(salt); fout.write(iv)
                cs = 0 if chunk_size is None else int(chunk_size)
                fout.write(struct.pack(">I", cs))
                name_meta = os.path.basename(path).encode("utf-8") + b"\0"
                fout.write(encryptor.update(name_meta))
                if progress_callback:
                    progress_callback(float(len(name_meta)))
                if chunk_size is None:
                    file_data = fin.read()
                    fout.write(encryptor.update(file_data))
                    if progress_callback:
                        progress_callback(float(len(file_data)))
                else:
                    effective_chunk = max(chunk_size, BUFFER_SIZE)
                    progress_batch = 0.0
                    for data in chunker.stream_chunks(fin, None, effective_chunk):
                        fout.write(encryptor.update(data))
                        progress_batch += len(data)
                        if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                            progress_callback(float(progress_batch)); progress_batch = 0.0
                    if progress_batch > 0 and progress_callback:
                        progress_callback(float(progress_batch))

        os.remove(path)
        msg = f"Encrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        try:
            chunker.cleanup_temp_dir()  # type: ignore[union-attr]
        except Exception:
            pass
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while encrypting {path}: {e}"
        logs.append(msg); safe_print(msg)
        try:
            if out_path and os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        if chunker:
            try:
                chunker.cleanup_temp_dir()
            except Exception:
                pass
        return False, "\n".join(logs)


def _decrypt_file_py(path, password, chunk_size, progress_callback):
    """Python-level AES-256-GCM/CFB decrypt (fallback when native is unavailable)."""
    logs = []
    out_path = None
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)
        if not (path.endswith(".gfglock") or path.endswith(".gfglck")):
            msg = f"{path} is already decrypted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        total_size = os.path.getsize(path)
        if total_size < 2:
            msg = f"Critical error: {path} is too small or corrupted"
            logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        if total_size < SMALL_FILE_THRESHOLD:
            chunk_size = None

        with open(path, "rb", buffering=BUFFER_SIZE) as fin:
            if path.endswith(".gfglock"):
                if total_size < SALT_SIZE + NONCE_SIZE + TAG_SIZE + 1:
                    msg = f"Critical error: {path} is too small or corrupted"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                salt = fin.read(SALT_SIZE); nonce = fin.read(NONCE_SIZE)
                cs_bytes = fin.read(CHUNK_FIELD_SIZE)
                try:
                    file_chunk_size = struct.unpack(">I", cs_bytes)[0]
                    if file_chunk_size == 0:
                        file_chunk_size = None
                except Exception:
                    file_chunk_size = None
                data_len = total_size - SALT_SIZE - NONCE_SIZE - CHUNK_FIELD_SIZE - TAG_SIZE
                key = derive_key(password, salt)
                chunk_size = file_chunk_size

                if chunk_size is None:
                    encrypted_data = fin.read(data_len); tag = fin.read(TAG_SIZE)
                    if progress_callback:
                        progress_callback(float(len(encrypted_data)))
                    try:
                        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
                        decryptor = cipher.decryptor()
                        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
                    except Exception as e:
                        msg = f"Critical error while decrypting {path}: authentication failed ({e})"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                    idx = decrypted.find(b"\0")
                    if idx == -1:
                        msg = f"Critical error while decrypting {path}: metadata not found"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                    original_name = decrypted[:idx].decode("utf-8")
                    out_path = os.path.join(os.path.dirname(path), original_name)
                    with open(out_path, "wb", buffering=BUFFER_SIZE) as fout:
                        fout.write(decrypted[idx + 1:])
                else:
                    effective_chunk = max(chunk_size, BUFFER_SIZE)
                    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
                    decryptor = cipher.decryptor()
                    meta = b""; got_meta = False
                    temp_out: Optional[io.BufferedWriter] = None
                    remaining = data_len; progress_batch = 0.0
                    try:
                        while remaining > 0:
                            to_read = min(remaining, effective_chunk)
                            enc_chunk = fin.read(to_read)
                            if not enc_chunk:
                                break
                            remaining -= len(enc_chunk)
                            progress_batch += len(enc_chunk)
                            dec = decryptor.update(enc_chunk)
                            if not got_meta:
                                idx = dec.find(b"\0")
                                if idx != -1:
                                    meta += dec[:idx]
                                    original_name = meta.decode("utf-8")
                                    out_path = os.path.join(os.path.dirname(path), original_name)
                                    temp_out = cast(io.BufferedWriter, open(out_path, "wb", buffering=BUFFER_SIZE))
                                    rest = dec[idx + 1:]
                                    if rest and temp_out is not None:
                                        temp_out.write(rest)
                                    got_meta = True
                                else:
                                    meta += dec
                            else:
                                if temp_out:
                                    temp_out.write(dec)
                            if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                                progress_callback(float(progress_batch)); progress_batch = 0.0
                        if progress_batch > 0 and progress_callback:
                            progress_callback(float(progress_batch))
                        tag = fin.read(TAG_SIZE)
                        decryptor.finalize_with_tag(tag)  # type: ignore[attr-defined]
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
                        try: temp_out.close()
                        except Exception: pass

            elif path.endswith(".gfglck"):
                if total_size < SALT_SIZE + 16 + CHUNK_FIELD_SIZE + 1:
                    msg = f"Critical error: {path} is too small or corrupted"
                    logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                salt = fin.read(SALT_SIZE); iv = fin.read(16)
                cs_bytes = fin.read(CHUNK_FIELD_SIZE)
                try:
                    file_chunk_size = struct.unpack(">I", cs_bytes)[0]
                    if file_chunk_size == 0:
                        file_chunk_size = None
                except Exception:
                    file_chunk_size = None
                data_len = total_size - SALT_SIZE - 16 - CHUNK_FIELD_SIZE
                chunk_size = file_chunk_size
                key = derive_key(password, salt)
                cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
                decryptor = cipher.decryptor()
                meta = b""; got_meta = False
                temp_out = None

                if chunk_size is None:
                    encrypted_data = fin.read(data_len)
                    if progress_callback:
                        progress_callback(float(len(encrypted_data)))
                    dec = decryptor.update(encrypted_data) + decryptor.finalize()
                    idx = dec.find(b"\0")
                    if idx == -1:
                        msg = f"Critical error while decrypting {path}: metadata not found"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                    original_name = dec[:idx].decode("utf-8")
                    out_path = os.path.join(os.path.dirname(path), original_name)
                    with open(out_path, "wb", buffering=BUFFER_SIZE) as fout:
                        fout.write(dec[idx + 1:])
                else:
                    effective_chunk = max(chunk_size, BUFFER_SIZE)
                    remaining = data_len; progress_batch = 0.0
                    try:
                        while remaining > 0:
                            to_read = min(remaining, effective_chunk)
                            enc_chunk = fin.read(to_read)
                            if not enc_chunk:
                                break
                            remaining -= len(enc_chunk)
                            progress_batch += len(enc_chunk)
                            dec = decryptor.update(enc_chunk)
                            if not got_meta:
                                idx = dec.find(b"\0")
                                if idx != -1:
                                    meta += dec[:idx]
                                    original_name = meta.decode("utf-8")
                                    out_path = os.path.join(os.path.dirname(path), original_name)
                                    temp_out = cast(io.BufferedWriter, open(out_path, "wb", buffering=BUFFER_SIZE))
                                    rest = dec[idx + 1:]
                                    if rest and temp_out is not None:
                                        temp_out.write(rest)
                                    got_meta = True
                                else:
                                    meta += dec
                            else:
                                if temp_out is not None:
                                    temp_out.write(dec)
                            if progress_batch >= PROGRESS_UPDATE_INTERVAL and progress_callback:
                                progress_callback(float(progress_batch)); progress_batch = 0.0
                        if progress_batch > 0 and progress_callback:
                            progress_callback(float(progress_batch))
                        decryptor.finalize()
                    except Exception as e:
                        msg = f"Critical error while decrypting {path}: {e}"
                        logs.append(msg); safe_print(msg)
                        if temp_out:
                            try: temp_out.close()
                            except Exception: pass
                        if out_path and os.path.exists(out_path):
                            try: os.remove(out_path)
                            except Exception: pass
                        return False, "\n".join(logs)
                    if not got_meta:
                        msg = f"Critical error while decrypting {path}: metadata not found"
                        logs.append(msg); safe_print(msg); return False, "\n".join(logs)
                    if temp_out:
                        try: temp_out.close()
                        except Exception: pass
            else:
                msg = f"Critical error while decrypting {path}: unknown file format"
                logs.append(msg); safe_print(msg); return False, "\n".join(logs)

        try:
            os.remove(path)
        except Exception:
            pass
        msg = f"Decrypted: {path} -> {out_path}"
        logs.append(msg); safe_print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while decrypting {path}: {e}"
        logs.append(msg); safe_print(msg)
        return False, "\n".join(logs)


# ── Folder helpers (unchanged) ────────────────────────────────────────────────

def _enc(args):
    return encrypt_file(*args)


def _dec(args):
    return decrypt_file(*args)


def encrypt_folder(folder, password, encrypt_name=False, threads=1, chunk_size=None, AEAD=True):
    """Encrypt all files in a folder (multi-threaded)."""
    start = time.time(); count = 0
    files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs]
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            ok = encrypt_file(fp, password, encrypt_name, chunk_size=chunk_size, AEAD=AEAD)
            if bool(ok[0] if isinstance(ok, tuple) else ok):
                count += 1
    else:
        args_list = [(fp, password, encrypt_name, chunk_size, AEAD) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_enc, args_list):
                if bool(ok[0] if isinstance(ok, tuple) else ok):
                    count += 1
    elapsed = time.time() - start
    safe_print(f"{count} files encrypted successfully.\nTime elapsed: {format_duration(elapsed)}")


def decrypt_folder(folder, password, threads=1, chunk_size=None):
    """Decrypt all files in a folder (multi-threaded)."""
    start = time.time(); count = 0
    files = [os.path.join(root, f) for root, _, fs in os.walk(folder) for f in fs]
    threads = clamp_threads(threads)
    if threads == 1:
        for fp in files:
            ok = decrypt_file(fp, password, chunk_size=chunk_size)
            if bool(ok[0] if isinstance(ok, tuple) else ok):
                count += 1
    else:
        args_list = [(fp, password, chunk_size) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_dec, args_list):
                if bool(ok[0] if isinstance(ok, tuple) else ok):
                    count += 1
    elapsed = time.time() - start
    safe_print(f"{count} files decrypted successfully.\nTime elapsed: {format_duration(elapsed)}")


if __name__ == "__main__":
    freeze_support()
