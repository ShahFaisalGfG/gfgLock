# gfgLock v3.0.0 — Release Notes

**Released:** June 2026 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v3.0.0 ships a native C++ encryption engine backed by OpenSSL, delivering hardware-accelerated performance across all supported cipher modes, alongside a full automated test suite and a single-command build pipeline.

---

## Breaking Changes

None. All files encrypted with v2.7.5 are fully compatible with v3.0.0. No re-encryption or migration step is required.

---

## Added

- **Native C++ encryption engine** — a new compiled extension (`gfglock_native.pyd`) provides hardware-accelerated AES-256-GCM, AES-256-CFB, ChaCha20-Poly1305, and PBKDF2-HMAC-SHA256 via OpenSSL.
- **Transparent Python fallback** — if the native extension is unavailable, the app falls back silently to the existing Python implementation. File format and output are identical on both paths; files encrypted by one path are fully decryptable by the other.
- **Automated test suite** — a `pytest` suite under `tests/` validates all cipher modes on both the native and Python paths, including cross-path round-trip compatibility (encrypt via C++, decrypt via Python, and vice versa). Run with `pytest`.
- **`scripts/build_native.ps1`** — a self-contained PowerShell script that locates MSVC via `vswhere.exe`, bootstraps vcpkg, installs OpenSSL and pybind11, compiles the CMake project in Release mode, and verifies the extension with a Python smoke test.

## Changed

- **Build scripts moved to `scripts/`** — all build and release scripts relocated from the project root into `scripts/`. A single command `.\scripts\build.ps1` now produces the complete distributable: native extension, PyInstaller bundle, and all three installer variants.

## Fixed

- **Application startup reliability** — an initialisation ordering issue that could affect launch in certain environments has been resolved.

---

## Dependencies

| Package | Version | Notes |
| --- | --- | --- |
| PySide6 | 6.7+ | unchanged |
| cryptography | 46.0+ | unchanged — AES-256 Python fallback |
| pycryptodome | 3.20+ | relaxed from 3.23 — ChaCha20 Python fallback |
| py-cpuinfo | 9.0+ | unchanged |
| pytest | 8.0+ | dev only |
| pybind11 | 2.12+ | build only, via vcpkg |
| OpenSSL | via vcpkg | build only, statically linked into `.pyd` |

---

## Upgrading

1. Uninstall the previous version via **Add/Remove Programs** (or delete the portable folder).
2. Install the v3.0.0 package that fits your environment:
   - `gfgLock_3.0.0_system_installer.exe` — system-wide, requires administrator.
   - `gfgLock_3.0.0_user_installer.exe` — per-user, no administrator required.
   - `gfgLock_3.0.0_portable.exe` — portable, no installation required.
3. No file re-encryption needed. All files encrypted with earlier versions are decryptable with v3.0.0.

> **First build note:** vcpkg will clone from GitHub and download OpenSSL on the first native build — internet access required.

---

*Stay secure. Encrypt responsibly.*
