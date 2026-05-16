; =======================================================
; gfgLock Windows Silent Installer
; Inno Setup Script
; Version: 2.7.5
; =======================================================
; Per-user, no-prompt silent installer.
; Double-click to install — no wizard pages, no questions.
; All defaults applied automatically:
;   - installs to %APPDATA%\gfgLock
;   - creates desktop shortcut
;   - registers file associations (.gfglock, .gfglck, .gfgcha)
;   - registers Explorer context menu entries

#define MyAppName "gfgLock"
#define MyAppVersion "2.7.5"
#define MyAppPublisher "gfgRoyal"
#define MyAppURL "https://shahfaisalgfg.github.io/shahfaisal/"
#define MyAppExeName "gfgLock.exe"
#define SourceDir "..\dist\gfgLock"
#define IconsDir "..\gfglock\assets\icons"
#define ScreenshotsDir "..\screenshots"


[Setup]
AppId={{C8D4E2A1-9F5B-4C3D-A7E8-987654321DEF}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Per-user install — no admin required
PrivilegesRequired=lowest

DefaultDirName={userappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\build\installer
OutputBaseFilename={#MyAppName}_{#MyAppVersion}_silent_user_installer
SetupIconFile={#IconsDir}\gfgLock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Architectures
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; Suppress all wizard pages
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"


[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\README.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#ScreenshotsDir}\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.png"; DestDir: "{app}\docs\icons"; Flags: ignoreversion recursesubdirs createallsubdirs


[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{userprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userprograms}\Documentation"; Filename: "{app}\docs\README.html"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"


[Registry]
; File associations — always registered (no task prompt)
Root: HKCU; Subkey: "Software\Classes\.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglock"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglock\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglck"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (CFB)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfglck\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKCU; Subkey: "Software\Classes\.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfgcha"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (ChaCha20)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\gfgLock.gfgcha\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; Context menu — always registered
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: ""; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" encrypt ""%1"""; Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: ""; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" decrypt ""%1"""; Flags: uninsdeletekey


[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent


[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\temp"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"
Type: files; Name: "{userappdata}\{#MyAppName}\settings.json"
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\logs"


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

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := True;
end;
