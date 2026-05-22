# gfgLock v2.6.9 — Release Notes

**Release Date:** December 19, 2025  
**Version:** 2.6.9  
**Status:** Stable  
**Platform:** Windows 10+ (64-bit)

---

## Summary

gfgLock v2.6.9 is the initial public release. It provides multi-algorithm file encryption (AES-256 GCM/CFB, ChaCha20-Poly1305), real-time file logging, theme support, and a compact, responsive GUI focused on secure batch workflows.

## Major Highlights

- Multi-algorithm encryption: AES-256 GCM (`.gfglock`), AES-256 CFB (`.gfglck`), ChaCha20-Poly1305 (`.gfgcha`)
- Real-time, file-based logging with general and critical logs
- Theme support (System/Light/Dark) and live Apply
- Preferences with configurable threads and chunk sizes

## Important Notes

- Decryption selects the algorithm automatically based on file extension.
- Logs (frozen app): `%APPDATA%\gfgLock\logs\`
- Portable single-file executable available: `gfgLock_portable.exe` - unsigned

## Chunk Size & Encryption Mode Quick Guide

**Chunk Sizes:**

- **Off (no chunking):** Fastest for small files (<10 MB); loads entire file in RAM
- **8 MB (default):** Balanced; recommended for most users
- **16-32 MB:** Better for large files (>100 MB) on modern systems
- **64+ MB:** Enterprise setups with high-speed NVMe storage

**Encryption Modes:**

- **AES-256 GCM** (`.gfglock`): **Recommended**—authenticated, secure, hardware-accelerated
- **AES-256 CFB** (`.gfglck`): **Fastest**—aauthentication, ideal for speed-critical use
- **ChaCha20-Poly1305** (`.gfgcha`): Side-channel resistant, excellent for high-security scenarios

## Installation (brief)

Download `gfgLock_2.6.9_installer.exe` from Releases and run the installer.

## Changelog (condensed)

- Added: AES-256 GCM, AES-256 CFB, ChaCha20-Poly1305
- Added: File-based logging and log management
- Improved: Theme handling and Preferences UX

## Known Issues

- Context menu may behave unexpectedly when many files are selected; use drag & drop or place files in a folder as a workaround.

---

Last Updated: December 19, 2025  
For full usage and screenshots, see [`README.md`](readme.md) in the repository.
