# gfgLock v2.7.0 - Release Notes

**Released:** December 21, 2025 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v2.7.0 is a focused performance release: optimised cipher throughput, automatic AES-NI hardware acceleration, and a new stream mode for small-file and low-latency workflows.

---

## Breaking Changes

None. All files encrypted with v2.6.9 are fully compatible with v2.7.0.

---

## Added

- **Stream mode (`chunk_size: Off`)** - processes the entire file in a single pass without chunk buffers. Fastest option for files under ~10 MB; loads the full file into RAM. Select *Off* in **Preferences → Chunk Size**.
- **AES-NI hardware detection** - detects whether the host CPU supports AES-NI at startup and routes encryption through the hardware-accelerated code path automatically when available.

## Changed

- **Optimised cipher performance** - internal encryption and decryption routines reworked for improved throughput and lower CPU overhead across all three supported algorithms.

## Fixed

- General stability improvements and minor edge-case bug fixes.

---

## Upgrading

Download `gfgLock_Setup_2.7.0.exe` from the [Releases](https://github.com/ShahFaisalGfG/gfgLock/releases) page and run the installer. No file re-encryption is required.

---

*Stay secure. Encrypt responsibly.*
