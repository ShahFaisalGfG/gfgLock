# bundle.ps1 - PyInstaller arguments and the bundle self-test, shared by every build script and
# the release workflow so local and CI builds package and verify exactly the same files.
# Dot-source it from the project root: . "$PSScriptRoot\bundle.ps1"

$SelfTestTimeoutSec = 180

function Get-PyInstallerArgs {
    <#
    .SYNOPSIS
        Returns the PyInstaller arguments for a onedir (installer) or onefile (portable) build.
    #>
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [ValidateSet("onedir", "onefile")] [string]$Mode,
        [Parameter(Mandatory)] [string]$DistPath
    )
    $root = Split-Path -Parent $PSScriptRoot
    return @(
        "--name",      $Name,
        "--windowed",
        "--$Mode",
        "--icon",      "$root\gfglock\assets\icons\gfgLock.ico",
        # gfglock_native.pyd lives in gfglock\core and is imported by name, so PyInstaller
        # needs the search path and an explicit hidden import to bundle it with its DLLs.
        "--paths",     "$root\gfglock\core",
        "--hidden-import", "gfglock_native",
        "--additional-hooks-dir", "$root\hooks",
        "--runtime-hook", "$root\hooks\pyi_rth_qt_dll_dirs.py",
        "--add-data",  "$root\gfglock\qml;gfglock\qml",
        "--add-data",  "$root\gfglock\assets;gfglock\assets",
        "--add-data",  "$root\gfglock\assets\icons\gfgLock.png;assets\icons",
        "--add-data",  "$root\gfglock\assets\icons\gfgLock.ico;assets\icons",
        "--add-data",  "$root\gfglock\assets\icons\gfgLock.png;icons",
        "--add-data",  "$root\screenshots;screenshots",
        "--add-data",  "$root\readme.html;.",
        "--distpath",  $DistPath,
        "--workpath",  "build\pyinstaller",
        "--specpath",  ".",
        "--noconfirm",
        "--clean",
        "$root\gfglock\__main__.py"
    )
}

function Test-Bundle {
    <#
    .SYNOPSIS
        Runs a built exe with --self-test, prints its report, and returns $true when every check passed.
    .DESCRIPTION
        The exe is a --windowed build with no console, so the report is read from a file. A build
        that hangs (for example on a startup error dialog) is stopped after $SelfTestTimeoutSec.
    #>
    param([Parameter(Mandatory)] [string]$ExePath)

    $report = Join-Path ([IO.Path]::GetTempPath()) "gfglock_self_test_$PID.txt"
    Remove-Item $report -Force -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $ExePath -ArgumentList "--self-test", "`"$report`"" -PassThru
    $null = $proc.Handle  # cache the handle so ExitCode is available after WaitForExit
    if (-not $proc.WaitForExit($SelfTestTimeoutSec * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "   Self-test did not finish within $SelfTestTimeoutSec s" -ForegroundColor Red
        return $false
    }
    if (Test-Path $report) {
        Get-Content $report | ForEach-Object { Write-Host "   $_" }
        Remove-Item $report -Force
    } else {
        Write-Host "   The self-test wrote no report (exit $($proc.ExitCode))" -ForegroundColor Red
    }
    return $proc.ExitCode -eq 0
}
