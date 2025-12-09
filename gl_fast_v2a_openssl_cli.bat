@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: gfglock_openssl.bat - Production Ready
:: Usage:
::   gfglock_openssl.bat encrypt "C:\path\folder" "mypassword" true
::   gfglock_openssl.bat decrypt "C:\path\folder" "mypassword" false

::   gl_v2a_openssl_cli.bat encrypt "C:\Users\shahf\Music\Archives1" "mypassword"
::   gl_v2a_openssl_cli.bat decrypt "C:\Users\shahf\Music\Archives1" "mypassword"
:: ============================================================

:: --- Check arguments ---
if "%~1"=="" (
  echo Usage: %~nx0 [encrypt|decrypt] "folder" "password" [encryptname:true|false]
  exit /b 1
)
if "%~2"=="" (
  echo Missing folder path.
  exit /b 1
)
if "%~3"=="" (
  echo Missing password.
  exit /b 1
)
if "%~4"=="" (
  echo Missing encryptname flag (true/false).
  exit /b 1
)

set MODE=%~1
set FOLDER=%~2
set PASS=%~3
set ENCRYPTNAME=%~4

:: --- Check if OpenSSL is installed ---
where openssl >nul 2>&1
if errorlevel 1 (
  echo.
  echo OpenSSL is not installed or not in PATH.
  echo It is required for gfglock to work.
  echo.
  set /p choice="Do you want to install OpenSSL via winget now? (Y/n): "
  if /i "%choice%"=="n" (
    echo Exiting program.
    exit /b 1
  )
  if /i "%choice%"=="" (
    echo Installing OpenSSL via winget...
    winget install OpenSSL --exact --silent --accept-package-agreements --accept-source-agreements
    echo Please restart your terminal after installation and re-run this script.
    exit /b 0
  )
  if /i "%choice%"=="y" (
    echo Installing OpenSSL via winget...
    winget install OpenSSL
    echo Please restart your terminal after installation and re-run this script.
    exit /b 0
  )
)

:: --- Process files ---
if /i "%MODE%"=="encrypt" (
  for /r "%FOLDER%" %%F in (*) do (
    set "src=%%~fF"
    if /i "!src:~-8!"==".gfglock" (
      echo Already encrypted: !src!
    ) else (
      set "base=%%~nF"
      set "dir=%%~dpF"

      if /i "%ENCRYPTNAME%"=="true" (
        for /f "tokens=1-4 delims=/:. " %%a in ("%%~tF") do (
          set "ts=%%a%%b%%c%%d"
        )
        set "rand=!random!"
        set "out=!dir!!ts!_!rand!.gfglock"
      ) else (
        set "out=!dir!!base!.gfglock"
      )

      echo Encrypting: !src! -> !out!
      openssl enc -aes-256-cfb -salt -pass pass:%PASS% -in "!src!" -out "!out!"
      if not errorlevel 1 (
        del "!src!"
      ) else (
        echo Failed to encrypt: !src!
      )
    )
  )
  echo Done encrypting.
  exit /b 0
)

if /i "%MODE%"=="decrypt" (
  for /r "%FOLDER%" %%F in (*.gfglock) do (
    set "src=%%~fF"
    set "dir=%%~dpF"
    set "base=%%~nF"

    echo Decrypting: !src!
    set "out=!dir!!base!.restored"
    openssl enc -d -aes-256-cfb -pass pass:%PASS% -in "!src!" -out "!out!"
    if not errorlevel 1 (
      del "!src!"
    ) else (
      echo Failed to decrypt: !src!
    )
  )
  echo Done decrypting.
  exit /b 0
)

echo Invalid mode: %MODE%
exit /b 1