; =======================================================
; gfgLock Windows Installer
; Inno Setup Script
; Version: 3.0.0
; =======================================================

#define MyAppName "gfgLock"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "gfgRoyal"
#define MyAppURL "https://shahfaisalgfg.github.io/shahfaisal/"
#define MyAppExeName "gfgLock.exe"
#define SourceDir "..\dist\gfgLock"
#define IconsDir "..\gfglock\assets\icons"
#define ScreenshotsDir "..\screenshots"

[Setup]
; App identification
AppId={{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}}
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
OutputBaseFilename={#MyAppName}_{#MyAppVersion}_system_installer
SetupIconFile={#IconsDir}\gfgLock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110,120

; Privileges — require admin (force system-wide install)
PrivilegesRequired=admin

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
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "{cm:AssociateGfglockFiles}"; GroupDescription: "{cm:FileAssociations}"

[Files]
; Main application files (compiled executable and dependencies)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Icon for the application
Source: "{#IconsDir}\gfgLock.ico"; DestDir: "{app}\icons"; Flags: ignoreversion
; Documentation
Source: "..\README.html"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#ScreenshotsDir}\*"; DestDir: "{app}\docs\screenshots"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#IconsDir}\gfgLock.png"; DestDir: "{app}\docs\icons"; Flags: ignoreversion recursesubdirs createallsubdirs



[Icons]
; Start Menu
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\Documentation"; Filename: "{app}\docs\README.html"

; Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icons\gfgLock.ico"; Tasks: desktopicon

; Quick Launch (legacy) - skipped for system installer to avoid per-user area usage
; Historically Quick Launch shortcuts were created under the current user's
; AppData. Creating per-user items from an elevated/system installer can be
; unsafe and triggers Inno Setup warnings, so we do not create Quick Launch
; entries here. The per-user installer (`gfglock_installer_non_admin.iss`)
; can create a Quick Launch shortcut for the installing user if desired.

[Registry]
; =============================================================================
; File association for .gfglock files (only if user chooses "Associate" task)
; =============================================================================
Root: HKCR; Subkey: ".gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglock"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File"; Flags: uninsdeletekey; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglock\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKCR; Subkey: ".gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfglck"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglck"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (CFB)"; Flags: uninsdeletekey; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglck\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfglck\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKCR; Subkey: ".gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock.gfgcha"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfgcha"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypted File (ChaCha20)"; Flags: uninsdeletekey; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfgcha\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKCR; Subkey: "gfgLock.gfgcha\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate


; =============================================================================
; IExplorerCommand CLSID registrations (Windows 11 first-level context menu)
; =============================================================================

; Encrypt — {{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}
Root: HKCR; Subkey: "CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Encrypt Shell Extension"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CLSID\{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey

; Decrypt — {{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}
Root: HKCR; Subkey: "CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}"; ValueType: string; ValueName: ""; ValueData: "gfgLock Decrypt Shell Extension"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\gfglock_shell.dll"; Flags: uninsdeletekey
Root: HKCR; Subkey: "CLSID\{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Flags: uninsdeletekey

; =============================================================================
; Context menu: Encrypt with gfgLock
; ExplorerCommandHandler  → Windows 11 first-level menu (all files at once)
; \command subkey         → Windows 10 fallback (single-file)
; =============================================================================
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: ""; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Encrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockEncrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" encrypt ""%1"""; Flags: uninsdeletekey

; =============================================================================
; Context menu: Decrypt with gfgLock
; =============================================================================
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: ""; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Decrypt with gfgLock"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\icons\gfgLock.ico"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "Position"; ValueData: "Top"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt"; ValueType: string; ValueName: "ExplorerCommandHandler"; ValueData: "{{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}"; Flags: uninsdeletekey
Root: HKCR; Subkey: "AllFileSystemObjects\shell\gfgLockDecrypt\command"; ValueType: expandsz; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" decrypt ""%1"""; Flags: uninsdeletekey


; =============================================================================
; Optional: Store installation info (useful for future updates/uninstallers)
; =============================================================================
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "ExePath"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey


[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\docs\README.html"; Description: "View README"; Flags: shellexec nowait postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillGfgLock"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\temp"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"

[Code]
function UserInstallExists(): Boolean;
var S: String;
begin
  Result :=
    RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}_is1', 'InstallLocation', S) or
    RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{C8D4E2A1-9F5B-4C3D-A7E8-987654321DEF}_is1', 'InstallLocation', S);
end;

function GetUserUninstallStr(out UninstStr: String): Boolean;
begin
  Result :=
    RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
      '{B9A3F7D2-8C4E-4A5B-93C6-123456789ABC}_is1', 'UninstallString', UninstStr);
  if not Result then
    Result :=
      RegQueryStringValue(HKCU,
        'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
        '{C8D4E2A1-9F5B-4C3D-A7E8-987654321DEF}_is1', 'UninstallString', UninstStr);
end;

function InitializeSetup(): Boolean;
var
  UninstStr: String;
  ResultCode: Integer;
begin
  Result := True;
  if UserInstallExists() then
  begin
    if MsgBox(
      'A per-user installation of gfgLock was found.' + #13#10#13#10 +
      'Click Yes to remove it and continue with the system-wide installation.' + #13#10 +
      'Click No to cancel — then use the per-user installer to update instead.',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
    if GetUserUninstallStr(UninstStr) then
      Exec(RemoveQuotes(UninstStr), '/VERYSILENT /NORESTART', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'This wizard will guide you through the installation of {MyAppName}.'#13#13 +
    'gfgLock is a secure file encryption tool with AES-256 cryptography and a modern GUI interface.'#13#13 +
    'It is recommended that you close all other applications before continuing.';
end;

procedure RemoveStaleUserRegistryEntries();
begin
  // Clean up per-user CLSID and context-menu entries left by older per-user installs.
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\CLSID\{E1D4C8A3-2B57-4F6E-9D3A-F5C7821094BE}');
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\CLSID\{F2E5D9B4-3C68-4A7F-BE4B-06D8932105CF}');
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\AllFileSystemObjects\shell\gfgLockEncrypt');
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\AllFileSystemObjects\shell\gfgLockDecrypt');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveStaleUserRegistryEntries();
end;

// procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
// begin
  // if CurUninstallStep = usUninstall then
  // begin
    // if MsgBox('Are you sure you want to completely remove {#MyAppName} and all of its components?',
      // mbConfirmation, MB_YESNO) = IDNO then
      // Abort;
  // end;
// end;

// Attempt to remove per-user AppData (Roaming) data for all users during uninstall.
// This is best-effort: failures are ignored so uninstall proceeds silently.
procedure DeletePerUserDataForAllUsers();
var
  FindRec: TFindRec;
  UsersPath, ProfilePath: String;
begin
  UsersPath := 'C:\Users';
  if FindFirst(UsersPath + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          // Skip common/system profile folders
          if (CompareText(FindRec.Name, 'All Users') = 0) or
             (CompareText(FindRec.Name, 'Default') = 0) or
             (CompareText(FindRec.Name, 'Default User') = 0) or
             (CompareText(FindRec.Name, 'Public') = 0) then
            continue;

          ProfilePath := UsersPath + '\' + FindRec.Name + '\AppData\Roaming\{#MyAppName}';
          try
            if DirExists(ProfilePath) then
            begin
              DelTree(ProfilePath, True, True, True);
            end;
          except
            // ignore errors and continue
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    try
      DeletePerUserDataForAllUsers();
    except
      // ignore any unexpected errors
    end;
  end;
end;