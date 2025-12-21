; =======================================================
; gfgLock Windows Installer
; Inno Setup Script
; Version: 2.6.9
; =======================================================
; gfgLock per-user installer (non-admin)
; Use this script to create a per-user installer that does not require elevated privileges

#define MyAppName "gfgLock"
#define MyAppVersion "2.6.9"
#define MyAppPublisher "gfgRoyal"
#define MyAppURL "https://shahfaisalgfg.github.io/shahfaisal/"
#define MyAppExeName "gfgLock.exe"
#define SourceDir "..\src\dist\gfgLock"
#define IconsDir "..\src\assets\icons"
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
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\README.html"; DestDir: "{app}\docs"; Flags: ignoreversion isreadme
Source: "..\requirements.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#ScreenshotsDir}\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.png"; DestDir: "{app}\docs\icons"; Flags: ignoreversion recursesubdirs createallsubdirs


[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{userprograms}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{userprograms}\Documentation"; Filename: "{app}\docs\README.html"
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

; Context menu entries per-user
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

; Remove per-user settings and logs for the user running the uninstaller
; Note: this deletes the current user's AppData entries only (not other users).
Type: files; Name: "{userappdata}\{#MyAppName}\settings.json"
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\logs"

[Code]
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This wizard will guide you through the installation of {MyAppName}.'#13#13 +
    'gfgLock is a secure file encryption tool with AES-256 cryptography and a modern GUI interface.'#13#13 +
    'It is recommended that you close all other applications before continuing.';
end;
