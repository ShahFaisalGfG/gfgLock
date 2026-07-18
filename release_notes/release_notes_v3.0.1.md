# gfgLock v3.0.1 - Release Notes

**Released:** July 2026 · **Status:** Stable · **Platform:** Windows 10 / 11 (64-bit)

---

v3.0.1 is a maintenance release. It adds a startup splash screen and fixes an installer defect that could leave duplicate entries in Add/Remove Programs.

---

## Breaking Changes

None. All files encrypted with v3.0.0 are fully compatible with v3.0.1. No re-encryption or migration step is required.

---

## Added

- **Startup splash screen** - the app now shows a splash screen with live dependency-loading progress while it boots, instead of a blank window during startup.

## Fixed

- **Duplicate Add/Remove Programs entries** - the system and per-user installers used a malformed `AppId` that didn't match between the two. Installing one after the other (or switching install modes) could leave two separate entries. Both installers now share the same, correctly-formatted `AppId`.
- **User installer uninstall hang risk** - the per-user (no-admin) installer no longer schedules a reboot-time file replacement for the shell extension DLL. That mechanism requires administrator privileges the user installer doesn't have; if left in place, it could get skipped or leave the DLL behind. If Explorer holds the DLL locked at uninstall time, it's now simply left behind as a harmless orphan, since its registry entries are already removed.

## Changed

- Removed stale, build-generated DLLs that had been accidentally committed to the repository, and added `.gitignore` rules for vcpkg's `applocal` deployment artifacts so this can't recur. No effect on the shipped application.

---

## Dependencies

No dependency changes since v3.0.0.

---

## Upgrading

1. Uninstall the previous version via **Add/Remove Programs** (or delete the portable folder).
2. Install the v3.0.1 package that fits your environment:
   - `gfgLock_3.0.1_system_installer.exe` - system-wide, requires administrator.
   - `gfgLock_3.0.1_user_installer.exe` - per-user, no administrator required.
   - `gfgLock_3.0.1_portable.exe` - portable, no installation required.
3. No file re-encryption needed. All files encrypted with earlier versions are decryptable with v3.0.1.

> **Upgrading from v3.0.0 or earlier:** if Add/Remove Programs previously showed two gfgLock entries, uninstall both before installing v3.0.1.

---

*Stay secure. Encrypt responsibly.*
