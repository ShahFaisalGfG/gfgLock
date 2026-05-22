# gfgLock v3.0.0 — Release Notes

**Released:** June 2026

---

## Overview

v3.0.0 introduces a native C++ encryption engine backed by OpenSSL that delivers hardware-accelerated performance across all supported cipher modes. The release also ships a dedicated native build script and a full automated test suite.

---

## Breaking Changes

None. All files encrypted with v2.7.5 are fully compatible with v3.0.0. No re-encryption or migration step is required.

---

## What's New

### Native C++ Encryption Engine

A new C++ extension (`gfglock_native.pyd`) provides hardware-accelerated implementations of every supported cipher mode and the key-derivation function:

| Operation | Algorithm |
| --- | --- |
| Encrypt / Decrypt | AES-256-GCM |
| Encrypt / Decrypt | AES-256-CFB |
| Encrypt / Decrypt | ChaCha20-Poly1305 |
| Key Derivation | PBKDF2-HMAC-SHA256 |

### Transparent Python Fallback

If the native extension is unavailable the application falls back automatically to the existing Python implementation. The fallback is silent — the user experience, file format, and output are identical on both paths. Files encrypted by the native path are fully decryptable by the Python fallback and vice versa.

### Test Suite

A `pytest` test suite under `tests/` validates all cipher modes on both the native and Python paths, including cross-path round-trip compatibility (encrypt via C++, decrypt via Python and vice versa):

```powershell
pytest
```

---

## Bug Fixes

- **Application startup reliability** — an initialisation ordering issue that could affect application launch in certain environments has been resolved.

---

## Build & Tooling

### `scripts/build_native.ps1`

A self-contained PowerShell script that compiles the native extension from source and places it alongside the Python package. No manual toolchain configuration is required beyond having Visual Studio Build Tools installed.

Steps performed:

1. Locates the MSVC toolchain via `vswhere.exe` and configures the x64 environment.
2. Bootstraps vcpkg (first run only) and installs OpenSSL and pybind11 from `native/vcpkg.json`.
3. Configures and builds the CMake project in Release mode with parallel jobs.
4. Verifies the compiled extension is importable via a Python smoke test.

**Requirements:** Visual Studio 2022 or newer Build Tools (Desktop development with C++ workload), CMake ≥ 3.25. Internet access is required on the first run for the vcpkg bootstrap and OpenSSL download.

### Build Scripts `scripts/`

All build and release scripts have been moved from the project root into `scripts/`. A single command produces the complete distributable — native extension, PyInstaller bundle, and all three installer variants:

```powershell
.\scripts\build.ps1
```

---

## Dependencies

| Package | Version | Notes |
| --- | --- | --- |
| PySide6 | 6.7+ | unchanged |
| cryptography | 46.0+ | unchanged (AES-256 Python fallback) |
| pycryptodome | 3.20+ | relaxed from 3.23 (ChaCha20 Python fallback) |
| py-cpuinfo | 9.0+ | unchanged |
| pytest | 8.0+ | dev only |
| pybind11 | 2.12+ | build only, installed via vcpkg |
| OpenSSL | via vcpkg | build only, statically linked into `.pyd` |

---

## Upgrading

1. Uninstall the previous version via **Add/Remove Programs** (or delete the portable folder).
2. Install the appropriate v3.0.0 package:
   - `gfgLock_3.0.0_system_installer.exe` — system-wide installation, requires administrator.
   - `gfgLock_3.0.0_user_installer.exe` — per-user installation, no administrator required.
   - `gfgLock_3.0.0_portable.exe` — portable, no installation required.
3. No file re-encryption is needed. All files encrypted with earlier versions are decryptable with v3.0.0.

---

**Stay Secure. Encrypt Responsibly.**
