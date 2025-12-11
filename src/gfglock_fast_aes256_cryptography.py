# gfglock_fast_aes256_cryptography.py

# install requirements using requirements.txt(pip install -r requirements.txt) or run below command in terminal.
# pip install cryptography

import os, time, datetime, hashlib
from multiprocessing import Pool, cpu_count, freeze_support
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from secrets import token_bytes

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
    try: max_safe = max(cpu_count() - 1, 1)
    except Exception: max_safe = 1
    if not isinstance(threads, int) or threads < 1: return 1
    return min(threads, max_safe)

def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60: return f"{seconds} seconds"
    elif seconds < 3600:
        mins, secs = divmod(seconds, 60); return f"{mins} mins {secs} sec"
    else:
        hours, remainder = divmod(seconds, 3600)
        mins, secs = divmod(remainder, 60)
        return f"{hours} hrs {mins} mins {secs} sec"

def derive_key(password): return hashlib.sha256(password.encode()).digest()

def encrypt_file(path, password, encrypt_name=False, chunk_size=8*1024*1024):
    logs = []
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg)
            print(msg)
            return False, "\n".join(logs)
        if path.endswith(".gfglock"):
            msg = f"{path} is already encrypted"
            logs.append(msg)
            print(msg)
            return False, "\n".join(logs)

        key = derive_key(password)
        iv = token_bytes(16)
        cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        if encrypt_name:
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            rand_part = int.from_bytes(token_bytes(4), "big")
            out_name = f"{now}_{rand_part}.gfglock"
        else:
            base = os.path.splitext(os.path.basename(path))[0]
            out_name = base + ".gfglock"
        out_path = os.path.join(os.path.dirname(path), out_name)
        with open(path, "rb") as fin, open(out_path, "wb") as fout:
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
        logs.append(msg)
        print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while encrypting {path}: {e}"
        logs.append(msg)
        print(msg)
        return False, "\n".join(logs)

def decrypt_file(path, password, chunk_size=8*1024*1024):
    logs = []
    try:
        if not os.path.exists(path):
            msg = f"Critical error: {path} not found"
            logs.append(msg)
            print(msg)
            return False, "\n".join(logs)
        if not path.endswith(".gfglock"):
            msg = f"{path} is already decrypted"
            logs.append(msg)
            print(msg)
            return False, "\n".join(logs)

        key = derive_key(password)
        with open(path, "rb") as fin:
            iv = fin.read(16)
            cipher = Cipher(algorithms.AES(key), modes.CFB(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            meta = b""
            while True:
                b = fin.read(1)
                if not b:
                    raise ValueError("Missing metadata")
                db = decryptor.update(b)
                if db == b"\0":
                    break
                meta += db
            original_name = meta.decode("utf-8")
            out_path = os.path.join(os.path.dirname(path), original_name)
            with open(out_path, "wb") as fout:
                while True:
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fout.write(decryptor.update(chunk))
                fout.write(decryptor.finalize())
        os.remove(path)
        msg = f"Decrypted: {path} -> {out_path}"
        logs.append(msg)
        print(msg)
        return True, "\n".join(logs)
    except Exception as e:
        msg = f"Critical error while decrypting {path}: {e}"
        logs.append(msg)
        print(msg)
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
    print(f"{count} files encrypted successfully.\nTime elapsed: {format_duration(elapsed)}")


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
    print(f"{count} files decrypted successfully.\nTime elapsed: {format_duration(elapsed)}")

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
    encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=threads, chunk_size=s18_chunk)
    decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=threads, chunk_size=s18_chunk)

    # Example usage single thread & 8mb(default chunk size):
    # encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True)
    # decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123")