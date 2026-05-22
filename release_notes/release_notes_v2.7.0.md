# gfgLock v2.7.0 — Release Notes

**Release Date:** December 21, 2025  
**Version:** 2.7.0  
**Status:** Stable  
**Platform:** Windows 10+ (64-bit)

---

## Summary

gfgLock v2.7.0 focuses on performance and usability: faster encryption, hardware acceleration where available, and a new streamed (non-chunk) mode for special workflows.

## Highlights

- Optimized core encryption algorithms for improved throughput and lower CPU overhead.
- Added hardware acceleration support (AES-NI) and improved crypto backend detection.
- Added streamed, non-chunk mode (chunk_size: "Off") — useful for small files and streaming scenarios.
- General stability and minor bug fixes.

## Notes

- Streamed mode processes data without fixed chunk buffers; use `Off` for small files or when streaming semantics are desired.
- Hardware acceleration is used automatically when supported by the host CPU and crypto backend.

## Installation

Download `gfgLock_Setup_2.7.0.exe` from Releases and run the installer.

---

Last Updated: December 21, 2025
