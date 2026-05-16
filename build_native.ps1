<#
.SYNOPSIS
    Build the gfglock_native C++ extension (.pyd) and place it in gfglock/core/.
.DESCRIPTION
    Step 1 - Find and activate MSVC via vcvarsall.bat
    Step 2 - Bootstrap vcpkg if not present
    Step 3 - Install OpenSSL and pybind11 via vcpkg
    Step 4 - Install pybind11 into the Python venv
    Step 5 - CMake configure (release-x64-msvc preset)
    Step 6 - CMake build (Release)
    Step 7 - Verify gfglock_native.pyd landed in gfglock/core/
.NOTES
    Requirements: Visual Studio 2022 or newer Build Tools (MSVC, x64)
    vcpkg is bootstrapped automatically if .vcpkg/ is missing.
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$NativeDir = Join-Path $ScriptDir "native"
$BuildDir  = Join-Path $NativeDir "build"
$VcpkgDir  = Join-Path $ScriptDir ".vcpkg"
$OutPydGlob = Join-Path $ScriptDir "gfglock\core\gfglock_native*.pyd"

# --- Helpers -----------------------------------------------------------------

function Write-Step([string]$Msg) {
    Write-Host "`n>> $Msg" -ForegroundColor Cyan
}

function Fail([string]$Msg) {
    Write-Host "`nERROR: $Msg" -ForegroundColor Red
    exit 1
}

