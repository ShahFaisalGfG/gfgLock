:: gfglock_openssl.bat
:: Usage:
::   gfglock_openssl.bat encrypt "C:\path\folder" "mypassword"
::   gfglock_openssl.bat decrypt "C:\path\folder" "mypassword"

@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo Usage: %~nx0 [encrypt|decrypt] "folder" "password"
  exit /b 1
)
set MODE=%~1
set FOLDER=%~2
set PASS=%~3

if "%MODE%"=="encrypt" (
  for /r "%FOLDER%" %%F in (*) do (
    set "src=%%~fF"
    echo Processing: !src!
    if /I "!src:~-8!"==".gfglock" (
      echo Already encrypted: !src!
    ) else (
      set "name=%%~nxF"
      set "base=%%~nF"
      set "dir=%%~dpF"
      set "out=!dir!!base!.gfglock"
      rem Write a simple header: original name + null + OpenSSL ciphertext
      rem Create a temp header file
      echo !name!> "!dir!tmp_name.txt"
      rem Convert to binary with null termination
      certutil -encodehex "!dir!tmp_name.txt" "!dir!tmp_name.bin" 0x00 >nul
      del "!dir!tmp_name.txt"
      rem Encrypt content and prepend header
      rem Note: You can use aes-256-cfb or aes-256-ctr
      openssl enc -aes-256-cfb -salt -pass pass:%PASS% -in "!src!" -out "!dir!tmp_data.bin"
      copy /b "!dir!tmp_name.bin"+"!dir!tmp_data.bin" "!out!" >nul
      del "!dir!tmp_name.bin" "!dir!tmp_data.bin"
      del "!src!"
      echo Encrypted: !src! -> !out!
    )
  )
  echo Done.
  exit /b 0
)

if "%MODE%"=="decrypt" (
  for /r "%FOLDER%" %%F in (*.gfglock) do (
    set "src=%%~fF"
    set "dir=%%~dpF"
    echo Processing: !src!
    rem Extract header until null (this sample is simplified; for robust parsing, use a small helper exe)
    rem For practical workflows, keep a sidecar mapping, or use the Python decrypt which reads the header.
    echo This demo decrypt path assumes sidecar mapping or header-aware tool.
    rem If you maintain a mapping file (src->original), you can:
    rem openssl enc -d -aes-256-cfb -pass pass:%PASS% -in "!src!" -out "!dir!original.ext"
  )
  echo Done.
  exit /b 0
)

echo Invalid mode: %MODE%
exit /b 1