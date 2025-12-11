; =======================================================
; gfgLock Windows Installer
; Inno Setup Script
; Version: 1.0.0
; =======================================================

#define MyAppName "gfgLock"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "gfgRoyal"
#define MyAppURL "https://shahfaisalgfg.github.io/shahfaisal/"
#define MyAppExeName "gfgLock_gui.exe"
#define SourceDir "..\src\dist\gfgLock_gui"
#define IconsDir "..\src\assets\icons"

[Setup]
; App identification
AppId={{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation settings
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\build\installer
OutputBaseFilename={#MyAppName}_Setup_{#MyAppVersion}
SetupIconFile={#IconsDir}\gfgLock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110,120

; Privileges
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Architectures
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.AssociateGfglockFiles=Associate .gfglock files with gfgLock
english.FileAssociations=File associations:

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.01
Name: "associate"; Description: "{cm:AssociateGfglockFiles}"; GroupDescription: "{cm:FileAssociations}"; Flags: unchecked

[Files]
; Main application files (compiled executable and dependencies)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Icon for the application
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
; Documentation
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion isreadme
Source: "..\requirements.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
; Optional: Include source code for transparency
Source: "..\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs; Attribs: hidden

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\Documentation"; Filename: "{app}\docs\README.md"

; Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"; Tasks: desktopicon

; Quick Launch (legacy)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"; Tasks: quicklaunchicon

[Registry]
; File association for .gfglock files
Root: HKCR; Subkey: ".gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglock"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File"; Flags: uninsdeletekey; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate


; Context menu for all filesystem objects (files + folders, any count)
Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockEncrypt"; ValueType: string; ValueName: ""; ValueData: "Encrypt"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockEncrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\\icons\\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockEncrypt\\command"; ValueType: string; ValueName: ""; ValueData: """{app}\\{#MyAppExeName}"" encrypt %*"; Flags: uninsdeletekey

Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockDecrypt"; ValueType: string; ValueName: ""; ValueData: "Decrypt"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockDecrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\\icons\\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\\shell\\gfgLockDecrypt\\command"; ValueType: string; ValueName: ""; ValueData: """{app}\\{#MyAppExeName}"" decrypt %*"; Flags: uninsdeletekey







; Application path info (optional)
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "ExePath"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\temp"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"

[Code]
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This wizard will guide you through the installation of {MyAppName}.'#13#13 +
    'gfgLock is a secure file encryption tool with AES-256 cryptography and a modern GUI interface.'#13#13 +
    'It is recommended that you close all other applications before continuing.';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox('Are you sure you want to completely remove {#MyAppName} and all of its components?',
      mbConfirmation, MB_YESNO) = IDNO then
      Abort;
  end;
end;