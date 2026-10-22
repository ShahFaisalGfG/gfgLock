#Requires -Version 7.2
<#
.SYNOPSIS
    Build the gfgLock system-wide or per-user Windows installer.
.DESCRIPTION
    Step 1 - Native build : gfglock_native.pyd and gfglock_shell.dll (scripts\build_native.ps1)
    Step 2 - PyInstaller  : the app bundle in dist\gfgLock\, then its --self-test
    Step 3 - Inno Setup   : build\installer\gfgLock_<version>_<kind>_installer.exe
.PARAMETER Kind
    System installs for all users into Program Files (needs admin rights); User installs for
    the current user into %APPDATA%\gfgLock (no admin rights).
.NOTES
    Requirements: PowerShell 7.2+, the venv from requirements.txt, Inno Setup 6, and Visual Studio
    Build Tools (see dev_setup.md)
#>

param(
    [Parameter(Mandatory)] [ValidateSet("User", "System")] [string]$Kind
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\bundle.ps1"

$BuildStart = Get-Date
Set-Location (Split-Path -Parent $PSScriptRoot)

Enable-Venv
Assert-BuildTools -Installer
$Meta = Get-AppMeta
Invoke-NativeBuild

$null = New-AppBundle -Name $Meta.AppName -Mode onedir -DistPath "dist"

Write-Step "Compiling the $($Kind.ToLowerInvariant()) installer with Inno Setup"
$Installer = Invoke-Iscc -Kind $Kind -Meta $Meta

Write-Host ""
Write-Host "Build complete in $(Format-Elapsed ((Get-Date) - $BuildStart))." -ForegroundColor Green
Write-Host "Installer : $Installer  ($(Get-SizeMb $Installer) MB)" -ForegroundColor Green
