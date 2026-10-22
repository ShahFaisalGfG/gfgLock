; =======================================================
; gfgLock Windows installers - the parts both share
; Included by gfglock_system_installer.iss (all users) and
; gfglock_user_installer.iss (current user). The build scripts
; pass the app metadata from pyproject.toml as /D definitions;
; the defaults below apply when a script is compiled by hand.
; =======================================================

#ifndef MyAppName
  #define MyAppName "gfgLock"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "3.2.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "gfgRoyal"
#endif
#ifndef MyAppURL
  #define MyAppURL "https://shahfaisalgfg.github.io/shahfaisal/"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "gfgLock.exe"
#endif

; Written with Inno Setup's "{{" escape for an opening brace, as section values need it; [Code]
; reads them through ExpandConstant. The two Explorer command CLSIDs must match
; native\src\shell_extension.cpp.
#define AppGuid "{{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}"
#define EncryptClsid "{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}"
#define DecryptClsid "{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}"

; Held by gfgLock while it runs (gfglock\utils\single_instance.py APP_MUTEXES)
#define AppMutexes "gfgLockAppMutex,Global\gfgLockAppMutex"

#define SourceDir "..\dist\" + MyAppName
#define ShellDll "..\build\shell\gfglock_shell.dll"
#define IconsDir "..\gfglock\assets\icons"
#define ScreenshotsDir "..\screenshots"
#define RepoUrl "https://github.com/ShahFaisalGfG/gfgLock"

