# v2_gfglock_chunk_mp.py
import os
import hashlib
import datetime
import time
from multiprocessing import Pool, cpu_count
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# --- Logging helpers ---
def log_message(filename, message):
    log_path = os.path.join(os.getcwd(), filename)
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"{datetime.datetime.now()} - {message}\n")

def derive_key(password):
    import hashlib
    return hashlib.sha256(password.encode()).digest()

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

def clamp_threads(threads):
    try:
        max_safe = max(cpu_count() - 1, 1)
    except Exception:
        max_safe = 1
    if not isinstance(threads, int):
        return 1
    if threads < 1:
        return 1
    if threads > max_safe:
        return max_safe
    return threads

# --- Core encryption/decryption (chunk-based) ---
def encrypt_file(filepath, password, encrypt_name=False, enable_logs=False, chunk_size=4*1024*1024):
    try:
        if not os.path.exists(filepath):
            log_message("failed_enc_gfglock.log", f"File not found: {filepath}")
            print(f"Critical error: {filepath} not found")
            return False

        if filepath.endswith(".gfglock"):
            msg = f"{filepath} is already encrypted"
            if enable_logs:
                log_message("gfglock.logs", msg)
            print(msg)
            return False

        key = derive_key(password)
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CFB, iv=iv)

        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = str(int.from_bytes(get_random_bytes(4), 'big'))
            new_name = f"{now}_{rand_part}.gfglock"
        else:
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            new_name = base_name + ".gfglock"

        new_path = os.path.join(os.path.dirname(filepath), new_name)

        with open(filepath, 'rb') as fin, open(new_path, 'wb') as fout:
            fout.write(iv)
            original_name = os.path.basename(filepath)
            meta = original_name.encode("utf-8") + b"\0"
            # Encrypt the meta in one go
            fout.write(cipher.encrypt(meta))

            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                fout.write(cipher.encrypt(chunk))

        os.remove(filepath)
        msg = f"Encrypted: {filepath} -> {new_path}"
        if enable_logs:
            log_message("gfglock.logs", msg)
        print(msg)
        return True

    except Exception as e:
        log_message("failed_enc_gfglock.log", f"Failed to encrypt {filepath}: {e}")
        print(f"Critical error while encrypting {filepath}: {e}")
        return False

def decrypt_file(filepath, password, enable_logs=False, chunk_size=4*1024*1024):
    try:
        if not os.path.exists(filepath):
            log_message("failed_dec_gfglock.log", f"File not found: {filepath}")
            print(f"Critical error: {filepath} not found")
            return False

        if not filepath.endswith(".gfglock"):
            msg = f"{filepath} is already decrypted"
            if enable_logs:
                log_message("gfglock.logs", msg)
            print(msg)
            return False

        key = derive_key(password)

        with open(filepath, 'rb') as fin:
            iv = fin.read(16)
            cipher = AES.new(key, AES.MODE_CFB, iv=iv)

            # Read and decrypt metadata until null terminator
            meta_cipher = b""
            while True:
                b = fin.read(1)
                if not b:
                    # No meta found -> critical error
                    raise ValueError("Missing metadata in encrypted file")
                # decrypt one byte of meta at a time (safe for CFB)
                dec_b = cipher.decrypt(b)
                if dec_b == b"\0":
                    break
                meta_cipher += dec_b

            original_name = meta_cipher.decode("utf-8")
            new_path = os.path.join(os.path.dirname(filepath), original_name)

            with open(new_path, 'wb') as fout:
                while True:
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fout.write(cipher.decrypt(chunk))

        os.remove(filepath)
        msg = f"Decrypted: {filepath} -> {new_path}"
        if enable_logs:
            log_message("gfglock.logs", msg)
        print(msg)
        return True

    except Exception as e:
        log_message("failed_dec_gfglock.log", f"Failed to decrypt {filepath}: {e}")
        print(f"Critical error while decrypting {filepath}: {e}")
        return False

# --- Folder ops with optional multiprocessing ---
def _encrypt_one(args):
    return encrypt_file(*args)

def _decrypt_one(args):
    return decrypt_file(*args)

def encrypt_folder(folder, password, encrypt_name=False, enable_logs=False, threads=1, chunk_size=4*1024*1024):
    start = time.time()
    count = 0

    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))

    threads = clamp_threads(threads)
    if threads == 1:
        for file_path in files:
            if encrypt_file(file_path, password, encrypt_name, enable_logs, chunk_size):
                count += 1
    else:
        args_list = [(fp, password, encrypt_name, enable_logs, chunk_size) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_encrypt_one, args_list):
                if ok:
                    count += 1

    elapsed = time.time() - start
    print(f"{count} files encrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

def decrypt_folder(folder, password, enable_logs=False, threads=1, chunk_size=4*1024*1024):
    start = time.time()
    count = 0

    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))

    threads = clamp_threads(threads)
    if threads == 1:
        for file_path in files:
            if decrypt_file(file_path, password, enable_logs, chunk_size):
                count += 1
    else:
        args_list = [(fp, password, enable_logs, chunk_size) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_decrypt_one, args_list):
                if ok:
                    count += 1

    elapsed = time.time() - start
    print(f"{count} files decrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

# --- Example usage ---
# encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, enable_logs=True, threads=4, chunk_size=8*1024*1024)
# decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", enable_logs=True, threads=4, chunk_size=8*1024*1024)