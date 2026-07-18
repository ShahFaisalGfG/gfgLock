# gfgLock v2.6.9 - Release Notes

**Released:** December 19, 2025 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v2.6.9 is the initial public release of gfgLock - a free, open-source file encryption app for Windows. It ships multi-algorithm authenticated encryption, real-time logging, live theme switching, and a configurable batch-processing workflow.

---

## Added

### Encryption

- **AES-256 GCM** (`.gfglock`) - authenticated encryption, hardware-accelerated. Recommended default.
- **AES-256 CFB** (`.gfglck`) - stream cipher; highest throughput, ideal for speed-critical batch workflows.
- **ChaCha20-Poly1305** (`.gfgcha`) - authenticated, constant-time; suited for CPUs without AES-NI and side-channel–sensitive environments.
- **Auto-detected decryption** - the algorithm is selected automatically from the encrypted file's extension; no manual selection required.
- **Chunk-based processing** - configurable chunk sizes (Off / 8 MB / 16 MB / 32 MB / 64 MB / 128 MB) for large-file handling. *Off* loads the entire file into RAM for maximum speed on small files.
- **Multi-threaded batch operations** - encrypt or decrypt entire folders using multiple CPU threads, configurable in Preferences.

### Interface

- **Drag & drop** - drop files or folders directly onto the window.
- **File Explorer context menu** - right-click any file → *Encrypt with gfgLock* / *Decrypt with gfgLock*.
- **Live theme switching** - System, Light, and Dark themes with instant preview.
- **Real-time progress** - per-file progress bar during active operations.

### Logging

- **File-based logging** - all operations recorded to `%APPDATA%\gfgLock\logs\`.
- **Two log levels** - *Full* (all operations) and *Critical* (errors only), selectable in **Preferences → Advanced**.
- **Log management** - clear logs or open the logs folder directly from Preferences.

### Preferences

- **CPU threads** - 1 to *(cores − 1)*; balance raw speed against system responsiveness.
- **Chunk size** - select from Off to 128 MB depending on file sizes and available RAM.
- **Default algorithm** - pre-select the cipher at startup.
- **Encrypt filenames** - optionally randomise output filenames.

---

## Known Issues

- The context menu may behave unexpectedly when a large number of files are selected simultaneously. As a workaround, place files in a folder and use **Add Folder** or drag the folder onto the window.

---

## Installation

Download `gfgLock_2.6.9_installer.exe` from the [Releases](https://github.com/ShahFaisalGfG/gfgLock/releases) page and run the installer. A portable executable (`gfgLock_portable.exe`) is also available for environments where installation is not possible - note that the portable build is unsigned.

---

*Stay secure. Encrypt responsibly.*
