; =======================================================
; gfgLock Windows installer for all users (needs admin rights)
; Inno Setup script. The parts it shares with the per-user
; installer are in common.iss.
; =======================================================

#include "common.iss"

[Setup]
PrivilegesRequired=admin
DefaultDirName={autopf}\{#MyAppName}
OutputBaseFilename={#MyAppName}_{#MyAppVersion}_system_installer

[Files]
; restartreplace is the fallback for a shell DLL that could not be moved aside; uninsrestartdelete
; removes one that Explorer still holds at uninstall when Windows next starts
Source: "{#ShellDll}"; DestDir: "{app}"; Flags: ignoreversion restartreplace uninsrestartdelete

[Registry]
; Where the per-user installer looks for a copy installed for all users
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}"; Flags: uninsdeletekeyifempty
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "ExePath"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

[UninstallDelete]
; Installed files are removed by the uninstaller itself. The folder goes only when it is empty, so
; installing into a folder that already held other files can never cost those files. Settings and
; logs live in each user's %APPDATA%\gfgLock and are kept for a reinstall.
Type: dirifempty; Name: "{app}"

[Code]
var
  UserDataMoved: Boolean;

// This user's data folder, which the copy installed for all users reads too.
function UserDataDir(): String;
begin
  Result := ExpandConstant('{userappdata}\{#MyAppName}');
end;

// Where the settings and logs wait while the per-user copy is removed.
function KeptDataDir(): String;
begin
  Result := UserDataDir() + ' (kept by Setup)';
end;

// Moves one file or folder from FromDir to ToDir; True when it moved.
function MoveDataItem(const Name, FromDir, ToDir: String): Boolean;
var
  Source, Target: String;
begin
  Result := False;
  Source := AddBackslash(FromDir) + Name;
  Target := AddBackslash(ToDir) + Name;
  if not FileExists(Source) and not DirExists(Source) then
    Exit;
  if FileExists(Target) or DirExists(Target) then
    Log('Left ' + Source + ' where it is: ' + Target + ' already exists')
  else if not ForceDirectories(ToDir) then
    Log('Could not create ' + ToDir)
  else
  begin
    Result := RenameFile(Source, Target);
    if not Result then
      Log('Could not move ' + Source + ' to ' + Target);
  end;
end;

// Every per-user uninstaller deletes this user's settings and logs, so they move to a sibling
// folder until the per-user copy is gone.
procedure KeepUserData();
begin
  if MoveDataItem('settings.json', UserDataDir(), KeptDataDir()) then
    UserDataMoved := True;
  if MoveDataItem('logs', UserDataDir(), KeptDataDir()) then
    UserDataMoved := True;
end;

// Puts back what KeepUserData moved; a later call does nothing.
procedure RestoreUserData();
begin
  if not UserDataMoved then
    Exit;
  MoveDataItem('settings.json', KeptDataDir(), UserDataDir());
  MoveDataItem('logs', KeptDataDir(), UserDataDir());
  RemoveDir(KeptDataDir());
  UserDataMoved := False;
end;

// Runs the uninstaller of the per-user entry Key silently; an entry whose uninstaller is gone is
// deleted instead. True when nothing failed.
function RunUserUninstaller(const Key: String): Boolean;
var
  UninstExe: String;
  ResultCode: Integer;
begin
  Result := True;
  if not RegQueryStringValue(HKCU, Key, 'UninstallString', UninstExe) then
    Exit;
  UninstExe := RemoveQuotes(UninstExe);
  if not FileExists(UninstExe) then
    RegDeleteKeyIncludingSubkeys(HKCU, Key)
  else if not Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := False
  else
    Result := ResultCode = 0;
end;

// Removes the per-user copy and its stale 2.6.9-3.0.0 entry; this user's settings and logs stay.
function RemoveUserInstall(): Boolean;
begin
  KeepUserData();
  Result := RunUserUninstaller(CurrentUninstallKey());
  if Result and StaleInstallExists(HKCU) then
    Result := RunUserUninstaller(StaleUninstallKey());
  if Result then
    Result := not InstallExists(HKCU);
end;

// The per-user copy is removed before Setup's own AppMutex check runs, so gfgLock must be closed
// first: its uninstaller would fail on a running copy, and older ones end it by force.
function AppClosed(): Boolean;
begin
  Result := True;
  while CheckForMutexes('{#AppMutexes}') do
    if SuppressibleMsgBox('gfgLock is running. Close it, then click OK to continue.',
      mbError, MB_OKCANCEL, IDCANCEL) <> IDOK then
    begin
      Result := False;
      Exit;
    end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not InstallExists(HKCU) then
    Exit;
  if SuppressibleMsgBox(
    'gfgLock is installed for your account only.' + #13#10#13#10 +
    'Click Yes to remove that copy and install gfgLock for all users. Your settings and logs are kept.' + #13#10 +
    'Click No to cancel, then update that copy with the per-user installer instead.',
    mbConfirmation, MB_YESNO, IDYES) = IDNO then
  begin
    Result := False;
    Exit;
  end;
  if not AppClosed() then
  begin
    Result := False;
    Exit;
  end;
  if not RemoveUserInstall() then
  begin
    RestoreUserData();
    SuppressibleMsgBox(
      'The copy of gfgLock installed for your account could not be removed.' + #13#10#13#10 +
      'Uninstall it in Settings > Apps, then run this installer again.',
      mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

// Removes this user's association of Ext with gfgLock's ProgId, which would override the one
// written for all users; an extension another program owns is left alone.
procedure RemoveUserAssociation(const Ext, ProgId: String);
var
  Value: String;
begin
  if RegQueryStringValue(HKCU, 'Software\Classes\' + Ext, '', Value) and (CompareText(Value, ProgId) = 0) then
  begin
    RegDeleteValue(HKCU, 'Software\Classes\' + Ext, '');
    RegDeleteKeyIfEmpty(HKCU, 'Software\Classes\' + Ext);
  end;
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\' + ProgId);
end;

// Clean up per-user CLSID, context-menu, and file-association entries left by older per-user
// installs; they would override the ones written for all users.
procedure RemoveStaleUserRegistryEntries();
begin
  RegDeleteKeyIncludingSubkeys(HKCU, ExpandConstant('Software\Classes\CLSID\{#EncryptClsid}'));
  RegDeleteKeyIncludingSubkeys(HKCU, ExpandConstant('Software\Classes\CLSID\{#DecryptClsid}'));
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt');
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt');
  RemoveUserAssociation('.gfglock', 'gfgLock.gfglock');
  RemoveUserAssociation('.gfglck', 'gfgLock.gfglck');
  RemoveUserAssociation('.gfgcha', 'gfgLock.gfgcha');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveStaleUserRegistryEntries()
  else if CurStep = ssPostInstall then
  begin
    RestoreUserData();
    RemoveStaleEntry(HKCU);
  end;
end;

procedure DeinitializeSetup();
begin
  RestoreUserData();
end;