function Invoke-VcVars([string]$VcVarsPath) {
    Write-Host "   Sourcing: $VcVarsPath" -ForegroundColor DarkGray
    $dump = cmd /c "`"$VcVarsPath`" x64 2>&1 && set"
    foreach ($line in $dump) {
        if ($line -match "^([^=]+)=(.*)$") {
            [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

# --- Working directory -------------------------------------------------------

Set-Location $ScriptDir

# --- MSVC environment --------------------------------------------------------

Write-Step "Locating MSVC (vcvarsall.bat)"

$VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$VcVarsAll = $null
$VsInstallPath = $null

if (Test-Path $VsWhere) {
    $VsInstallPath = & $VsWhere -latest -products * -property installationPath 2>$null
    if ($VsInstallPath) {
        $Candidate = Join-Path $VsInstallPath "VC\Auxiliary\Build\vcvarsall.bat"
        if (Test-Path $Candidate) { $VcVarsAll = $Candidate }
    }
}

if (-not $VcVarsAll) {
    $SearchRoots = @(
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio",
        "${env:ProgramFiles}\Microsoft Visual Studio"
    )
    foreach ($Root in $SearchRoots) {
        $Found = Get-ChildItem "$Root\*\*\VC\Auxiliary\Build\vcvarsall.bat" -ErrorAction SilentlyContinue |
                 Sort-Object FullName -Descending | Select-Object -First 1
        if ($Found) { $VcVarsAll = $Found.FullName; $VsInstallPath = $Found.Directory.Parent.Parent.Parent.FullName; break }
    }
}

if (-not $VcVarsAll) {
    Fail "Could not find vcvarsall.bat. Install Visual Studio Build Tools with the C++ workload."
}

Invoke-VcVars $VcVarsAll

# Tell vcpkg exactly where VS lives so it doesn't rely on its own detection
if ($VsInstallPath) {
    $env:VCPKG_VISUAL_STUDIO_PATH = $VsInstallPath
    Write-Host "   VS path: $VsInstallPath" -ForegroundColor DarkGray
}

# --- Virtual environment -----------------------------------------------------

Write-Step "Activating virtual environment"

$VenvFound = $false
foreach ($v in @(".venv\Scripts\Activate.ps1", "venv\Scripts\Activate.ps1")) {
    if (Test-Path $v) { . $v; $VenvFound = $true; break }
}
if (-not $VenvFound) {
    Write-Host "   No venv found - using system Python" -ForegroundColor Yellow
}

# --- pybind11 ----------------------------------------------------------------

Write-Step "Checking pybind11"

$Pybind11Dir = python -c "import pybind11; print(pybind11.get_cmake_dir())" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $Pybind11Dir) {
    Write-Host "   Installing pybind11..." -ForegroundColor DarkGray
    pip install "pybind11[global]>=2.12" --quiet
    $Pybind11Dir = python -c "import pybind11; print(pybind11.get_cmake_dir())"
    if ($LASTEXITCODE -ne 0) { Fail "pybind11 install failed." }
}
Write-Host "   pybind11 cmake dir: $Pybind11Dir" -ForegroundColor DarkGray

# --- vcpkg bootstrap ---------------------------------------------------------

Write-Step "Checking vcpkg"

if (-not (Test-Path $VcpkgDir)) {
    Write-Host "   Bootstrapping vcpkg at $VcpkgDir ..." -ForegroundColor DarkGray
    git clone "https://github.com/microsoft/vcpkg.git" $VcpkgDir --depth 1 --quiet
    if ($LASTEXITCODE -ne 0) { Fail "vcpkg clone failed." }
    & "$VcpkgDir\bootstrap-vcpkg.bat" -disableMetrics 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "vcpkg bootstrap failed." }
    foreach ($item in @(".git", ".github", ".gitignore", ".gitattributes")) {
        Remove-Item -Recurse -Force (Join-Path $VcpkgDir $item) -ErrorAction SilentlyContinue
    }
}

$VcpkgExe = Join-Path $VcpkgDir "vcpkg.exe"
Write-Host "   vcpkg: $VcpkgExe" -ForegroundColor DarkGray

# --- vcpkg install OpenSSL ---------------------------------------------------

Write-Step "Installing OpenSSL via vcpkg"

$env:VCPKG_ROOT = $VcpkgDir
$SavedPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $VcpkgExe install --vcpkg-root="$VcpkgDir" --x-manifest-root="$NativeDir" --triplet x64-windows --allow-unsupported 2>&1 | Out-Null
$VcpkgExit = $LASTEXITCODE
$ErrorActionPreference = $SavedPref
if ($VcpkgExit -ne 0) { Fail "vcpkg install failed (exit $VcpkgExit). Re-run with output: & '$VcpkgExe' install --vcpkg-root='$VcpkgDir' --x-manifest-root='$NativeDir' --triplet x64-windows" }

# --- CMake configure ---------------------------------------------------------

Write-Step "CMake configure"

$Preset = "release-x64-msvc"
Write-Host "   Preset : $Preset" -ForegroundColor DarkGray

$CmakeArgs = @(
    "--preset", $Preset,
    "-S", $NativeDir,
    "-B", $BuildDir,
    "-Dpybind11_DIR=$Pybind11Dir"
)

cmake @CmakeArgs
if ($LASTEXITCODE -ne 0) { Fail "CMake configure failed (exit $LASTEXITCODE)." }

# --- CMake build -------------------------------------------------------------

Write-Step "CMake build (Release)"
cmake --build $BuildDir --config Release --parallel
if ($LASTEXITCODE -ne 0) { Fail "CMake build failed (exit $LASTEXITCODE)." }

# --- Verify output -----------------------------------------------------------

Write-Step "Verifying output"

$OutPyd = Get-ChildItem $OutPydGlob -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $OutPyd) {
    Fail "Expected .pyd not found in gfglock\core\ (pattern: $OutPydGlob)"
}

$Kb = [math]::Round($OutPyd.Length / 1KB, 1)
Write-Host ""
Write-Host "Native module ready: $($OutPyd.FullName)  ($Kb KB)" -ForegroundColor Green

# --- Quick smoke test --------------------------------------------------------

Write-Step "Smoke test"
python -c "import sys; sys.path.insert(0,'gfglock/core'); import gfglock_native as n; print('  NATIVE_AVAILABLE: True')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Smoke test FAILED - check build output" -ForegroundColor Red
} else {
    Write-Host "   Smoke test PASSED" -ForegroundColor Green
}
