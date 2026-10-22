; =======================================================
; gfgLock Windows installer for the current user (no admin rights)
; Inno Setup script. The parts it shares with the all-users
; installer are in common.iss.
; =======================================================

#include "common.iss"

[Setup]
PrivilegesRequired=lowest
; Per-user AppData (Roaming), which also holds this user's settings and logs
DefaultDirName={userappdata}\{#MyAppName}
OutputBaseFilename={#MyAppName}_{#MyAppVersion}_user_installer

[Files]
; Scheduling a replacement or deletion for the next restart (restartreplace, uninsrestartdelete)
; needs admin rights, so this installer relies on moving the shell DLL aside. One that Explorer
; still holds at uninstall stays behind as a harmless orphan; its registry entries are removed.
Source: "{#ShellDll}"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Up to 3.1.0 this installer put its Start menu items at the top level; they now sit in the same
; gfgLock folder as the all-users installer's
Type: files; Name: "{userprograms}\{#MyAppName}.lnk"
Type: files; Name: "{userprograms}\{cm:UninstallProgram,{#MyAppName}}.lnk"

[UninstallDelete]
; Installed files are removed by the uninstaller itself. This user's settings and logs (in
; %APPDATA%\gfgLock) go too. Folders go only when empty, so an install location that already
; held other files never loses them.
Type: files; Name: "{userappdata}\{#MyAppName}\settings.json"
Type: files; Name: "{userappdata}\{#MyAppName}\settings.json.tmp"
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\logs"
Type: dirifempty; Name: "{userappdata}\{#MyAppName}"
Type: dirifempty; Name: "{app}"

[Code]
function SystemInstallExists(): Boolean;
var
  S: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\{#MyAppPublisher}\{#MyAppName}', 'InstallPath', S) or InstallExists(HKLM);
end;

function InitializeSetup(): Boolean;
begin
  Result := not SystemInstallExists();
  if not Result then
    SuppressibleMsgBox(
      'gfgLock is already installed for all users on this PC.' + #13#10#13#10 +
      'Update it with the all-users (system) installer instead.',
      mbError, MB_OK, IDOK);
end;

// Clean up system-wide CLSID entries left by older system installs. Deleting them needs admin
// rights, so this works only when Setup runs elevated.
procedure RemoveStaleSystemRegistryEntries();
begin
  RegDeleteKeyIncludingSubkeys(HKLM, ExpandConstant('Software\Classes\CLSID\{#EncryptClsid}'));
  RegDeleteKeyIncludingSubkeys(HKLM, ExpandConstant('Software\Classes\CLSID\{#DecryptClsid}'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveStaleSystemRegistryEntries();
end;
