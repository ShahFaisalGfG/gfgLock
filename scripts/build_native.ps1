<#
.SYNOPSIS
    Build the gfglock_native C++ extension (.pyd) and place it in gfglock/core/.
.DESCRIPTION
    Step 1 - Find and activate MSVC via vcvarsall.bat
    Step 2 - Bootstrap vcpkg if not present
    Step 3 - Install OpenSSL and pybind11 via vcpkg
    Step 4 - Install pybind11 into the Python venv
    Step 5c - CMake configure (release-x64-msvc preset)
    Step 6 - CMake build (Release)
    Step 7 - Verify gfglock_native.pyd landed in gfglock/core/
.NOTES
    Requirements: Visual Studio 2022 or newer Build Tools (MSVC, x64)
    vcpkg is bootstrapped automatically if .vcpkg/ is missing.
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$NativeDir   = Join-Path $ProjectRoot "native"
$BuildDir    = Join-Path $NativeDir "build"
$VcpkgDir    = Join-Path $ProjectRoot ".vcpkg"
$OutPydGlob  = Join-Path $ProjectRoot "gfglock\core\gfglock_native*.pyd"

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

Set-Location $ProjectRoot

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

# Locate the Ninja bundled with VS - its relative layout is stable across
# editions/versions, but the VS install root itself is not (differs between
# machines and between GitHub-hosted runner images), so this must be resolved
# fresh each run rather than hardcoded anywhere.
$NinjaExe = $null
if ($VsInstallPath) {
    $Candidate = Join-Path $VsInstallPath "Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
    if (Test-Path $Candidate) { $NinjaExe = $Candidate }
}
if (-not $NinjaExe) {
    $SystemNinja = Get-Command ninja -ErrorAction SilentlyContinue
    if ($SystemNinja) { $NinjaExe = $SystemNinja.Source }
}
if (-not $NinjaExe) {
    Fail "Could not find ninja.exe (checked VS install and PATH). Install the C++ CMake tools for Windows workload."
}
Write-Host "   Ninja: $NinjaExe" -ForegroundColor DarkGray

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

$PythonExe = python -c "import sys; print(sys.executable)"
Write-Host "   Python executable : $PythonExe" -ForegroundColor DarkGray

# vcpkg ships its own python3 port for build-time tooling (e.g. meson), and
# registers a CMake find-module wrapper that hijacks find_package(Python ...)
# to resolve Development headers/libs from that vcpkg-internal copy instead of
# the interpreter we actually target. Pre-supplying the real include dir and
# import lib bypasses that wrapper's search and pins Development.Module to the
# Python this extension must actually load under (sys.base_prefix survives
# being called from inside a venv, where it differs from sys.prefix).
$PyDevPaths = python -c "import sys, sysconfig, os; print(sysconfig.get_path('include')); print(os.path.join(sys.base_prefix, 'libs', 'python' + sysconfig.get_config_var('py_version_nodot') + '.lib'))"
$PyIncludeDir, $PyLibrary = $PyDevPaths
if (-not (Test-Path $PyIncludeDir) -or -not (Test-Path $PyLibrary)) {
    Fail "Could not locate Python development headers/library ($PyIncludeDir / $PyLibrary). Install the full Python distribution (not just the interpreter)."
}
Write-Host "   Python include     : $PyIncludeDir" -ForegroundColor DarkGray
Write-Host "   Python import lib  : $PyLibrary" -ForegroundColor DarkGray

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
& $VcpkgExe install --vcpkg-root="$VcpkgDir" --x-manifest-root="$NativeDir" --triplet x64-windows --allow-unsupported
$VcpkgExit = $LASTEXITCODE
$ErrorActionPreference = $SavedPref
if ($VcpkgExit -ne 0) { Fail "vcpkg install failed (exit $VcpkgExit)." }

# --- CMake configure ---------------------------------------------------------

Write-Step "CMake configure"

$Preset = "release-x64-msvc"
Write-Host "   Preset : $Preset" -ForegroundColor DarkGray

$CmakeArgs = @(
    "--preset", $Preset,
    "-S", $NativeDir,
    "-B", $BuildDir,
    "-DCMAKE_MAKE_PROGRAM=$NinjaExe",
    "-Dpybind11_DIR=$Pybind11Dir",
    "-DPython_EXECUTABLE=$PythonExe",
    "-DPython_INCLUDE_DIR=$PyIncludeDir",
    "-DPython_LIBRARY=$PyLibrary"
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

$ShellDll = Join-Path $ProjectRoot "build\shell\gfglock_shell.dll"
if (-not (Test-Path $ShellDll)) {
    Fail "Expected gfglock_shell.dll not found at: $ShellDll"
}

$PydKb  = [math]::Round($OutPyd.Length / 1KB, 1)
$DllKb  = [math]::Round((Get-Item $ShellDll).Length / 1KB, 1)
Write-Host ""
Write-Host "Native module ready : $($OutPyd.FullName)  ($PydKb KB)" -ForegroundColor Green
Write-Host "Shell extension     : $ShellDll  ($DllKb KB)" -ForegroundColor Green

# --- Quick smoke test --------------------------------------------------------

Write-Step "Smoke test"
python -c "import sys; sys.path.insert(0,'gfglock/core'); import gfglock_native as n; print('  NATIVE_AVAILABLE: True')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Smoke test FAILED - check build output" -ForegroundColor Red
} else {
    Write-Host "   Smoke test PASSED" -ForegroundColor Green
}
