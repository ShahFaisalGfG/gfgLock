# gfgLock v3.2.1 - Release Notes

**Released:** November 2026 · **Status:** Stable · **Platform:** Windows 10 (1809 or later) / 11 (64-bit)

---

v3.2.1 lets gfgLock keep itself up to date. It checks for a new version once a day, downloads it in the background, and installs it when you close gfgLock, after checking the publisher's signature on every file. Both steps can be turned off.

---

## Updating to 3.2.1

gfgLock 3.2.0 and older can't update themselves, so install this version once over your current one:

- `winget upgrade gfgRoyal.gfgLock`, or
- the installer you used before (system or user), from the assets below, or
- the new portable exe in place of the old one.

Your settings and logs are kept. From 3.2.1 on, updates arrive on their own.

---

## Added

- **Automatic updates.** Once a day gfgLock asks GitHub whether a newer version is out. A copy installed with either installer, or the portable exe, downloads the new version in the background and installs it when you close gfgLock. **Restart now** in the notice installs it at once and opens the new version. An all-users install asks for administrator approval, as installing it did; if the prompt is declined, gfgLock doesn't ask again on every close, and the notice offers **Install now**.
- **Signed updates.** Each release carries a list of its files with their SHA-256 checksums, signed with the publisher's key (ECDSA P-256). gfgLock checks that signature with Windows' own crypto, then checks every downloaded file against its checksum, and checks both again just before the installer starts, while the files are locked against changes. Anything that doesn't match is deleted, never run.
- **Preferences > Updates.** **Check automatically** and **Install automatically**, both on by default, plus **Check now** and when the last check ran.
- **Update notice** at the top of the window: the new version, its download progress, **Release notes**, and **Skip this version**.

## Changed

- **Check for updates** in the About dialog (**F1**) checks in place and shows the result there; **Releases** opens the releases page.
- **Privacy:** the update check is gfgLock's only network connection. It sends gfgLock's name and version to GitHub, never your files, passwords, or settings. Downloads wait while Windows reports a metered connection, and run at background priority so they don't slow the PC.
- The portable `.7z` folder can't replace itself, so its notice links to the new release instead.

## Notes

- A download stopped halfway (closing gfgLock, a lost connection) resumes where it stopped.
- The updater keeps its state in `updates.json` beside `settings.json`, and downloads in `%LOCALAPPDATA%\gfgLock\updates` (the portable exe keeps both in its `gfgLock data` folder). Finished downloads are removed once the new version starts.
