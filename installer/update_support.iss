; =======================================================
; Silent updates started by the app's own updater
; Included by common.iss. The app (services\update_install.py) runs
; this installer with /VERYSILENT /updatepid=<its process id>
; /relaunch=0|1 as it exits; Setup waits for that process and the
; app's mutexes, records how this copy was installed, and starts the
; new version again when asked. Shared by gfgLock, gfgShield, and
; CC-Gen-Ultimate: keep the copies identical. Needs AppMutexes and
; MyAppExeName; UpdateRelaunchFlags may be defined first.
; =======================================================

#ifndef UpdateRelaunchFlags
  ; The app restarts as the user who started Setup, not elevated like an all-users Setup.
  #define UpdateRelaunchFlags "runasoriginaluser"
#endif

[INI]
; How this copy was installed; the updater picks the matching installer from each release.
Filename: "{app}\install.ini"; Section: "install"; Key: "kind"; String: "{code:UpdateInstallKind}"; Flags: uninsdeletesection

[UninstallDelete]
Type: files; Name: "{app}\install.ini"

[Run]
Filename: "{app}\{#MyAppExeName}"; Flags: nowait {#UpdateRelaunchFlags}; Check: ShouldRelaunch

[Code]
const
  UpdateWaitMs = 60000;
  UpdateSynchronize = $00100000;

function UpdateOpenProcess(DesiredAccess: Cardinal; InheritHandle: Boolean; ProcessId: Cardinal): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function UpdateWaitForSingleObject(Handle: THandle; Milliseconds: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function UpdateCloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

// The process id of the app that started this update, or 0 for an ordinary install.
function UpdatePid(): Cardinal;
begin
  Result := StrToIntDef(ExpandConstant('{param:updatepid|0}'), 0);
end;

function IsUpdateRun(): Boolean;
begin
  Result := UpdatePid() <> 0;
end;

// After "Restart now" the new version starts again; an update installed on close doesn't.
function ShouldRelaunch(): Boolean;
begin
  Result := IsUpdateRun() and (ExpandConstant('{param:relaunch|0}') = '1');
end;

function UpdateInstallKind(Param: String): String;
begin
  if IsAdminInstallMode() then
    Result := 'system'
  else
    Result := 'user';
end;

// An update starts while the app is still closing: wait until it has exited (its files are free)
// and no other copy holds the mutexes, so Setup's own AppMutex check passes. A copy that stays
// open (another user's, say) cancels the update; the app offers it again next time.
<event('InitializeSetup')>
function WaitForUpdatingApp(): Boolean;
var
  Process: THandle;
  Waited: Integer;
begin
  Result := True;
  if not IsUpdateRun() then
    Exit;
  Process := UpdateOpenProcess(UpdateSynchronize, False, UpdatePid());
  if Process <> 0 then
  begin
    UpdateWaitForSingleObject(Process, UpdateWaitMs);
    UpdateCloseHandle(Process);
  end;
  Waited := 0;
  while CheckForMutexes('{#AppMutexes}') and (Waited < UpdateWaitMs) do
  begin
    Sleep(250);
    Waited := Waited + 250;
  end;
  Result := not CheckForMutexes('{#AppMutexes}');
  if not Result then
    Log('The app is still open, so the update was not installed');
end;
