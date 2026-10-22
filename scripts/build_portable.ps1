#Requires -Version 7.2
<#
.SYNOPSIS
    Build the gfgLock portable single-file executable.
.DESCRIPTION
    Bundles the app into one self-contained exe, build\gfgLock_<version>_portable.exe, and runs
    its --self-test. No installer is produced: the exe runs without installation and keeps its
    settings and logs in a "gfgLock data" folder beside itself.
.NOTES
    Requirements: PowerShell 7.2+ and the venv from requirements.txt (see dev_setup.md). It uses
    the gfglock_native.pyd that scripts\build_native.ps1 last built.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\bundle.ps1"

$BuildStart = Get-Date
Set-Location (Split-Path -Parent $PSScriptRoot)

Enable-Venv
Assert-BuildTools
$Meta = Get-AppMeta

$PortableExe = New-AppBundle -Name "$($Meta.AppName)_$($Meta.Version)_portable" -Mode onefile -DistPath "build"

Write-Host ""
Write-Host "Build complete in $(Format-Elapsed ((Get-Date) - $BuildStart))." -ForegroundColor Green
Write-Host "Portable  : $PortableExe  ($(Get-SizeMb $PortableExe) MB)" -ForegroundColor Green