[Setup]
AppId={#AppGuid}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; One gfgLock folder in the Start menu, without a page to rename it
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\build\installer
SetupIconFile={#IconsDir}\gfgLock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110,120
; Explorer refreshes file icons when the file associations were written
ChangesAssociations=WizardIsTaskSelected('associate')

; The shell extension is an x64 DLL, which Explorer on Arm64 Windows can't load. PySide6 6.11
; needs Windows 10 version 1809 or later.
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763

; gfgLock holds both mutexes while it runs, so Setup and Uninstall ask the user to close it
; rather than ending every running copy, and any run in progress, in all sessions.
AppMutex={#AppMutexes}
; Each install writes a fresh uninstall log. Appending would keep the [UninstallRun] and
; [UninstallDelete] entries of 3.1.0 and older (ending gfgLock by force, deleting the whole
; install folder) in every later uninstaller. [InstallDelete] clears the old bundle first, so the
; new log covers every program file.
UninstallLogMode=overwrite
; Only a running gfgLock.exe can hold a file Setup replaces. Explorer and file dialogs keep the
; shell DLL loaded; it is moved aside (MoveShellDllAside), so Setup never offers to close them.
CloseApplicationsFilter=*.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.AssociateGfglockFiles=Associate .gfglock, .gfglck, .gfgcha files with gfgLock
english.FileAssociations=File associations:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "{cm:AssociateGfglockFiles}"; GroupDescription: "{cm:FileAssociations}"

[Files]
; The app bundle from scripts\bundle.ps1. The shell DLL comes from build\shell (each installer
; lists it with its own flags), never from an older bundle.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "gfglock_shell.dll"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
; Documentation and the licence texts of every bundled component
Source: "..\readme.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\docs"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\licenses\*"; DestDir: "{app}\docs\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ScreenshotsDir}\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\Square150x150Logo.scale-100.png"; DestDir: "{app}\docs\icons"; Flags: ignoreversion

[InstallDelete]
; Remove the previous version's bundled runtime before copying the new one. Files a newer
; build no longer ships (old package metadata, dropped libraries) would otherwise stay behind
; and can break imports at startup. Only bundled program files live in _internal; settings
; and logs are stored in %APPDATA% and are kept.
Type: filesandordirs; Name: "{app}\_internal"
; The docs folder is replaced the same way, so old screenshots and files no longer shipped go.
Type: filesandordirs; Name: "{app}\docs"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"; Tasks: desktopicon

[Registry]
; HKA is HKLM for the all-users installer and HKCU for the per-user one, so Software\Classes
; registers the entries for all users or for the current user.

; File associations (only with the "associate" task)
Root: HKA; Subkey: "Software\Classes\.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglock"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglock\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglock\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglck"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (CFB)"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglck\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfglck\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfgcha"; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (ChaCha20)"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfgcha\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\gfgLock.gfgcha\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

; IExplorerCommand classes in gfglock_shell.dll (the Windows 11 menu, all selected items at once)
Root: HKA; Subkey: "Software\Classes\CLSID\{#EncryptClsid}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypt Shell Extension"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{#EncryptClsid}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{#EncryptClsid}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{#DecryptClsid}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Decrypt Shell Extension"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{#DecryptClsid}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CLSID\{#DecryptClsid}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey

; Context menu entries: ExplorerCommandHandler drives the Windows 11 menu; the command subkey is
; the fallback that opens one item at a time. Up to 3.1.0 the entries were pinned to the top of
; the menu with a "Position" value, which an upgrade deletes.
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: ""; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: none; ValueName: "Position"; Flags: deletevalue
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{#EncryptClsid}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" encrypt ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: ""; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: none; ValueName: "Position"; Flags: deletevalue
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{#DecryptClsid}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" decrypt ""%1"""; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "{#RepoUrl}"; Description: "View README on GitHub"; Flags: shellexec nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Shell DLLs moved aside by an upgrade (MoveShellDllAside) once nothing holds them any more
Type: files; Name: "{app}\gfglock_shell.*.old"

[Code]
const
  UninstallKeys = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\';

// The uninstall entry of this AppId.
function CurrentUninstallKey(): String;
begin
  Result := UninstallKeys + ExpandConstant('{#AppGuid}') + '_is1';
end;

// The entry 2.6.9 to 3.0.0 wrote. Their AppId ended in "}}", which Inno Setup keeps as a literal
// brace, so an upgrade from them left a second entry. Their uninstallers delete the whole install
// folder and the registry keys this version shares, so one never runs on the folder being
// installed; only the all-users installer runs one, to remove a separate per-user copy the user
// agreed to remove, after gfgLock was closed and the user's settings and logs were set aside.
function StaleUninstallKey(): String;
begin
  Result := UninstallKeys + ExpandConstant('{#AppGuid}') + '}_is1';
end;

// True when the stale entry under RootKey still points at an installed copy of gfgLock.
function StaleInstallExists(const RootKey: Integer): Boolean;
var
  Location: String;
begin
  Result := False;
  if RegQueryStringValue(RootKey, StaleUninstallKey(), 'InstallLocation', Location) then
    Result := FileExists(AddBackslash(Location) + '{#MyAppExeName}');
end;

// True when gfgLock is installed under RootKey: HKLM for all users, HKCU for the current user.
function InstallExists(const RootKey: Integer): Boolean;
begin
  Result := RegKeyExists(RootKey, CurrentUninstallKey()) or StaleInstallExists(RootKey);
end;

// Deletes the stale entry under RootKey and the uninstaller files it names, without running them.
// A copy still installed in another folder (an older version put somewhere else) keeps its entry,
// so it can still be uninstalled from Settings.
procedure RemoveStaleEntry(const RootKey: Integer);
var
  UninstExe, Location: String;
begin
  if not RegKeyExists(RootKey, StaleUninstallKey()) then
    Exit;
  if StaleInstallExists(RootKey)
    and RegQueryStringValue(RootKey, StaleUninstallKey(), 'InstallLocation', Location)
    and (CompareText(RemoveBackslash(Location), RemoveBackslash(ExpandConstant('{app}'))) <> 0) then
  begin
    Log('Left the uninstall entry of the copy in ' + Location + ' in place');
    Exit;
  end;
  if RegQueryStringValue(RootKey, StaleUninstallKey(), 'UninstallString', UninstExe) then
  begin
    UninstExe := RemoveQuotes(UninstExe);
    if CompareText(UninstExe, ExpandConstant('{uninstallexe}')) <> 0 then
    begin
      DeleteFile(UninstExe);
      DeleteFile(ChangeFileExt(UninstExe, '.dat'));
      DeleteFile(ChangeFileExt(UninstExe, '.msg'));
    end;
  end;
  if RegDeleteKeyIncludingSubkeys(RootKey, StaleUninstallKey()) then
    Log('Removed the stale uninstall entry ' + StaleUninstallKey())
  else
    Log('Could not remove the stale uninstall entry ' + StaleUninstallKey());
end;

// Explorer and file dialogs keep gfglock_shell.dll loaded, so it can't be overwritten, but a
// loaded DLL can be renamed. The old copy moves aside as gfglock_shell.<n>.old and the new one is
// copied as usual; .old files nothing holds any more are deleted here and at uninstall.
procedure MoveShellDllAside();
var
  Dir, OldName: String;
  FindRec: TFindRec;
  N: Integer;
begin
  Dir := ExpandConstant('{app}\');
  if FindFirst(Dir + 'gfglock_shell.*.old', FindRec) then
  try
    repeat
      DeleteFile(Dir + FindRec.Name);
    until not FindNext(FindRec);
  finally
    FindClose(FindRec);
  end;
  if not FileExists(Dir + 'gfglock_shell.dll') then
    Exit;
  N := 0;
  repeat
    N := N + 1;
    OldName := Dir + 'gfglock_shell.' + IntToStr(N) + '.old';
  until not FileExists(OldName);
  if RenameFile(Dir + 'gfglock_shell.dll', OldName) then
    Log('Moved the previous shell extension aside: ' + OldName)
  else
    Log('Could not move the previous shell extension aside');
end;

<event('CurStepChanged')>
procedure SharedCurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    MoveShellDllAside()
  else if CurStep = ssPostInstall then
    RemoveStaleEntry(HKA);
end;
