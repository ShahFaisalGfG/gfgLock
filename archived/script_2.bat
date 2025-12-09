@echo off
setlocal EnableDelayedExpansion

goto :main

:: ============================================================
:: ENCRYPT SINGLE FILE
:: ============================================================
:encrypt_file
set "INFILE=%~1"

if not exist "%INFILE%" (
    echo [ERR] File not found: "%INFILE%"
    exit /b 1
)

if /i "%INFILE:~-8%"==".gfglock" (
    echo [SKIP] Already encrypted: "%INFILE%"
    exit /b 0
)

set "OUTFILE=%INFILE%.gfglock"
"%OPENSSL_EXE%" enc -aes-256-cfb -salt -pbkdf2 -pass pass:"%PASSWORD%" -in "%INFILE%" -out "%OUTFILE%"
if errorlevel 1 (
    echo [ERR] Encryption failed: "%INFILE%"
    if exist "%OUTFILE%" del /q "%OUTFILE%"
    exit /b 1
)

del /q "%INFILE%"
echo Encrypted: "%INFILE%"
exit /b 0

:: ============================================================
:: DECRYPT SINGLE FILE
:: ============================================================
:decrypt_file
set "INFILE=%~1"

if /i not "%INFILE:~-8%"==".gfglock" (
    echo [SKIP] Not an encrypted file: "%INFILE%"
    exit /b 0
)

set "OUTFILE=%INFILE:~0,-8%"
"%OPENSSL_EXE%" enc -d -aes-256-cfb -pbkdf2 -pass pass:"%PASSWORD%" -in "%INFILE%" -out "%OUTFILE%"
if errorlevel 1 (
    echo [ERR] Decryption failed: "%INFILE%"
    if exist "%OUTFILE%" del /q "%OUTFILE%"
    exit /b 1
)

del /q "%INFILE%"
echo Decrypted: "%INFILE%"
exit /b 0

:: ============================================================
:: ENCRYPT FOLDER
:: ============================================================
:encrypt_folder
set "FOLDER=%~1"
echo Folder mode detected.
echo Encrypting all files in: "%FOLDER%"
echo.

set "STARTTIME=%TIME%"
for /f "delims=" %%F in ('dir /b /s /a-d "%FOLDER%"') do (
    call :encrypt_file "%%F"
)
set "ENDTIME=%TIME%"

call :show_elapsed !STARTTIME! !ENDTIME! "Encryption completed successfully."
exit /b

:: ============================================================
:: DECRYPT FOLDER
:: ============================================================
:decrypt_folder
set "FOLDER=%~1"
echo Folder mode detected.
echo Decrypting all .gfglock files in: "%FOLDER%"
echo.

set "STARTTIME=%TIME%"
for /f "delims=" %%F in ('dir /b /s /a-d "%FOLDER%"^|findstr /i "\.gfglock$"') do (
    call :decrypt_file "%%F"
)
set "ENDTIME=%TIME%"

call :show_elapsed !STARTTIME! !ENDTIME! "Decryption completed successfully."
exit /b

:: ============================================================
:: CALCULATE AND SHOW ELAPSED TIME
:: ============================================================
:show_elapsed
set "START=%~1"
set "END=%~2"
set "MSG=%~3"

:: Convert HH:MM:SS.mmm to seconds
for /f "tokens=1-4 delims=:." %%a in ("%START%") do set /a "S1=%%a*3600 + %%b*60 + %%c"
for /f "tokens=1-4 delims=:." %%a in ("%END%") do set /a "S2=%%a*3600 + %%b*60 + %%c"

set /a "ELAPSED=S2 - S1"
if !ELAPSED! lss 0 set /a "ELAPSED+=86400"

set /a "H=ELAPSED/3600"
set /a "M=(ELAPSED%%3600)/60"
set /a "S=ELAPSED%%60"

:: Build formatted time output
set "OUTPUT="

if !H! GTR 0 (
    set "OUTPUT=!H! hrs"
)

if !M! GTR 0 (
    if defined OUTPUT (
        set "OUTPUT=!OUTPUT! !M! mins"
    ) else (
        set "OUTPUT=!M! mins"
    )
)

:: Always add seconds
if defined OUTPUT (
    set "OUTPUT=!OUTPUT! !S! sec"
) else (
    set "OUTPUT=!S! sec"
)

echo.
echo %MSG%
echo Elapsed time: !OUTPUT!
echo.
exit /b

:: ============================================================
:: MAIN
:: ============================================================
:main

:: Check arguments
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
if "%~3"=="" goto :usage

set "MODE=%~1"
set "INPUT_PATH=%~2"
set "PASSWORD=%~3"

:: Locate OpenSSL
set "OPENSSL_EXE="
for %%P in (
    "C:\Program Files\OpenSSL-Win64\bin\openssl.exe"
    "C:\Program Files\OpenSSL-Win32\bin\openssl.exe"
    "%LOCALAPPDATA%\Programs\OpenSSL\bin\openssl.exe"
) do (
    if exist %%~P set "OPENSSL_EXE=%%~P"
)

if "%OPENSSL_EXE%"=="" (
    where openssl >nul 2>&1
    if not errorlevel 1 for /f "delims=" %%O in ('where openssl') do set "OPENSSL_EXE=%%O"
)

if "%OPENSSL_EXE%"=="" (
    echo OpenSSL not found. Install it first.
    exit /b 1
)

echo Using OpenSSL: "%OPENSSL_EXE%"
echo.

:: Detect folder or file
if exist "%INPUT_PATH%\" (
    set "IS_FOLDER=1"
) else (
    set "IS_FOLDER=0"
)

:: Execute based on mode
if /i "%MODE%"=="encrypt" (
    if %IS_FOLDER%==1 (
        call :encrypt_folder "%INPUT_PATH%"
    ) else (
        set "STARTTIME=%TIME%"
        call :encrypt_file "%INPUT_PATH%"
        set "ENDTIME=%TIME%"
        call :show_elapsed !STARTTIME! !ENDTIME! "Encryption completed successfully."
    )
    exit /b
)

if /i "%MODE%"=="decrypt" (
    if %IS_FOLDER%==1 (
        call :decrypt_folder "%INPUT_PATH%"
    ) else (
        set "STARTTIME=%TIME%"
        call :decrypt_file "%INPUT_PATH%"
        set "ENDTIME=%TIME%"
        call :show_elapsed !STARTTIME! !ENDTIME! "Decryption completed successfully."
    )
    exit /b
)

goto :usage

:usage
echo Usage:
echo   %~nx0 encrypt "file_or_folder" "password"
echo   %~nx0 decrypt "file_or_folder" "password"
exit /b
