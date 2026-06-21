; =======================================================
; gfgLock Windows Installer
; Inno Setup Script
; Version: 3.0.0
; =======================================================
; gfgLock per-user installer (non-admin)
; Use this script to create a per-user installer that does not require elevated privileges

#ifndef MyAppName
  #define MyAppName "gfgLock"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "3.0.0"
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
#define SourceDir "..\dist\gfgLock"
#define IconsDir "..\gfglock\assets\icons"
#define ScreenshotsDir "..\screenshots"


[Setup]
AppId={{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install per-user (no admin privileges required)
PrivilegesRequired=lowest

; Install to per-user AppData (Roaming) for current user
DefaultDirName={userappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\build\installer
OutputBaseFilename={#MyAppName}_{#MyAppVersion}_user_installer
SetupIconFile={#IconsDir}\gfgLock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110,120

; Architectures
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.AssociateGfglockFiles=Associate .gfglock, .gfglck, .gfgcha files with gfgLock
english.FileAssociations=File associations:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "{cm:AssociateGfglockFiles}"; GroupDescription: "{cm:FileAssociations}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Shell extension DLL - restartreplace schedules replacement on reboot if Explorer holds a lock
Source: "{#SourceDir}\gfglock_shell.dll"; DestDir: "{app}"; Flags: ignoreversion restartreplace uninsrestartdelete
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#ScreenshotsDir}\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.png"; DestDir: "{app}\docs\icons"; Flags: ignoreversion recursesubdirs createallsubdirs


[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{userprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"; Tasks: desktopicon

[Registry]
; Per-user file associations under HKCU\Software\Classes
Root: HKCU; Subkey: "Software\Classes\.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglock"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

Root: HKCU; Subkey: "Software\Classes\.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglck"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (CFB)"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

Root: HKCU; Subkey: "Software\Classes\.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfgcha"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (ChaCha20)"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

; =============================================================================
; IExplorerCommand CLSID registrations - per-user (HKCU, no admin required)
; =============================================================================

; Encrypt - {{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}
Root: HKCU; Subkey: "Software\Classes\CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypt Shell Extension"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey

; Decrypt - {{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}
Root: HKCU; Subkey: "Software\Classes\CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Decrypt Shell Extension"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey

; =============================================================================
; Context menu entries per-user
; ExplorerCommandHandler  → Windows 11 first-level menu (all files at once)
; \command subkey         → Windows 10 fallback (single-file)
; =============================================================================
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: ""; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" encrypt ""%1"""; Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: ""; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" decrypt ""%1"""; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "https://github.com/ShahFaisalGfG/gfgLock"; Description: "View README on GitHub"; Flags: shellexec nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillGfgLock"
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\gfglock_shell.dll"""; Flags: runhidden; RunOnceId: "UnregShellExt"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function SystemInstallExists(): Boolean;
var S: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\gfgRoyal\gfgLock', 'InstallPath', S);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if SystemInstallExists() then
  begin
    MsgBox(
      'A system-wide installation of gfgLock is already present.' + #13#10#13#10 +
      'Please use the system installer to update it.',
      mbError, MB_OK);
    Result := False;
  end;
end;

procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This wizard will guide you through the installation of {MyAppName}.'#13#13 +
    'gfgLock is a secure file encryption tool with AES-256 cryptography and a modern GUI interface.'#13#13 +
    'It is recommended that you close all other applications before continuing.';
end;

procedure RemoveStaleSystemRegistryEntries();
begin
  // Clean up system-wide CLSID entries left by older system installs (best-effort).
  RegDeleteKeyIncludingSubkeys(HKCR, 'CLSID\{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}');
  RegDeleteKeyIncludingSubkeys(HKCR, 'CLSID\{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DllPath: String;
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    DllPath := ExpandConstant('{app}\gfglock_shell.dll');
    if FileExists(DllPath) then
      Exec(ExpandConstant('{sys}\regsvr32.exe'), '/s /u "' + DllPath + '"',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    RemoveStaleSystemRegistryEntries();
  end;
end;
