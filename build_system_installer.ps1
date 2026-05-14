<#
.SYNOPSIS
    Build the gfgLock system-wide Windows installer.
.DESCRIPTION
    Step 1 — PyInstaller  : bundles the app into dist\gfgLock\
    Step 2 — Inno Setup   : compiles the system-wide installer into build\installer\
.NOTES
    Requirements: Python venv with pyinstaller>=6.17, Inno Setup 6
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ─────────────────────────────────────────────────────────────

$AppName   = "gfgLock"
$Version   = "2.7.5"
$Entry     = "gfglock\__main__.py"
$DistDir   = "dist\$AppName"
$IssFile   = "installer\gfglock_system_installer.iss"
$OutputExe = "build\installer\${AppName}_${Version}_system_installer.exe"
$IsccPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

function Write-Step([string]$Msg) {
    Write-Host ""
    Write-Host ">> $Msg" -ForegroundColor Cyan
}

function Fail([string]$Msg) {
    Write-Host ""
    Write-Host "ERROR: $Msg" -ForegroundColor Red
    exit 1
}

function Format-Elapsed([TimeSpan]$ts) {
    if ($ts.TotalMinutes -ge 1) { return "{0}m {1:D2}s" -f [int]$ts.Minutes, $ts.Seconds }
    return "{0}s" -f [int]$ts.TotalSeconds
}

# ── Working directory ─────────────────────────────────────────────────────────

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BuildStart = Get-Date
Set-Location $ScriptDir

# ── Virtual environment ───────────────────────────────────────────────────────

Write-Step "Activating virtual environment"

$VenvScripts = @(".venv\Scripts\Activate.ps1", "venv\Scripts\Activate.ps1")
$VenvFound   = $false
foreach ($v in $VenvScripts) {
    if (Test-Path $v) {
        . $v
        $VenvFound = $true
        Write-Host "   Activated: $v" -ForegroundColor DarkGray
        break
    }
}
if (-not $VenvFound) {
    Write-Host "   No venv found — using system Python" -ForegroundColor Yellow
}

# ── Prerequisites ─────────────────────────────────────────────────────────────

Write-Step "Checking prerequisites"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fail "python not found in PATH"
}
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Fail "pyinstaller not found. Install it with: pip install 'pyinstaller>=6.17'"
}

$Iscc = $null
foreach ($p in $IsccPaths) {
    if (Test-Path $p) { $Iscc = $p; break }
}
if (-not $Iscc) {
    Fail "Inno Setup 6 not found. Download from: https://jrsoftware.org/isinfo.php"
}

Write-Host "   Python      : $(python --version)"      -ForegroundColor DarkGray
Write-Host "   PyInstaller : $(pyinstaller --version)" -ForegroundColor DarkGray
Write-Host "   ISCC        : $Iscc"                    -ForegroundColor DarkGray

# ── Clean ─────────────────────────────────────────────────────────────────────

Write-Step "Cleaning previous build artifacts"

foreach ($path in @($DistDir, "build\pyinstaller", "build\$AppName", "$AppName.spec")) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        Write-Host "   Removed $path" -ForegroundColor DarkGray
    }
}

New-Item -ItemType Directory -Path "build\installer" -Force | Out-Null

# ── PyInstaller ───────────────────────────────────────────────────────────────

Write-Step "Running PyInstaller  (this may take several minutes)"

$PyArgs = @(
    "--name",      $AppName,
    "--windowed",
    "--onedir",
    "--icon",      "gfglock\assets\icons\gfgLock.ico",
    "--add-data",  "$ScriptDir\gfglock\qml;gfglock\qml",
    "--add-data",  "$ScriptDir\gfglock\assets;gfglock\assets",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.png;assets\icons",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.ico;assets\icons",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.png;icons",
    "--add-data",  "$ScriptDir\screenshots;screenshots",
    "--add-data",  "$ScriptDir\readme.html;.",
    "--distpath",  "dist",
    "--workpath",  "build\pyinstaller",
    "--specpath",  ".",
    "--noconfirm",
    "--clean",
    $Entry
)

pyinstaller @PyArgs

if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller failed (exit $LASTEXITCODE). Check output above."
}

$ExePath = "$DistDir\$AppName.exe"
if (-not (Test-Path $ExePath)) {
    Fail "Expected executable not found: $ExePath"
}

$BundleMb = [math]::Round((Get-ChildItem $DistDir -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "   Bundle ready : $DistDir  ($BundleMb MB)" -ForegroundColor DarkGray

# ── Inno Setup ────────────────────────────────────────────────────────────────

Write-Step "Compiling installer with Inno Setup"

Write-Host "   Compiling : $IssFile" -ForegroundColor DarkGray
& $Iscc $IssFile
if ($LASTEXITCODE -ne 0) {
    Fail "Inno Setup failed for '$IssFile' (exit $LASTEXITCODE)."
}

# ── Done ──────────────────────────────────────────────────────────────────────

if (-not (Test-Path $OutputExe)) {
    Fail "Expected installer not found: $OutputExe"
}

$Mb = [math]::Round((Get-Item $OutputExe).Length / 1MB, 1)
Write-Host ""
Write-Host "Build complete in $(Format-Elapsed ((Get-Date) - $BuildStart))." -ForegroundColor Green
Write-Host "Installer : $OutputExe  ($Mb MB)" -ForegroundColor Green
