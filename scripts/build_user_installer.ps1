<#
.SYNOPSIS
    Build the gfgLock per-user Windows installer.
.DESCRIPTION
    Step 1 - Native build : compiles gfglock_native.pyd and gfglock_shell.dll
    Step 2 - PyInstaller  : bundles the app into dist\gfgLock\
    Step 3 - Shell DLL    : copies gfglock_shell.dll into dist\gfgLock\
    Step 4 - Inno Setup   : compiles the per-user installer into build\installer\
.NOTES
    Requirements: Python venv with pyinstaller>=6.17, Inno Setup 6, Visual Studio Build Tools
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ─────────────────────────────────────────────────────────────

$Entry   = "gfglock\__main__.py"
$IssFile = "installer\gfglock_user_installer.iss"

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
    # $ts.Minutes/.Seconds are sub-hour remainders (0-59) - the hours branch must
    # come first, or any run past 60 minutes silently drops its hour component.
    if ($ts.TotalHours -ge 1)   { return "{0}h {1:D2}m {2:D2}s" -f [int]$ts.TotalHours, $ts.Minutes, $ts.Seconds }
    if ($ts.TotalMinutes -ge 1) { return "{0}m {1:D2}s" -f [int]$ts.Minutes, $ts.Seconds }
    return "{0}s" -f [int]$ts.TotalSeconds
}

# ── Working directory ─────────────────────────────────────────────────────────

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$BuildStart  = Get-Date
Set-Location $ProjectRoot

# ── App metadata ──────────────────────────────────────────────────────────────

. "$ScriptDir\app_meta.ps1"
$Meta      = Get-AppMeta
$AppName   = $Meta.AppName
$Version   = $Meta.Version
$DistDir   = "dist\$AppName"
$OutputExe = "build\installer\${AppName}_${Version}_user_installer.exe"

# ── Native C++ targets ────────────────────────────────────────────────────────

Write-Step "Building native C++ targets (gfglock_native.pyd + gfglock_shell.dll)"

& "$ScriptDir\build_native.ps1"
if ($LASTEXITCODE -ne 0) {
    Fail "build_native.ps1 failed (exit $LASTEXITCODE). Check output above."
}

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
    Write-Host "   No venv found - using system Python" -ForegroundColor Yellow
}

# ── Prerequisites ─────────────────────────────────────────────────────────────

Write-Step "Checking prerequisites"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fail "python not found in PATH"
}
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Fail "pyinstaller not found. Install it with: pip install 'pyinstaller>=6.17'"
}

$IsccPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
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
    "--add-data",  "$ProjectRoot\gfglock\qml;gfglock\qml",
    "--add-data",  "$ProjectRoot\gfglock\assets;gfglock\assets",
    "--add-data",  "$ProjectRoot\gfglock\assets\icons\gfgLock.png;assets\icons",
    "--add-data",  "$ProjectRoot\gfglock\assets\icons\gfgLock.ico;assets\icons",
    "--add-data",  "$ProjectRoot\gfglock\assets\icons\gfgLock.png;icons",
    "--add-data",  "$ProjectRoot\screenshots;screenshots",
    "--add-data",  "$ProjectRoot\readme.html;.",
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

# ── Shell extension DLL ───────────────────────────────────────────────────────

Write-Step "Copying gfglock_shell.dll to dist"

$ShellDll = Join-Path $ProjectRoot "build\shell\gfglock_shell.dll"
if (-not (Test-Path $ShellDll)) {
    Fail "gfglock_shell.dll not found at: $ShellDll - run build_native.ps1 first."
}
Copy-Item $ShellDll (Join-Path $ProjectRoot "dist\$AppName\gfglock_shell.dll") -Force
Write-Host "   Copied gfglock_shell.dll to dist\$AppName\" -ForegroundColor DarkGray

# ── Inno Setup ────────────────────────────────────────────────────────────────

Write-Step "Compiling installer with Inno Setup"

Write-Host "   Compiling : $IssFile" -ForegroundColor DarkGray
& $Iscc `
    "/DMyAppName=$($Meta.AppName)" `
    "/DMyAppVersion=$($Meta.Version)" `
    "/DMyAppPublisher=$($Meta.Publisher)" `
    "/DMyAppURL=$($Meta.Url)" `
    $IssFile
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
