import os
import hashlib
import datetime
import time
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

# --- Encryption ---
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

        # --- Output filename ---
        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = str(int.from_bytes(get_random_bytes(4), 'big'))
            new_name = f"{now}_{rand_part}.gfglock"
        else:
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            new_name = base_name + ".gfglock"

        new_path = os.path.join(os.path.dirname(filepath), new_name)

        with open(filepath, 'rb') as fin, open(new_path, 'wb') as fout:
            # Write IV
            fout.write(iv)
            # Write metadata (original filename)
            original_name = os.path.basename(filepath)
            meta = original_name.encode("utf-8") + b"\0"
            fout.write(cipher.encrypt(meta))

            # Encrypt file in chunks
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

# --- Decryption ---
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

            # Read metadata first
            meta_bytes = b""
            while True:
                b = fin.read(1)
                if b == b"\0" or not b:
                    break
                meta_bytes += cipher.decrypt(b)
            original_name = meta_bytes.decode("utf-8")

            new_path = os.path.join(os.path.dirname(filepath), original_name)
            with open(new_path, 'wb') as fout:
                # Decrypt remaining chunks
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

# --- Folder operations ---
def encrypt_folder(folder, password, encrypt_name=False, enable_logs=False):
    start = time.time()
    count = 0
    for root, _, files in os.walk(folder):
        for file in files:
            file_path = os.path.join(root, file)
            if encrypt_file(file_path, password, encrypt_name, enable_logs):
                count += 1
    elapsed = time.time() - start
    print(f"{count} files encrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

def decrypt_folder(folder, password, enable_logs=False):
    start = time.time()
    count = 0
    for root, _, files in os.walk(folder):
        for file in files:
            file_path = os.path.join(root, file)
            if decrypt_file(file_path, password, enable_logs):
                count += 1
    elapsed = time.time() - start
    print(f"{count} files decrypted successfully.")
    print(f"Time elapsed: {format_duration(elapsed)}")

# --- Example usage ---
# encrypt_file("C:/Users/shahf/Music/Archives/video.mp4", "mypassword123", encrypt_name=True, enable_logs=True)
# decrypt_file("C:/Users/shahf/Music/Archives/20251207153700_123456.gfglock", "mypassword123", enable_logs=True)
# encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, enable_logs=True)
decrypt_folder("C:/Users/shahf/Music/BOX", "mypassword123", enable_logs=True)