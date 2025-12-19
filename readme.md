# gfgLock

A modern, secure file encryption utility with a sleek PyQt5 GUI, supporting multiple encryption algorithms (AES-256 GCM, AES-256 CFB, ChaCha20-Poly1305) with batch processing, real-time progress tracking, and comprehensive logging.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://github.com/ShahFaisalGfG/gfgLock/releases)
[![GitHub Release](https://img.shields.io/github/v/release/ShahFaisalGfG/gfgLock)](https://github.com/ShahFaisalGfG/gfgLock/releases)

---

## Features

### 🔐 Multi-Algorithm Encryption

- **AES-256 GCM** (`.gfglock`) — Authenticated encryption with associated data
- **AES-256 CFB** (`.gfglck`) — Cipher Feedback mode, compatible with OpenSSL
- **ChaCha20-Poly1305** (`.gfgcha`) — Modern AEAD stream cipher, resistant to side-channel attacks

### 🖥️ User-Friendly GUI

- Drag & drop support for files and folders
- Batch processing — enqueue multiple items and process them in one run
- Real-time progress dialog with live per-file logs
- Summary statistics (succeeded, failed, skipped items)
- Algorithm selection dropdown (encrypt mode)
- File filtering based on operation mode (encrypt/decrypt)

### ⚙️ Advanced Settings

- **CPU Thread Control** — Optimize performance by adjusting thread count per operation
- **Chunk Size Configuration** — Fine-tune memory usage and processing speed
- **Filename Encryption** — Option to encrypt filenames for maximum privacy
- **Theme Support** — System, Light, and Dark modes with proper disabled state styling
- **Comprehensive Logging** — File-based logs with timestamped entries and critical/general level separation

### 🔧 Developer-Friendly

- Clean, modular Python codebase with separate core encryption modules
- Thread-based architecture using `ThreadPoolExecutor` for responsive UI
- Extensible settings system (JSON-based configuration)
- Standalone Windows installer (no separate Python install required)

---

## Quick Start

### Installation

1. Download the latest installer from [GitHub Releases](https://github.com/ShahFaisalGfG/gfgLock/releases)
2. Run `gfgLock_Setup_x.x.x.exe` and follow the setup wizard
3. Optionally associate file extensions and enable context menu integration during installation
4. Launch gfgLock from the Start Menu or desktop shortcut

### Basic Usage

1. **Launch** the application
2. **Add files/folders** using drag & drop or "Add Files"/"Add Folders" buttons
3. **Select operation**:
   - For **Encryption**: Choose algorithm (AES-256 GCM, AES-256 CFB, or ChaCha20-Poly1305)
   - For **Decryption**: Extension is auto-detected
4. **Enter password** (confirm for encryption)
5. **Adjust settings** (threads, chunk size, filename encryption) if desired
6. **Click "Start"** and monitor progress in real-time
7. Review logs and summary in the progress dialog

---

## Installation Methods

### Option 1: Windows Installer (Recommended)

- Standalone executable with bundled dependencies
- One-click installation with modern UI wizard
- Optional file association and context menu integration
- Automatic uninstaller

### Option 2: Command Line (Developer)

```bash
# Clone repository
git clone https://github.com/ShahFaisalGfG/gfgLock.git
cd gfgLock

# Create virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run application
python -m gui
```

---

## Settings & Preferences

The Preferences window provides control over:

### Appearance Tab

- **Theme Selection** — System (default), Light, or Dark mode

### Encryption Tab

- **CPU Threads** — Number of threads for encryption operations
- **Chunk Size** — Processing block size (256 KB to 16 MB)
- **Encrypt Filenames** — Randomize output filenames for privacy

### Decryption Tab

- **CPU Threads** — Number of threads for decryption operations
- **Chunk Size** — Processing block size (256 KB to 16 MB)

### Advanced Tab

- **Encryption Mode** — Default algorithm for new encryption operations
- **Enable Logs** — Toggle logging system on/off
- **Log Level** — All logs or only critical errors
- **Action Buttons**:
  - **Clear All Logs** — Remove all log files
  - **Open Logs Folder** — View logs in file explorer

**Apply vs. Save:**

- **Apply** — Save settings and apply immediately without closing Preferences
- **Save** — Save settings, apply, and close the Preferences window

---

## File Extensions & Compatibility

| Algorithm         | Extension  | Description                              |
| ----------------- | ---------- | ---------------------------------------- |
| AES-256 GCM       | `.gfglock` | Galois/Counter Mode AEAD (primary)       |
| AES-256 CFB       | `.gfglck`  | Cipher Feedback mode, OpenSSL compatible |
| ChaCha20-Poly1305 | `.gfgcha`  | Stream cipher AEAD                       |

**Note:** Files encrypted with one algorithm cannot be decrypted with another. Always use the same tool to decrypt.

---

## Logging

Logs are stored in `%APPDATA%\gfgLock\logs\` (or `src/logs/` in development mode):

- **general.log** — All status messages and operations
- **critical.log** — Errors and critical issues only

### Log Format

```log
[YYYY-MM-DD HH:MM:SS] [Operation] Message
```

Example:

```log
[2025-12-19 14:32:45] Encrypting: document.pdf → document.pdf.gfglock
[2025-12-19 14:32:47] Encryption successful: document.pdf.gfglock (1.2 MB)
[2025-12-19 14:32:48] Critical Error: Failed to encrypt: corrupted_file.bin (Permission denied)
```

---

## Security Notes

- **Strong Passwords:** Use passwords of 12+ characters combining uppercase, lowercase, digits, and symbols
- **Unique Passwords:** Use different passwords for different sets of files
- **Algorithm Selection:**
  - **GCM Mode** — Recommended for most use cases (authenticated encryption)
  - **CFB Mode** — Compatible with legacy OpenSSL tools
  - **ChaCha20** — Excellent for high-security applications, resistant to hardware side-channels
- **Verification:** Always verify downloaded files using SHA-256 checksums (provided with releases)

---

## System Requirements

- **OS:** Windows 10 or later (64-bit)
- **RAM:** 2 GB minimum (4 GB recommended)
- **Disk Space:** 500 MB for installation
- **CPU:** Multi-core processor recommended for optimal performance

---

## Troubleshooting

### "Could not parse application stylesheet" warning

- Harmless Qt message; application will continue normally
- Can occur when switching themes; no data loss or corruption

### Files fail to decrypt

- Verify the file extension (`.gfglock`, `.gfglck`, or `.gfgcha`)
- Ensure the correct password is used
- Check file integrity (may be corrupted)
- Review critical logs for detailed error messages

### Performance issues

- Increase "CPU Threads" in Encryption/Decryption settings
- Reduce "Chunk Size" for large files
- Ensure sufficient RAM and disk space available
- Close other applications to free system resources

### Logs not being created

- Enable logs in Advanced settings
- Ensure `%APPDATA%\gfgLock\logs\` folder is writable
- Check Windows firewall/antivirus permissions

---

## Project Structure

```log
gfgLock/
├── src/
│   ├── gui.py                      # Main GUI and dialogs
│   ├── core/
│   │   ├── aes256_gcm_cfb.py       # AES-256 GCM/CFB encryption
│   │   └── chacha20_poly1305.py   # ChaCha20-Poly1305 encryption
│   ├── services/
│   │   └── worker.py               # Multi-threaded encryption/decryption
│   ├── views/
│   │   └── preferences.py           # Settings dialog
│   ├── utils/
│   │   ├── gfg_helpers.py           # Utilities (logging, settings)
│   │   ├── theme_manager.py         # Theme system (light/dark/system)
│   │   └── settings.json            # Default settings
│   ├── widgets/
│   │   └── custom_title_bar.py      # Frameless window title bar
│   └── assets/icons/
│       └── gfgLock.png              # Application icon
├── installer/
│   └── gfglock_installer.iss        # Inno Setup installer config
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

---

## Dependencies

- **PyQt5** — GUI framework
- **cryptography** — AES-256 encryption (OpenSSL backend)
- **pycryptodome** — ChaCha20-Poly1305 implementation

Full list in [requirements.txt](requirements.txt)

---

## Development

### Setup Development Environment

```bash
# Clone and navigate
git clone https://github.com/ShahFaisalGfG/gfgLock.git
cd gfgLock

# Create virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run application
python -m gui
```

### Building the Installer

Requires [Inno Setup](https://jrsoftware.org/isinfo.php):

```bash
# PyInstaller builds the executable
pyinstaller src/gfgLock_gui.spec

# Inno Setup creates the installer
iscc installer/gfglock_installer.iss
```

---

## CLI Usage (Advanced)

For command-line encryption/decryption without the GUI:

```bash
python -c "
from core.aes256_gcm_cfb import encrypt_file, decrypt_file
encrypt_file('document.pdf', 'password')  # Creates document.pdf.gfglock
decrypt_file('document.pdf.gfglock', 'password')  # Restores document.pdf
"
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) or [Release Notes](https://github.com/ShahFaisalGfG/gfgLock/releases) for version history.

---

## Contributing

Contributions are welcome! Please feel free to:

- Report bugs via [Issues](https://github.com/ShahFaisalGfG/gfgLock/issues)
- Submit feature requests
- Open pull requests with improvements

---

## License

MIT License — See [LICENSE](LICENSE) for details.

---

## Credits

**Developed by:** Shah Faisal (gfgRoyal)

**Repository:** [https://github.com/ShahFaisalGfG/gfgLock](https://github.com/ShahFaisalGfG/gfgLock)

**Portfolio:** [https://shahfaisalgfg.github.io/shahfaisal/](https://shahfaisalgfg.github.io/shahfaisal/)

---

## Support

For questions, issues, or suggestions:

- 📧 Open an issue on [GitHub Issues](https://github.com/ShahFaisalGfG/gfgLock/issues)
- 🔗 Visit the [project homepage](https://shahfaisalgfg.github.io/shahfaisal/)

---

**Stay Secure. Encrypt Responsibly.** 🔐
