# gfgLock - v2.6.9

**Release date:** 2025-12-19

**Release page:** [gfgLock v2.6.9 - GitHub Releases](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/v2.6.9)

---

## Overview

This is a major feature release introducing **multi-algorithm encryption support**, a **comprehensive logging system**, **enhanced theme support**, and numerous **UI/UX improvements**. Version 2.6.9 significantly expands the capabilities of gfgLock while maintaining the security and performance standards set in v1.0.0.

### Release Highlights

✨ **Multi-Algorithm Support** — Choose between AES-256 GCM, AES-256 CFB, or ChaCha20-Poly1305  
📝 **Advanced Logging System** — Real-time file logging with critical/general level separation  
🎨 **Enhanced Theming** — System, Light, and Dark modes with consistent disabled state styling  
⚙️ **Settings Management** — New Apply button for live testing before committing changes  
📁 **Smart File Filtering** — UI automatically filters compatible files based on operation mode  
🎯 **Improved UX** — Better algorithm selection, file management, and preference controls

---

## Major Features

### 🔐 Multi-Algorithm Encryption (NEW)

Three distinct encryption algorithms, each with its own file extension:

| Algorithm             | Extension  | Mode | Key Features                                          |
| --------------------- | ---------- | ---- | ----------------------------------------------------- |
| **AES-256 GCM**       | `.gfglock` | AEAD | Authenticated encryption, recommended for general use |
| **AES-256 CFB**       | `.gfglck`  | AEAD | OpenSSL-compatible, legacy support                    |
| **ChaCha20-Poly1305** | `.gfgcha`  | AEAD | Modern stream cipher, side-channel resistant          |

**Encryption Dialog Changes:**

- New algorithm dropdown in encryption mode (hidden in decryption mode)
- Default algorithm configurable in Advanced preferences
- Decryption automatically detects algorithm from file extension
- Prevents mismatched encryption/decryption attempts

### 📋 Comprehensive Logging System (NEW)

Real-time, file-based logging with immediate write-on-event:

