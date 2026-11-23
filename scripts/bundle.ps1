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

function New-VersionFile {
    <#
    .SYNOPSIS
        Writes an exe's version details for PyInstaller and returns the file's path.
    .DESCRIPTION
        Every exe the build makes carries the app's name as its product name and the version from
        pyproject.toml (read_meta.py writes them), which code signing requires; the description
        names the exe in Task Manager and in its Properties.
    #>
    param(
        [Parameter(Mandatory)] [string]$Exe,
        [Parameter(Mandatory)] [string]$Description
    )
    $root = Split-Path -Parent $PSScriptRoot
    $path = "$root\build\pyinstaller\$Exe.version.txt"
    python (Join-Path $PSScriptRoot "read_meta.py") --version-file $path --exe $Exe --description $Description
    if ($LASTEXITCODE -ne 0) { Fail "Could not write the version details of $Exe.exe (exit $LASTEXITCODE)" }
    return $path
}

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
        "--version-file", (New-VersionFile -Exe $Name -Description (Get-AppMeta).AppName),
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
        [Parameter(Mandatory)] [string]$DistPath,
        # Local staging builds only: the test update server (http://127.0.0.1:<port>) and the
        # public key (PEM file) its manifests are signed with. Release builds never pass these.
        [string]$UpdateFeed = "",
        [string]$UpdateKeyFile = ""
    )
    $root = Split-Path -Parent $PSScriptRoot
    $staging = "$root\gfglock\config\update_staging.py"
    if ($UpdateFeed) {
        if ($UpdateFeed -notmatch '^http://127\.0\.0\.1:\d{2,5}$') { Fail "-UpdateFeed must be http://127.0.0.1:<port>" }
        if (-not (Test-Path $UpdateKeyFile)) { Fail "-UpdateFeed needs -UpdateKeyFile with the test feed's public key" }
        $key = (Get-Content $UpdateKeyFile -Raw).Trim()
        Set-Content -Path $staging -Encoding utf8NoBOM -Value @"
# Written by scripts\bundle.ps1 -UpdateFeed for a local staging build; never commit or release it.
BASE_URL = "$UpdateFeed"
PUBLIC_KEYS = ("""$key
""",)
"@
        Write-Host "   Staging build: updates come from $UpdateFeed" -ForegroundColor Yellow
    } elseif (Test-Path $staging) {
        Fail "$staging is left from a staging build; delete it first."
    }
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
        if ($UpdateFeed) { Remove-Item $staging -Force -ErrorAction SilentlyContinue }
    }
    if ($exitCode -ne 0) { Fail "PyInstaller failed (exit $exitCode). Check output above." }
    if (-not (Test-Path $exe)) { Fail "Expected executable not found: $exe" }
    $sizeMb = [math]::Round((Get-ChildItem $output -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "   Built $output ($sizeMb MB)" -ForegroundColor DarkGray

    Write-Step "Verifying $Name can encrypt, decrypt, and load every QML module"
    if (-not (Test-Bundle $exe)) {
        Fail "Self-test failed for $exe - a module, DLL, or data file is missing from the build. See the report above."
    }
    if ($Mode -eq "onedir") {
        $null = New-ConsoleExe -BundleDir $output
    }
    return $exe
}

function New-ConsoleExe {
    <#
    .SYNOPSIS
        Builds the command line, bin\gfglock.exe, into a onedir bundle and checks that it runs.
    .DESCRIPTION
        A one-file console exe without Qt, carrying the native engine and the Agent Skill (which
        `gfglock skill install` copies out). It sits in a bin folder because Windows ignores case,
        so gfglock.exe can't sit next to gfgLock.exe; the installers can add that folder to PATH,
        and the portable .7z ships it inside the bundle. It finds the app's settings one folder up.
    #>
    param([Parameter(Mandatory)] [string]$BundleDir)
    $root = Split-Path -Parent $PSScriptRoot
    $name = "gfglock"
    $bin = Join-Path $BundleDir "bin"
    Write-Step "Building the command line ($bin\$name.exe)"
    $pyinstaller = (Get-Command pyinstaller -ErrorAction Stop).Source
    $pyArgs = @(
        "--name",      $name,
        "--console",
        "--onefile",
        "--icon",      "$root\gfglock\assets\icons\gfgLock.ico",
        "--version-file", (New-VersionFile -Exe $name -Description "$((Get-AppMeta).AppName) command line"),
        "--exclude-module", "PySide6",
        "--exclude-module", "shiboken6",
        "--paths",     $root,
        # The native engine and its pinned OpenSSL, as in the app (see Get-PyInstallerArgs).
        "--paths",     "$root\gfglock\core",
        "--hidden-import", "gfglock_native",
        "--add-binary", "$root\gfglock\core\libcrypto-3-x64.dll;.",
        "--add-data",  "$root\skills\gfglock;skills\gfglock",
        "--distpath",  $bin,
        "--workpath",  "$root\build\pyinstaller",
        "--specpath",  "$root\build\pyinstaller",
        "--noconfirm", "--clean",
        "$root\gfglock\cli.py"
    )
    $savedPath = $env:PATH
    $env:PATH = Get-IsolatedPath
    try {
        & $pyinstaller @pyArgs | Out-Host
        $exitCode = $LASTEXITCODE
    } finally {
        $env:PATH = $savedPath
    }
    if ($exitCode -ne 0) { Fail "PyInstaller failed for $name (exit $exitCode)." }
    $exe = Join-Path $bin "$name.exe"
    if (-not (Test-Path $exe)) { Fail "Console exe not found: $exe" }
    Write-Host "   Built $exe ($(Get-SizeMb $exe) MB)" -ForegroundColor DarkGray
    $version = & $exe --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^gfglock \d+\.\d+\.\d+$') { Fail "$name.exe --version failed: $version" }
    $skill = & $exe skill show --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $skill.files.'SKILL.md') { Fail "$name.exe doesn't carry its skill." }
    Write-Host "   $version, with its skill" -ForegroundColor DarkGray
    return $exe
}

function New-PortableArchive {
    <#
    .SYNOPSIS
        Packs a onedir bundle as the portable .7z, with its licences and the portable marker.
    .DESCRIPTION
        The marker file next to gfgLock.exe makes that copy keep its settings and logs in a
        "gfgLock data" folder beside itself. The Explorer shell DLL is not included: it only
        works once an installer registers it. The archive holds the bundle's contents at its top
        level, beside the marker and the licences.
    #>
    param(
        [Parameter(Mandatory)] [string]$BundleDir,
        [Parameter(Mandatory)] [string]$ArchivePath
    )
    $root = Split-Path -Parent $PSScriptRoot
    if (-not (Test-Path $BundleDir -PathType Container)) { Fail "Bundle folder not found: $BundleDir" }
    # 7-Zip stores a relative path's folders ("dist\gfgLock\...") but drops an absolute path's, so
    # the bundle is passed as a full path to keep gfgLock.exe at the top, next to the marker.
    $BundleDir = (Resolve-Path $BundleDir).Path
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
