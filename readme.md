# gfgLock 🔐

High‑performance AES‑256 file & folder encryption tools for Windows and Python.

gfgLock provides three implementations of AES‑256 encryption:

- **Python (PyCryptodome backend)** → chunked + multiprocessing
- **Python (Cryptography backend)** → super fast, OpenSSL‑powered
- **Windows Batch (OpenSSL CLI)** → native speed, no Python required

All variants use **AES‑256‑CFB** mode with secure key derivation, ensuring strong industry‑grade encryption.

---

## 📂 Repository Contents

1. **`gfglock_aes256_pycryptodome.py`**

   - Backend: [PyCryptodome](https://pycryptodome.readthedocs.io/)
   - Features: Chunk‑based streaming, multiprocessing support
   - Strength: AES‑256 encryption
   - Speed: Good, but slower than Cryptography backend
   - Best for: Developers who prefer PyCryptodome or want multiprocessing control

2. **`gfglock_fast_aes256_cryptography.py`**

   - Backend: [Cryptography](https://cryptography.io/) (OpenSSL under the hood)
   - Features: Chunk‑based streaming, optimized C backend
   - Strength: AES‑256 encryption
   - Speed: Super fast (recommended)
   - Best for: End‑users and developers needing maximum performance

3. **`gfgLock` (Windows GUI)**

   - Backend: `gfglock_fast_aes256_cryptography.py` wrapped in a user-friendly Windows GUI
   - Distribution: Packaged as a Windows installer (Inno Setup) and published on GitHub Releases
   - Install / Run: Download the installer from the releases page and run the setup executable to install a fully standalone application (no separate Python install required for the shipped build)
   - Features (end‑user focused):
     - Drag & drop files or folders into the UI for encryption/decryption
     - Select multiple files; the dialog shows how many were processed, skipped, succeeded or failed
     - Password + (optional) confirm field with sensible keyboard focus / tab order
     - Progress dialog with live logs (same messages you'd see in the CLI)
     - Optional filename randomization for encrypted outputs
     - Context‑menu integration and file association when installed (adds a "Encrypt with gfgLock" / "Decrypt with gfgLock" entry)
   - File extension: Files encrypted by the GUI use the `.gfglock` extension — decrypt with the same app that encrypted them
   - Releases / Installer: https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock

4. **`gfglock_aes256_openssl_cli.bat`**
   - Backend: Native [OpenSSL CLI](https://www.openssl.org/)
   - Features: Windows batch script, recursive folder/file encryption
   - Strength: AES‑256 encryption with PBKDF2 key derivation
   - Speed: Native OpenSSL performance (very fast)
   - Best for: End‑users who want a simple `.bat` script without Python

---

## 🔑 Encryption Level

All three scripts use **AES‑256 (Advanced Encryption Standard, 256‑bit key)** in **CFB mode**:

- AES‑256 is considered military‑grade encryption, approved by NIST.
- Resistant to brute‑force attacks.
- Secure for sensitive data storage and transfer.

---

## ⚡ Installation

### Python Scripts

1. Install Python 3.9+
2. Clone the repo:
   ```bash
   git clone https://github.com/shahfaisalgfg/gfgLock.git
   cd gfgLock
   ```
3. Install requirements:

   ```bash
   git clone https://github.com/shahfaisalgfg/gfgLock.git
   cd gfgLock
   ```

4. Install requirements:
   ```bash
   pip install cryptography pycryptodome
   ```

### Windows GUI (recommended for most end users)

- Download the latest `gfgLock` installer from the Releases page: `https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock`.
- Run the installer (created with Inno Setup) and follow the steps. The installer bundles the application and icons and can add optional context menu/file association entries.
- After installation you can launch `gfgLock` from the Start Menu or desktop shortcut.

Note: the GUI build is a standalone Windows installer — you do not need to install Python or libraries separately when using the shipped installer.

### Batch Script

- Requires OpenSSL installed on Windows.
- If not found, the script will attempt installation via winget.

## 🚀 Usage

- Python (PyCryptodome)

  ```Python
  from gfglock_aes256_pycryptodome import encrypt_folder, decrypt_folder
   # Encrypt folder with AES‑256
   encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=4, chunk_size=8*1024*1024)

   # Decrypt folder
   decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=4, chunk_size=8*1024*1024)
  ```

- Python (Cryptography, Fast)
  ```Python
   from gfglock_fast_aes256_cryptography import encrypt_folder, decrypt_folder

   # Encrypt folder (super fast)
   encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=4, chunk_size=32*1024*1024)

   # Decrypt folder
   decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=4, chunk_size=32*1024*1024)
  ```
- Batch Script (OpenSSL CLI)

  - Windows GUI (`gfgLock`)

    - Typical flow:

      1.  Launch the `gfgLock` app.
      2.  Drag & drop files/folders or use "Add Files" / "Add Folders".
      3.  Enter a strong password (and confirm it when encrypting).
      4.  Choose thread/chunk options if you want to tune performance (defaults are sensible).
      5.  Click "Start Encryption" or "Start Decryption".
      6.  Review the progress dialog — it shows per-file messages, counts for succeeded/failed/skipped items, and a detailed log you can copy.

    - Installer extras:

      - Context menu entries and optional `.gfglock` file association can be added by the installer for quick access from Explorer.
      - An "About" dialog and a "Check Updates" button link to the Releases page.

    - Tip: If several files are already encrypted, the GUI will report them as "skipped" rather than counting them as failures.

  ```cmd
  :: Encrypt single file
  gfglock_aes256_openssl_cli.bat encrypt "C:\path\to\file.ext" "mypassword"

  :: Decrypt single file
  gfglock_aes256_openssl_cli.bat decrypt "C:\path\to\file.ext.gfglock" "mypassword"

  :: Encrypt folder recursively
  gfglock_aes256_openssl_cli.bat encrypt "C:\path\to\folder" "mypassword" folder

   :: Decrypt folder recursively
   gfglock_aes256_openssl_cli.bat decrypt "C:\path\to\folder" "mypassword" folder
  ```

# File Encryption Tools

A collection of AES-256 file encryption/decryption implementations using different cryptographic libraries and methods.

### Output Extensions

- Cryptography backend → `.gfglock`
- PyCryptodome backend → `.gfgpcd`
- OpenSSL CLI backend → `.gfgssl`

⚠️ Important: Always decrypt files with the same script that encrypted them.

## 📊 Comparison Table

| Feature / Tool   | `gfglock_aes256_pycryptodome.py` | `gfglock_fast_aes256_cryptography.py` | `gfglock_aes256_openssl_cli.bat`        |
| ---------------- | -------------------------------- | ------------------------------------- | --------------------------------------- |
| **Library**      | PyCryptodome                     | Cryptography                          | OpenSSL (CLI)                           |
| **Platform**     | Cross-platform (Python)          | Cross-platform (Python)               | Windows (Batch)                         |
| **Performance**  | Good                             | Excellent (optimized)                 | Fast (native)                           |
| **Dependencies** | PyCryptodome                     | Cryptography                          | OpenSSL installed                       |
| **Ease of Use**  | Easy                             | Easy                                  | Requires OpenSSL setup                  |
| **Key Features** | Pure Python, chunked processing  | Rust-based backend, high performance  | Native encryption, minimal dependencies |
| **Best For**     | General Python use               | High-performance needs                | Windows CLI automation                  |

## 🛡️ Security Notes

- Always use strong passwords (12+ chars, mix of letters/numbers/symbols).
- Encrypted files replace originals only after successful encryption/decryption.
- AES‑256 is secure, but password strength is critical.

## 👨‍💻 Developer Notes

- Chunk size can be tuned:
  - 1–4 MB → gentle, slower
  - 8–16 MB → balanced (recommended default)
  - 32–64 MB → faster, heavier load
- Multiprocessing is supported in Python scripts.
- Logging can be added for audit trails if needed.

## 📜 License

MIT License — free to use, modify, and distribute.

## 🤝 Contributing

Pull requests are welcome! Please open issues for bugs or feature requests.

## ✨ Credits

Developed by Shah Faisal  
AES‑256 implementations powered by PyCryptodome, Cryptography, and OpenSSL.
