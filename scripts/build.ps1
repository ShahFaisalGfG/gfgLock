#Requires -Version 7.2
<#
.SYNOPSIS
    Full build: native targets, both installers, and the portable exe.
.DESCRIPTION
    Step 1 - Native build : gfglock_native.pyd and gfglock_shell.dll (scripts\build_native.ps1)
    Step 2 - PyInstaller  : the app bundle in dist\gfgLock\, then its --self-test
    Step 3 - Inno Setup   : the system and per-user installers in build\installer\
    Step 4 - Portable     : the single-file exe in build\, then its --self-test
.NOTES
    Requirements: PowerShell 7.2+, the venv from requirements.txt, Inno Setup 6, and Visual Studio
    Build Tools (see dev_setup.md)
#>

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

Write-Step "Compiling installers with Inno Setup"
$Installers = foreach ($Kind in "System", "User") {
    $Start = Get-Date
    $Path = Invoke-Iscc -Kind $Kind -Meta $Meta
    [pscustomobject]@{ Path = $Path; Elapsed = (Get-Date) - $Start }
}

$PortableStart = Get-Date
$PortableExe = New-AppBundle -Name "$($Meta.AppName)_$($Meta.Version)_portable" -Mode onefile -DistPath "build"
$PortableElapsed = (Get-Date) - $PortableStart

Write-Host ""
Write-Host "Build complete in $(Format-Elapsed ((Get-Date) - $BuildStart))." -ForegroundColor Green
foreach ($Installer in $Installers) {
    Write-Host "Installer    : $($Installer.Path)  ($(Get-SizeMb $Installer.Path) MB)  ($(Format-Elapsed $Installer.Elapsed))" -ForegroundColor Green
}
Write-Host "Portable Exe : $PortableExe  ($(Get-SizeMb $PortableExe) MB)  ($(Format-Elapsed $PortableElapsed))" -ForegroundColor Green
