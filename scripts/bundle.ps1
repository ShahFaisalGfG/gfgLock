#Requires -Version 7.2
# bundle.ps1 - PyInstaller builds, the bundle self-test, and the portable archive, shared by every
# build script and the release workflow so local and CI builds package and verify the same files.
# Dot-source it: . "$PSScriptRoot\bundle.ps1" (it loads common.ps1 too)

. "$PSScriptRoot\common.ps1"

$SelfTestTimeoutSec = 180
# DLL names of OpenSSL 3 builds that tools such as Git for Windows put on PATH. gfglock_native
# loads the pinned vcpkg build of the same name from its own folder.
$OpenSslDllNames = @("libcrypto-3-x64.dll", "libssl-3-x64.dll")
# Read by gfglock\utils\paths.py: next to gfgLock.exe it makes a one-folder build portable.
$PortableMarkerName = "gfgLock-portable.txt"
$PortableMarkerText = @"
Settings and logs for this copy of gfgLock stay in the "gfgLock data" folder next to gfgLock.exe.
Delete this file to keep them in %APPDATA%\gfgLock instead.
"@

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
    $pyArgs = @(
        "--name",      $Name,
        "--windowed",
        "--$Mode",
        "--icon",      "$root\gfglock\assets\icons\gfgLock.ico",
        # gfglock_native.pyd lives in gfglock\core and is imported by name, so PyInstaller
        # needs the search path and an explicit hidden import to bundle it with its DLLs.
        "--paths",     "$root\gfglock\core",
        "--hidden-import", "gfglock_native",
        # The pinned OpenSSL goes next to the module, the folder Windows loads it from.
        "--add-binary", "$root\gfglock\core\libcrypto-3-x64.dll;.",
        # Project hooks trim Qt to what the app uses (see each file in hooks\).
        "--additional-hooks-dir", "$root\hooks",
        "--runtime-hook", "$root\hooks\pyi_rth_qt_dll_dirs.py",
        "--add-data",  "$root\gfglock\qml;gfglock\qml",
        "--add-data",  "$root\gfglock\assets;gfglock\assets",
        "--distpath",  $DistPath,
        "--workpath",  "$root\build\pyinstaller",
        "--specpath",  "$root\build\pyinstaller",
        "--noconfirm",
        "--clean"
    )
    if ($Mode -eq "onefile") {
        # A one-file exe carries the licence texts inside; the installers and the portable .7z
        # ship them as files next to the app instead.
        $pyArgs += "--add-data", "$root\licenses;licenses"
    }
    return $pyArgs + "$root\gfglock\__main__.py"
}

function Get-IsolatedPath {
    <#
    .SYNOPSIS
        Returns PATH without the folders that hold another OpenSSL 3 build.
    .DESCRIPTION
        PyInstaller resolves DLL names through PATH, so a libcrypto-3-x64.dll found there (Git for
        Windows ships one) can be bundled in place of the pinned build gfglock_native needs. The
        venv and Windows folders always stay.
    #>
    $kept = @($env:VIRTUAL_ENV, $env:SystemRoot) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd("\") + "\" }
    $entries = foreach ($entry in $env:PATH -split [IO.Path]::PathSeparator) {
        if (-not $entry) { continue }
        $protected = $kept | Where-Object { ($entry.TrimEnd("\") + "\").StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }
        $openSsl = $OpenSslDllNames | Where-Object { [IO.File]::Exists([IO.Path]::Combine($entry, $_)) }
        if ($openSsl -and -not $protected) {
            Write-Host "   Hidden from PyInstaller (holds $($openSsl -join ', ')): $entry" -ForegroundColor DarkGray
            continue
        }
        $entry
    }
    return $entries -join [IO.Path]::PathSeparator
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

function New-AppBundle {
    <#
    .SYNOPSIS
        Builds the app with PyInstaller, runs the result's --self-test, and returns the exe path.
    .DESCRIPTION
        onedir builds <DistPath>\<Name>\<Name>.exe (used by the installers and the portable .7z);
        onefile builds <DistPath>\<Name>.exe. Earlier output of the same build is removed first.
    #>
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [ValidateSet("onedir", "onefile")] [string]$Mode,
        [Parameter(Mandatory)] [string]$DistPath
    )
    $root = Split-Path -Parent $PSScriptRoot
    $output = if ($Mode -eq "onedir") { Join-Path $DistPath $Name } else { Join-Path $DistPath "$Name.exe" }
    $exe = if ($Mode -eq "onedir") { Join-Path $output "$Name.exe" } else { $output }
    foreach ($path in @($output, "$root\build\pyinstaller\$Name")) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
            Write-Host "   Removed $path" -ForegroundColor DarkGray
        }
    }

    Write-Step "Running PyInstaller for $Name ($Mode, this may take several minutes)"
    $pyinstaller = (Get-Command pyinstaller -ErrorAction Stop).Source
    $pyArgs = Get-PyInstallerArgs -Name $Name -Mode $Mode -DistPath $DistPath
    $savedPath = $env:PATH
    $env:PATH = Get-IsolatedPath
    try {
        & $pyinstaller @pyArgs | Out-Host
        $exitCode = $LASTEXITCODE
    } finally {
        $env:PATH = $savedPath
    }
    if ($exitCode -ne 0) { Fail "PyInstaller failed (exit $exitCode). Check output above." }
    if (-not (Test-Path $exe)) { Fail "Expected executable not found: $exe" }
    $sizeMb = [math]::Round((Get-ChildItem $output -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "   Built $output ($sizeMb MB)" -ForegroundColor DarkGray

    Write-Step "Verifying $Name can encrypt, decrypt, and load every QML module"
    if (-not (Test-Bundle $exe)) {
        Fail "Self-test failed for $exe - a module, DLL, or data file is missing from the build. See the report above."
    }
    return $exe
}

function New-PortableArchive {
    <#
    .SYNOPSIS
        Packs a onedir bundle as the portable .7z, with its licences and the portable marker.
    .DESCRIPTION
        The marker file next to gfgLock.exe makes that copy keep its settings and logs in a
        "gfgLock data" folder beside itself. The Explorer shell DLL is not included: it only
        works once an installer registers it.
    #>
    param(
        [Parameter(Mandatory)] [string]$BundleDir,
        [Parameter(Mandatory)] [string]$ArchivePath
    )
    $root = Split-Path -Parent $PSScriptRoot
    $command = Get-Command 7z -ErrorAction SilentlyContinue
    $sevenZip = if ($command) { $command.Source } else { "$env:ProgramFiles\7-Zip\7z.exe" }
    if (-not (Test-Path $sevenZip)) { Fail "7-Zip not found (looked for 7z on PATH and $sevenZip)" }

    $extras = Join-Path $root "build\portable-extras"
    if (Test-Path $extras) { Remove-Item $extras -Recurse -Force }
    New-Item -ItemType Directory -Path $extras | Out-Null
    Copy-Item "$root\LICENSE" "$extras\LICENSE.txt"
    Copy-Item "$root\THIRD_PARTY_NOTICES.md" $extras
    Copy-Item "$root\licenses" "$extras\licenses" -Recurse
    Set-Content -Path "$extras\$PortableMarkerName" -Value $PortableMarkerText

    if (Test-Path $ArchivePath) { Remove-Item $ArchivePath -Force }
    & $sevenZip a -t7z -mx=9 $ArchivePath "$BundleDir\*" "$extras\*" | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "7-Zip failed (exit $LASTEXITCODE) for $ArchivePath" }
    Write-Host "   Packed $ArchivePath ($(Get-SizeMb $ArchivePath) MB)" -ForegroundColor DarkGray
}
