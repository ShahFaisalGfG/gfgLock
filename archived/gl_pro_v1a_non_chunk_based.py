# v1_gfglock_nonchunk_mp.py

# install requirements using requirements.txt or run below command in terminal.
# pip install pycryptodome

import os
import hashlib
import datetime
import time
from multiprocessing import Pool, cpu_count, freeze_support
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# --- Logging helpers ---
def log_message(filename, message):
    log_path = os.path.join(os.getcwd(), filename)
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(f"{datetime.datetime.now()} - {message}\n")

def pad(data):
    return data + b"\0" * (16 - len(data) % 16)

def unpad(data):
    return data.rstrip(b"\0")

def derive_key(password):
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

def get_cpu_thread_count() -> int:
    """
    Detects the number of logical CPU threads available on the system.
    Returns(int): The number of logical CPU threads. Returns 0 if the number cannot be determined.
    """
    cpu_count = os.cpu_count()
    if cpu_count is None:
        return 0  # Return 0 if the count is undetermined
    return cpu_count

def clamp_threads(threads):
    # Safe clamp: 1..max(cpu_count - 1, 1), avoid oversubscription
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

# --- Core encryption/decryption (non-chunk) ---
def encrypt_file(filepath, password, encrypt_name=False, enable_logs=False):
    try:
        if not os.path.exists(filepath):
            log_message("failed_enc_gfglock.log", f"File not found: {filepath}")
            print(f"Critical error: {filepath} not found")
            return False

        if filepath.endswith(".gfglock"):
            msg = f"{filepath} is already encrypted"
            if enable_logs:
                log_message("../gfglock.logs", msg)
            print(msg)
            return False

        key = derive_key(password)
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CFB, iv=iv)

        with open(filepath, 'rb') as f:
            plaintext = f.read()

        original_name = os.path.basename(filepath)
        meta = original_name.encode("utf-8") + b"\0"
        ciphertext = iv + cipher.encrypt(meta + pad(plaintext))

        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = str(int.from_bytes(get_random_bytes(4), 'big'))
            new_name = f"{now}_{rand_part}.gfglock"
        else:
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            new_name = base_name + ".gfglock"

        new_path = os.path.join(os.path.dirname(filepath), new_name)
        with open(new_path, 'wb') as f:
            f.write(ciphertext)

        os.remove(filepath)
        msg = f"Encrypted: {filepath} -> {new_path}"
        if enable_logs:
            log_message("../gfglock.logs", msg)
        print(msg)
        return True

    except Exception as e:
        log_message("failed_enc_gfglock.log", f"Failed to encrypt {filepath}: {e}")
        print(f"Critical error while encrypting {filepath}: {e}")
        return False

def decrypt_file(filepath, password, enable_logs=False):
    try:
        if not os.path.exists(filepath):
            log_message("../failed_dec_gfglock.log", f"File not found: {filepath}")
            print(f"Critical error: {filepath} not found")
            return False

        if not filepath.endswith(".gfglock"):
            msg = f"{filepath} is already decrypted"
            if enable_logs:
                log_message("../gfglock.logs", msg)
            print(msg)
            return False

        key = derive_key(password)

        with open(filepath, 'rb') as f:
            data = f.read()

        iv = data[:16]
        ciphertext = data[16:]
        cipher = AES.new(key, AES.MODE_CFB, iv=iv)
        decrypted = unpad(cipher.decrypt(ciphertext))

        meta_end = decrypted.find(b"\0")
        original_name = decrypted[:meta_end].decode("utf-8")
        plaintext = decrypted[meta_end+1:]

        new_path = os.path.join(os.path.dirname(filepath), original_name)
        with open(new_path, 'wb') as f:
            f.write(plaintext)

        os.remove(filepath)
        msg = f"Decrypted: {filepath} -> {new_path}"
        if enable_logs:
            log_message("../gfglock.logs", msg)
        print(msg)
        return True

    except Exception as e:
        log_message("../failed_dec_gfglock.log", f"Failed to decrypt {filepath}: {e}")
        print(f"Critical error while decrypting {filepath}: {e}")
        return False

# --- Folder ops with optional multiprocessing ---
def _encrypt_one(args):
    return encrypt_file(*args)

def _decrypt_one(args):
    return decrypt_file(*args)

def encrypt_folder(folder, password, encrypt_name=False, enable_logs=False, threads=1):
    start = time.time()
    count = 0

    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))

    threads = clamp_threads(threads)
    if threads == 1:
        for file_path in files:
            if encrypt_file(file_path, password, encrypt_name, enable_logs):
                count += 1
    else:
        args_list = [(fp, password, encrypt_name, enable_logs) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_encrypt_one, args_list):
                if ok:
                    count += 1

    elapsed = time.time() - start
    print(f"{count} files encrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

def decrypt_folder(folder, password, enable_logs=False, threads=1):
    start = time.time()
    count = 0

    files = []
    for root, _, fs in os.walk(folder):
        for f in fs:
            files.append(os.path.join(root, f))

    threads = clamp_threads(threads)
    if threads == 1:
        for file_path in files:
            if decrypt_file(file_path, password, enable_logs):
                count += 1
    else:
        args_list = [(fp, password, enable_logs) for fp in files]
        with Pool(processes=threads) as pool:
            for ok in pool.imap_unordered(_decrypt_one, args_list):
                if ok:
                    count += 1

    elapsed = time.time() - start
    print(f"{count} files decrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

# --- Example usage ---
if __name__ == "__main__":
    freeze_support()  # Windows multiprocessing safety

    total_threads = get_cpu_thread_count()
    # using half of total threads for balanced performance to avoid system overload
    optimal_threads = total_threads // 2
    threads = clamp_threads(optimal_threads)
    print(f"total threads: {total_threads}\nUsing: {threads}")

    # Example calls
    # encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, enable_logs=True, threads=threads)
    # decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", enable_logs=True, threads=threads)