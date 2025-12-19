# gfgLock 🔐

**A powerful, user-friendly AES‑256 file and folder encryption tool for Windows.**

High‑performance encryption with a modern graphical interface, or choose from command‑line Python and Batch implementations. All variants use **AES‑256‑CFB** mode with secure key derivation for military‑grade security.

---

## 📂 Repository Contents

### 1. **`gfgLock` (Windows GUI Application)** ⭐ Recommended for End-Users

**Download and install the standalone Windows application:**

- **Release Page:** [GitHub Releases - gfgLock](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock)
- **Backend:** `gfglock_fast_aes256_cryptography.py` (super-fast OpenSSL-powered encryption)
- **Distribution:** Packaged as a Windows installer (Inno Setup) — no Python installation needed
- **File Extension:** `.gfglock`

**Key Features:**

- ✅ **Drag & drop** support for files and folders
- ✅ **Progress tracking** with live logs (same output as CLI)
- ✅ **Batch operations** — encrypt/decrypt multiple files at once
- ✅ **Detailed reporting** — shows succeeded, failed, and skipped file counts
- ✅ **Optional filename randomization** for encrypted files
- ✅ **Context menu integration** (adds "Encrypt/Decrypt with gfgLock" to Explorer)
- ✅ **Optional file association** for `.gfglock` files
- ✅ **Professional UI** with password confirmation, tab order, and keyboard shortcuts

**Screenshot:**

![gfgLock Main Window](screenshots/main_window.png)

![gfgLock Encryption Window](screenshots/encryption_window.png)

![gfgLock Progress Window](screenshots/progress_window.png)

![gfgLock About Dialog](screenshots/about_window.png)

---

### 2. **`gfglock_fast_aes256_cryptography.py`** (Python CLI - Fastest)

- **Backend:** [Cryptography](https://cryptography.io/) (OpenSSL-powered)
- **Features:** Chunk‑based streaming, optimized C backend, multiprocessing support
- **Speed:** Excellent (recommended for developers)
- **Best for:** Developers and power users who prefer command-line tools
- **File Extension:** `.gfglock`

---

### 3. **`gfglock_aes256_pycryptodome.py`** (Python CLI - Cross-Platform)

- **Backend:** [PyCryptodome](https://pycryptodome.readthedocs.io/)
- **Features:** Pure Python, chunk‑based streaming, multiprocessing support
- **Speed:** Good (slower than Cryptography backend)
- **Best for:** Developers who prefer PyCryptodome or need cross-platform support
- **File Extension:** `.gfgpcd`

---

### 4. **`gfglock_aes256_openssl_cli.bat`** (Windows Batch Script)

- **Backend:** Native [OpenSSL CLI](https://www.openssl.org/)
- **Features:** Windows batch script, recursive folder/file encryption
- **Speed:** Very fast (native OpenSSL performance)
- **Best for:** Windows users who want a simple `.bat` script without Python
- **File Extension:** `.gfgssl`

---

## 🔑 Encryption Level

All three scripts use **AES‑256 (Advanced Encryption Standard, 256‑bit key)** in **CFB mode**:

- AES‑256 is considered military‑grade encryption, approved by NIST.
- Resistant to brute‑force attacks.
- Secure for sensitive data storage and transfer.

---

## ⚡ Installation

### Option 1: Windows GUI (⭐ Recommended for Most Users)

1. Visit the [GitHub Releases page](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/gfgLock)
2. Download the latest `gfgLock_Setup_*.exe` installer
3. Run the installer and follow the setup wizard
4. After installation, launch `gfgLock` from the Start Menu or desktop shortcut

**Note:** The GUI is a standalone Windows installer — you do **not** need Python or any additional libraries installed.

### Option 2: Python Scripts (Command-Line)

1. Install Python 3.9+
2. Clone the repository:

   ```bash
   git clone https://github.com/shahfaisalgfg/gfgLock.git
   cd gfgLock
   ```

3. Install dependencies:

   ```bash
   pip install cryptography pycryptodome
   ```

### Option 3: Batch Script (Windows Only)

- Requires OpenSSL installed on Windows
- If not found, the script will attempt automatic installation via winget

## 🚀 Usage

### Windows GUI (`gfgLock`)

**Simple workflow:**

1. Launch the `gfgLock` app
2. Drag & drop files/folders or use "Add Files" / "Add Folders"
3. Enter a strong password (and confirm it when encrypting)
4. Choose thread/chunk options if needed (defaults are sensible)
5. Click "Start Encryption" or "Start Decryption"
6. Review the progress dialog with per-file messages, counts, and detailed logs

**Installer extras:**

- Context menu integration: Right-click files/folders to "Encrypt/Decrypt with gfgLock"
- File association for `.gfglock` files (optional, during installation)
- "About" dialog and "Check Updates" button link to the releases page

**Pro tip:** Already-encrypted files are reported as "skipped," not as failures.

---

### Python CLI (Cryptography Backend - Fastest)

```python
from gfglock_fast_aes256_cryptography import encrypt_folder, decrypt_folder

# Encrypt folder (super fast)
encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=4, chunk_size=32*1024*1024)

# Decrypt folder
decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=4, chunk_size=32*1024*1024)
```

---

### Python CLI (PyCryptodome Backend - Cross-Platform)

```python
from gfglock_aes256_pycryptodome import encrypt_folder, decrypt_folder

# Encrypt folder with AES‑256
encrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", encrypt_name=True, threads=4, chunk_size=8*1024*1024)

# Decrypt folder
decrypt_folder("C:/Users/shahf/Music/Archives", "mypassword123", threads=4, chunk_size=8*1024*1024)
```

---

### Windows Batch Script (OpenSSL CLI)

```cmd
:: Encrypt single file
gfglock_aes256_openssl_cli.bat encrypt "C:\path\to\file.ext" "mypassword"

:: Decrypt single file
gfglock_aes256_openssl_cli.bat decrypt "C:\path\to\file.ext.gfgssl" "mypassword"

:: Encrypt folder recursively
gfglock_aes256_openssl_cli.bat encrypt "C:\path\to\folder" "mypassword" folder

:: Decrypt folder recursively
gfglock_aes256_openssl_cli.bat decrypt "C:\path\to\folder" "mypassword" folder
```

---

## 📊 File Extensions & Compatibility

- **gfgLock (GUI)** → `.gfglock` (must decrypt with GUI or Python Cryptography backend)
- **Python (Cryptography)** → `.gfglock` (compatible with GUI)
- **Python (PyCryptodome)** → `.gfgpcd` (must decrypt with same backend)
- **Windows Batch (OpenSSL)** → `.gfgssl` (must decrypt with OpenSSL CLI)

⚠️ **Important:** Always decrypt files with the **same tool that encrypted them**.

---

## 📊 Tool Comparison

| Feature / Tool     | gfgLock (GUI)        | Python (Cryptography) | Python (PyCryptodome) | Batch Script (OpenSSL) |
| ------------------ | -------------------- | --------------------- | --------------------- | ---------------------- |
| **Installation**   | Standalone installer | Requires Python 3.9+  | Requires Python 3.9+  | Requires OpenSSL       |
| **Performance**    | Excellent            | Excellent             | Good                  | Very fast              |
| **Platform**       | Windows only         | Cross-platform        | Cross-platform        | Windows only           |
| **User Interface** | Modern GUI           | Command-line          | Command-line          | Command-line           |
| **Best For**       | End-users            | Developers            | Developers            | Automation/scripting   |
| **File Extension** | `.gfglock`           | `.gfglock`            | `.gfgpcd`             | `.gfgssl`              |

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