**Log Location:** `%APPDATA%\gfgLock\logs\` (Windows) or `src/my_app/logs/` (development)

**Log Files:**

- `general.log` — All operations and status messages (when "All" log level selected)
- `critical.log` — Errors, authentication failures, and decryption failures (always written on error)

**Log Features:**

- **Timestamped Entries** — Every log line includes `[YYYY-MM-DD HH:MM:SS]` prefix
- **Immediate Writing** — Logs written to disk instantly on status/error events
- **Dual-Level Filtering** — Choose between "All" or "Critical Only" in preferences
- **Log Panel Export** — When switching to "All" level, current panel content exported with timestamps
- **Easy Access** — "Open Logs Folder" button launches logs directory in file explorer

**Advanced Settings UI:**

- Enable/Disable toggle with immediate persistence
- Log level dropdown (All / Critical)
- "Clear All Logs" button (styled in red)
- "Open Logs Folder" button (right-aligned)

**Example Log Output:**

```
[2025-12-19 14:32:45] Encrypting: document.pdf using AES-256 GCM
[2025-12-19 14:32:47] Encryption successful: document.pdf.gfglock (2.4 MB)
[2025-12-19 14:32:48] Critical Error: Failed to encrypt: corrupted_file.bin (Permission denied)
[2025-12-19 14:32:49] Skipped: already_encrypted.gfglock (File already encrypted)
```

### 🎨 Enhanced Theme Support (NEW)

Unified theme system with proper disabled widget styling:

**Theme Modes:**

- **System (Default)** — Respects Windows appearance settings
- **Light** — Bright, professional interface
- **Dark** — Eye-friendly dark mode with proper contrast

**Disabled State Styling:**

- **Light Mode:** Grey text (#999999) on light background (#f5f5f5), grey border
- **Dark Mode:** Dimmed text (#8a8a8a) on dark background (#2a2a2a), subtle border
- **Unified:** CSS-based theme rules ensure consistent disabled appearance across all widgets

**Fixed Issues:**

- Removed per-widget stylesheet overrides that conflicted with global theme
- Disabled buttons no longer appear white in dark mode
- Consistent palette for all disabled buttons and dropdowns

### ⚙️ Settings Improvements (NEW)

**New Apply Button:**

- Located next to Save button in Preferences window
- Applies settings immediately without closing the dialog
- Allows real-time testing of theme, logging, and encryption settings
- Emits `settings_changed` signal for immediate GUI updates

**Preference Controls:**

- **Appearance Tab:** Theme selection with live preview
- **Encryption Tab:** CPU threads, chunk size, filename encryption toggle
- **Decryption Tab:** CPU threads and chunk size configuration
- **Advanced Tab:**
  - Default encryption algorithm selector
  - Logging enable/disable with immediate persistence
  - Log level dropdown (All / Critical)
  - Log management buttons (Clear/Open)

### 📁 Smart File Management (NEW)

**Mode-Based File Filtering:**

- **Encrypt Mode:** Only shows unencrypted files; filters out `.gfglock`, `.gfglck`, `.gfgcha` extensions
- **Decrypt Mode:** Only shows encrypted files with recognized extensions
- Prevents confusion and invalid operation attempts

**UI Enhancements:**

- "Remove Selected" button with automatic enable/disable state
- Button greyed out when no files selected
- Clear visual feedback for available actions
- Drag & drop supports filtering rules

### 🔧 Worker & Core Modules (NEW)

**Multi-Algorithm Dispatch:**

- Worker accepts `enc_algo` parameter for encryption operations
- Automatically dispatches to correct encryption module:
  - `enc_algo='aes_gcm'` → AES-256 GCM encryption
  - `enc_algo='aes_cfb'` → AES-256 CFB encryption
  - `enc_algo='chacha20'` → ChaCha20-Poly1305 encryption
- Decryption inspects file extension to determine algorithm

**Error Handling:**

- Graceful handling of mismatched file extensions
- Clear error messages for authentication failures
- Retry logic for transient failures
- Detailed critical logging of encryption/decryption errors

---

## Technical Improvements

### Code Architecture

**Modular Design:**

```
src/my_app/
├── core/                    # Encryption algorithms
│   ├── aes256_gcm_cfb.py   # AES-256 GCM/CFB dual implementation
│   └── xchacha20_poly1305.py# ChaCha20-Poly1305 implementation
├── services/
│   └── worker.py            # Multi-threaded operations dispatcher
├── views/
│   └── preferences.py        # Settings dialog with logging UI
├── utils/
│   ├── gfg_helpers.py        # Logging utilities & settings management
│   └── theme_manager.py      # Dynamic theme application
├── widgets/
│   └── custom_title_bar.py  # Frameless window title bar
└── gui.py                    # Main window & encryption dialog
```

**Key Methods:**

- `EncryptDialog.update_count_label()` — Manages Remove Selected button state
- `EncryptDialog.on_status()` — Writes general logs with automatic critical detection
- `EncryptDialog.on_error()` — Writes critical logs immediately
- `PreferencesWindow.apply_settings()` — Applies settings without closing
- `PreferencesWindow.save_and_close()` — Applies settings and closes
- `PreferencesWindow._persist_log_level()` — Exports current logs with timestamps
- `get_logs_dir()` — Creates/returns logs directory

### Performance

- **Chunked Processing:** Configurable chunk sizes (256 KB - 16 MB) for memory-efficient operations
- **Multi-Threaded:** Adjustable thread count per operation for optimal CPU utilization
- **Streaming:** AEAD implementations use streaming for large file support
- **Theme Caching:** Dynamic stylesheet application with minimal redraws

### Security

- **Authenticated Encryption:** All algorithms use AEAD (GCM, CFB with MAC, ChaCha20-Poly1305)
- **Strong Key Derivation:** SHA-256 based key derivation from passwords
- **No Hardcoded Credentials:** All passwords user-provided, never stored
- **Secure Defaults:** 12+ character password recommendation in UI
- **Algorithm Isolation:** Clear separation between encryption implementations

---

## Bug Fixes & Refinements

### Fixed Issues

- ✅ Disabled buttons no longer white in dark theme
- ✅ Per-widget stylesheets no longer conflict with global theme CSS
- ✅ Log panel content properly exported with timestamps when switching log level
- ✅ File filtering prevents invalid encrypt/decrypt operations
- ✅ Remove Selected button state correctly toggled based on selection
- ✅ Settings changes apply immediately without closing preferences

### Refinements

- 🔹 Improved error messages with specific failure reasons
- 🔹 Better file extension validation with helpful feedback
- 🔹 Consistent timestamp format across all logs
- 🔹 Cleaner preferences UI with logical grouping
- 🔹 More responsive theme switching with Apply button

---

## Breaking Changes

### File Extension Format

**v1.0.0 → v2.6.9 Changes:**

| Version | Extension  | Algorithm         | Encrypted File Header |
| ------- | ---------- | ----------------- | --------------------- |
| v1.0.0  | `.gfglock` | AES-256 CFB       | `GFGL` + mode byte    |
| v2.6.9  | `.gfglock` | AES-256 GCM       | `GFGL` (no mode byte) |
| v2.6.9  | `.gfglck`  | AES-256 CFB       | `GFGC`                |
| v2.6.9  | `.gfgcha`  | ChaCha20-Poly1305 | `GFGX`                |

**Migration Notes:**

- Files encrypted with v1.0.0 (`.gfglock`) use AES-256 CFB with mode byte — **not compatible** with v2.6.9 GCM format
- To upgrade: Decrypt v1.0.0 files with v1.0.0, then re-encrypt with v2.6.9 using desired algorithm
- v1.0.0 CLI backend (`gfglock_fast_aes256_cryptography.py`) remains available for legacy support

### Settings Migration

v1.0.0 settings format remains compatible; new settings (encryption_mode, enable_logs, log_level) added with defaults if missing.

---

## Installation & Upgrades

### Fresh Installation

Download from [GitHub Releases](https://github.com/ShahFaisalGfG/gfgLock/releases/tag/v2.6.9):

- `gfgLock_Setup_2.6.9.exe` — Windows installer (recommended)
- `gfgLock_Setup_2.6.9.rar` — Archive containing installer

### Upgrading from v1.0.0

1. Backup any important encrypted files
2. Optionally decrypt files (they'll use v1.0.0 format)
3. Uninstall v1.0.0 via Control Panel
4. Install v2.6.9 using new installer
5. Re-encrypt files with chosen algorithm if desired
6. (Optional) Delete old v1.0.0 installation folder to free space

**Note:** Logs and settings from v1.0.0 will be preserved; they're compatible with v2.6.9.

---

## System Requirements

- **OS:** Windows 10 or later (64-bit only)
- **RAM:** 2 GB minimum; 4 GB+ recommended for large files
- **Disk Space:** 500 MB for installation; additional space for encrypted files
- **CPU:** Multi-core processor recommended for optimal performance

---

## Binaries & Checksums

### Available Downloads

| File                      | Size    | SHA-256          |
| ------------------------- | ------- | ---------------- |
| `gfgLock_Setup_2.6.9.exe` | ~140 MB | [To be computed] |
| `gfgLock_Setup_2.6.9.rar` | ~145 MB | [To be computed] |

**Verify Downloaded File (PowerShell):**

```powershell
Get-FileHash -Path "gfgLock_Setup_2.6.9.exe" -Algorithm SHA256
```

---

## Known Issues & Limitations

### Known Issues

- "Could not parse application stylesheet" warning may appear on theme switch (harmless, no data loss)
- Context menu integration requires admin privileges on some Windows 10 systems

### Limitations

- Windows only (Linux/macOS support in future roadmap)
- 64-bit only (no 32-bit build)
- File association limited to `.gfglock`, `.gfglck`, `.gfgcha` extensions
- Maximum file size limited by available RAM (for non-streaming operations)

### Future Roadmap

- 🔮 Cross-platform support (Linux, macOS)
- 🔮 Resumable/pause encryption for very large files
- 🔮 Cloud integration (OneDrive, Google Drive, AWS S3)
- 🔮 Batch scheduling (encrypt/decrypt on schedule)
- 🔮 File integrity verification (hash-based checksums)
- 🔮 Hardware acceleration (GPU-accelerated AES-NI support)

---

## Credits & Support

**Developer:** Shah Faisal (gfgRoyal)

**Repository:** [github.com/ShahFaisalGfG/gfgLock](https://github.com/ShahFaisalGfG/gfgLock)

**Portfolio:** [shahfaisalgfg.github.io/shahfaisal/](https://shahfaisalgfg.github.io/shahfaisal/)

**Report Issues:** [GitHub Issues](https://github.com/ShahFaisalGfG/gfgLock/issues)

---

## License

MIT License — See repository for full license text.

---

## Comparison: v1.0.0 → v2.6.9

| Feature                  | v1.0.0           | v2.6.9                              |
| ------------------------ | ---------------- | ----------------------------------- |
| **Algorithms**           | AES-256 CFB only | AES-256 GCM, CFB, ChaCha20-Poly1305 |
| **File Extensions**      | `.gfglock`       | `.gfglock`, `.gfglck`, `.gfgcha`    |
| **Logging**              | None             | Comprehensive file-based logging    |
| **Themes**               | Light only       | System, Light, Dark                 |
| **Preferences**          | Basic            | Advanced with Apply button          |
| **File Filtering**       | Manual           | Automatic by algorithm              |
| **Remove Selected**      | No               | Yes, with state management          |
| **Log Levels**           | N/A              | All / Critical                      |
| **Settings Persistence** | Save only        | Apply + Save                        |

---

## Thank You

Thank you for using gfgLock! Your feedback and contributions drive continuous improvement.

**Stay Secure. Encrypt Responsibly.** 🔐

---

**Release Information:**

- **Version:** 2.6.9
- **Release Date:** December 19, 2025
- **Build Type:** Production Release
- **Status:** Stable
