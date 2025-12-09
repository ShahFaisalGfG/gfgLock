@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: SAFE VERSION — NO PATH MODIFICATION
:: This version always finds OpenSSL even if not in PATH.
:: ============================================================

:: --- Validate arguments ---
if "%~1"=="" (
  echo Usage: %~nx0 [encrypt|decrypt] "folder" "password"
  exit /b 1
)
if "%~2"=="" ( echo Missing folder path. & exit /b 1 )
if "%~3"=="" ( echo Missing password. & exit /b 1 )

set MODE=%~1
set FOLDER=%~2
set PASS=%~3

:: ============================================================
:: FIND OPENSSL WITHOUT USING PATH
:: ============================================================
set OPENSSL_EXE=

:: Common ShiningLight paths
if exist "C:\Program Files\OpenSSL-Win64\bin\openssl.exe" (
  set OPENSSL_EXE=C:\Program Files\OpenSSL-Win64\bin\openssl.exe
)
if exist "C:\Program Files\OpenSSL-Win32\bin\openssl.exe" (
  set OPENSSL_EXE=C:\Program Files\OpenSSL-Win32\bin\openssl.exe
)

:: Winget Win64 (MSI)
for /d %%D in ("C:\Program Files\OpenSSL*\bin") do (
  if exist "%%D\openssl.exe" set OPENSSL_EXE=%%D\openssl.exe
)

:: User installed version?
if exist "%LOCALAPPDATA%\Programs\OpenSSL\bin\openssl.exe" (
  set OPENSSL_EXE=%LOCALAPPDATA%\Programs\OpenSSL\bin\openssl.exe
)

:: Final check
if "%OPENSSL_EXE%"=="" (
  echo.
  echo OpenSSL not found.
  echo Installing OpenSSL using winget...
  winget install --id ShiningLight.OpenSSL.Light -e --silent --accept-package-agreements --accept-source-agreements
  echo Re-run this script after installation.
  exit /b 1
)

echo Using OpenSSL at:
echo %OPENSSL_EXE%
echo.
