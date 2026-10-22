#Requires -Version 7.2
# common.ps1 - helpers shared by the build scripts and the release workflow: step output, the
# virtual environment, app metadata from pyproject.toml, the native build, and Inno Setup.
# Dot-source it: . "$PSScriptRoot\common.ps1" (bundle.ps1 loads it too)

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host ">> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Format-Elapsed([TimeSpan]$Span) {
    # .Minutes and .Seconds are sub-hour remainders (0-59), so the hours branch must come first,
    # or a run past 60 minutes drops its hours.
    if ($Span.TotalHours -ge 1)   { return "{0}h {1:D2}m {2:D2}s" -f [math]::Floor($Span.TotalHours), $Span.Minutes, $Span.Seconds }
    if ($Span.TotalMinutes -ge 1) { return "{0}m {1:D2}s" -f $Span.Minutes, $Span.Seconds }
    return "{0}s" -f [int]$Span.TotalSeconds
}

function Get-SizeMb([string]$Path) {
    return [math]::Round((Get-Item $Path).Length / 1MB, 1)
}

function Enable-Venv {
    <#
    .SYNOPSIS
        Activates the project's .venv (or venv), so python and pyinstaller come from it.
    #>
    Write-Step "Activating virtual environment"
    $root = Split-Path -Parent $PSScriptRoot
    foreach ($name in ".venv", "venv") {
        $activate = Join-Path $root "$name\Scripts\Activate.ps1"
        # Activating again first deactivates, which puts back the PATH saved at the first
        # activation and drops anything added since (the MSVC tools, for one).
        if ($env:VIRTUAL_ENV -and ((Resolve-Path $env:VIRTUAL_ENV -ErrorAction SilentlyContinue).Path -eq (Join-Path $root $name))) {
            Write-Host "   Already active: $name" -ForegroundColor DarkGray
            return
        }
        if (Test-Path $activate) {
            . $activate
            Write-Host "   Activated: $name" -ForegroundColor DarkGray
            return
        }
    }
    Write-Host "   No venv found - using the Python on PATH" -ForegroundColor Yellow
}

function Assert-BuildTools {
    <#
    .SYNOPSIS
        Fails unless python and pyinstaller (and Inno Setup with -Installer) are available, and
        prints their versions.
    #>
    param([switch]$Installer)
    Write-Step "Checking prerequisites"
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Fail "python not found in PATH"
    }
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        Fail "pyinstaller not found. Install the pinned build tools with: pip install -r requirements.txt"
    }
    Write-Host "   Python      : $(python --version)"      -ForegroundColor DarkGray
    Write-Host "   PyInstaller : $(pyinstaller --version)" -ForegroundColor DarkGray
    if ($Installer) {
        Write-Host "   ISCC        : $(Find-Iscc)" -ForegroundColor DarkGray
    }
}

function Get-AppMeta {
    <#
    .SYNOPSIS
        Returns the app metadata from pyproject.toml (Version, AppName, Publisher, Url, ExeName,
        WingetId) as a PSObject.
    #>
    $json = python (Join-Path $PSScriptRoot "read_meta.py")
    if ($LASTEXITCODE -ne 0) { Fail "Could not read the app metadata from pyproject.toml (exit $LASTEXITCODE)" }
    return $json | ConvertFrom-Json
}

function Invoke-NativeBuild {
    <#
    .SYNOPSIS
        Builds gfglock_native.pyd and gfglock_shell.dll with scripts\build_native.ps1.
    #>
    Write-Step "Building native C++ targets (gfglock_native.pyd + gfglock_shell.dll)"
    & (Join-Path $PSScriptRoot "build_native.ps1")
    if ($LASTEXITCODE -ne 0) { Fail "build_native.ps1 failed (exit $LASTEXITCODE). Check output above." }
}

function Find-Iscc {
    <#
    .SYNOPSIS
        Returns the path of Inno Setup 6's command-line compiler, or fails.
    #>
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { Fail "Inno Setup 6 not found. Download it from: https://jrsoftware.org/isinfo.php" }
    return $iscc
}

function Invoke-Iscc {
    <#
    .SYNOPSIS
        Compiles installer\gfglock_<kind>_installer.iss and returns the installer's path.
    .DESCRIPTION
        The app metadata is passed as /D definitions, which override the defaults in
        installer\common.iss. The installer lands in build\installer, or in -OutputDir.
    #>
    param(
        [Parameter(Mandatory)] [ValidateSet("User", "System")] [string]$Kind,
        [Parameter(Mandatory)] [psobject]$Meta,
        [string]$OutputDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "build\installer")
    )
    $kindName = $Kind.ToLowerInvariant()
    $iss = Join-Path (Split-Path -Parent $PSScriptRoot) "installer\gfglock_${kindName}_installer.iss"
    Write-Host "   Compiling : $iss" -ForegroundColor DarkGray
    & (Find-Iscc) `
        "/DMyAppName=$($Meta.AppName)" `
        "/DMyAppVersion=$($Meta.Version)" `
        "/DMyAppPublisher=$($Meta.Publisher)" `
        "/DMyAppURL=$($Meta.Url)" `
        "/DMyAppExeName=$($Meta.ExeName)" `
        "/O$OutputDir" `
        $iss | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed for '$iss' (exit $LASTEXITCODE)." }
    $installer = Join-Path $OutputDir "$($Meta.AppName)_$($Meta.Version)_${kindName}_installer.exe"
    if (-not (Test-Path $installer)) { Fail "Expected installer not found: $installer" }
    return $installer
}
