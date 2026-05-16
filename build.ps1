<#
.SYNOPSIS
    Full build: native targets, both installers, and portable exe.
.DESCRIPTION
    Step 1 — Native build : compiles gfglock_native.pyd and gfglock_shell.dll
    Step 2 — PyInstaller  : bundles the app into dist\gfgLock\
    Step 3 — Shell DLL    : copies gfglock_shell.dll into dist\gfgLock\
    Step 4 — Inno Setup   : compiles system and user installers into build\installer\
    Step 5 — Portable     : builds a single-file portable exe into build\
.NOTES
    Requirements: Python venv with pyinstaller>=6.17, Inno Setup 6, Visual Studio Build Tools
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ─────────────────────────────────────────────────────────────

$AppName  = "gfgLock"
$Version  = "3.0.0"
$Entry    = "gfglock\__main__.py"
$DistDir  = "dist\$AppName"
$IssFiles = @(
    "installer\gfglock_system_installer.iss",
    "installer\gfglock_user_installer.iss"
)
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

function Invoke-Iscc([string]$IssPath) {
    Write-Host "   Compiling : $IssPath" -ForegroundColor DarkGray
    & $Iscc $IssPath
    if ($LASTEXITCODE -ne 0) {
        Fail "Inno Setup failed for '$IssPath' (exit $LASTEXITCODE)."
    }
}

function Format-Elapsed([TimeSpan]$ts) {
    if ($ts.TotalMinutes -ge 1) { return "{0}m {1:D2}s" -f [int]$ts.Minutes, $ts.Seconds }
    return "{0}s" -f [int]$ts.TotalSeconds
}

# ── Working directory ─────────────────────────────────────────────────────────

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BuildStart = Get-Date
Set-Location $ScriptDir

# ── Native C++ extension ──────────────────────────────────────────────────────

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

$Iscc = $null
foreach ($p in $IsccPaths) {
    if (Test-Path $p) { $Iscc = $p; break }
}
if (-not $Iscc) {
    Fail "Inno Setup 6 not found. Download from: https://jrsoftware.org/isinfo.php"
}

Write-Host "   Python      : $(python --version)"         -ForegroundColor DarkGray
Write-Host "   PyInstaller : $(pyinstaller --version)"    -ForegroundColor DarkGray
Write-Host "   ISCC        : $Iscc"                       -ForegroundColor DarkGray

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

# ── Shell extension DLL ───────────────────────────────────────────────────────

Write-Step "Copying gfglock_shell.dll to dist"

$ShellDll = Join-Path $ScriptDir "build\shell\gfglock_shell.dll"
if (-not (Test-Path $ShellDll)) {
    Fail "gfglock_shell.dll not found at: $ShellDll - did build_native.ps1 succeed?"
}
Copy-Item $ShellDll (Join-Path $ScriptDir "dist\$AppName\gfglock_shell.dll") -Force
Write-Host "   Copied gfglock_shell.dll to dist\$AppName\" -ForegroundColor DarkGray

# ── Inno Setup ────────────────────────────────────────────────────────────────

Write-Step "Compiling installers with Inno Setup"

$IsccElapsed = @()
foreach ($iss in $IssFiles) {
    $t = Get-Date
    Invoke-Iscc $iss
    $IsccElapsed += (Get-Date) - $t
}

# ── Portable Exe ──────────────────────────────────────────────────────────────

Write-Step "Building portable executable"

$PortableName = "${AppName}_${Version}_portable"
$PortableExe  = "build\${PortableName}.exe"

foreach ($path in @("${PortableName}.spec", $PortableExe)) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
        Write-Host "   Removed $path" -ForegroundColor DarkGray
    }
}

$PortableArgs = @(
    "--name",      $PortableName,
    "--windowed",
    "--onefile",
    "--icon",      "gfglock\assets\icons\gfgLock.ico",
    "--add-data",  "$ScriptDir\gfglock\qml;gfglock\qml",
    "--add-data",  "$ScriptDir\gfglock\assets;gfglock\assets",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.png;assets\icons",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.ico;assets\icons",
    "--add-data",  "$ScriptDir\gfglock\assets\icons\gfgLock.png;icons",
    "--add-data",  "$ScriptDir\screenshots;screenshots",
    "--add-data",  "$ScriptDir\readme.html;.",
    "--distpath",  "build",
    "--workpath",  "build\pyinstaller",
    "--specpath",  ".",
    "--noconfirm",
    "--clean",
    $Entry
)

$PortableStart = Get-Date
pyinstaller @PortableArgs

if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller (portable) failed (exit $LASTEXITCODE). Check output above."
}
if (-not (Test-Path $PortableExe)) {
    Fail "Expected portable executable not found: $PortableExe"
}
$PortableElapsed = (Get-Date) - $PortableStart

# ── Done ──────────────────────────────────────────────────────────────────────

$Outputs = @(
    "build\installer\${AppName}_${Version}_system_installer.exe",
    "build\installer\${AppName}_${Version}_user_installer.exe"
)

Write-Host ""
Write-Host "Build complete in $(Format-Elapsed ((Get-Date) - $BuildStart))." -ForegroundColor Green

for ($i = 0; $i -lt $Outputs.Count; $i++) {
    $out = $Outputs[$i]
    if (Test-Path $out) {
        $Mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
        $elapsed = if ($i -lt $IsccElapsed.Count) { "  ($(Format-Elapsed $IsccElapsed[$i]))" } else { "" }
        Write-Host "Installer    : $out  ($Mb MB)$elapsed" -ForegroundColor Green
    } else {
        Write-Host "Missing      : $out" -ForegroundColor Yellow
    }
}

if (Test-Path $PortableExe) {
    $PortableMb = [math]::Round((Get-Item $PortableExe).Length / 1MB, 1)
    Write-Host "Portable Exe : $PortableExe  ($PortableMb MB)  ($(Format-Elapsed $PortableElapsed))" -ForegroundColor Green
} else {
    Write-Host "Missing      : $PortableExe" -ForegroundColor Yellow
}
