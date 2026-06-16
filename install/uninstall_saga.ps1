<#
.SYNOPSIS
  Remove a SAGA native install: stop Postgres, delete the desktop shortcut, and
  remove %LOCALAPPDATA%\SAGA (app + database). Game data is deleted - export first
  if you want to keep a campaign.
#>
[CmdletBinding()]
param([switch]$Yes)

$ErrorActionPreference = "Stop"

$AppDir = (Resolve-Path "$PSScriptRoot\..").Path
$InstallRoot = Split-Path $AppDir -Parent
$PgBin  = Join-Path $InstallRoot "pg\pgsql\bin"
$PgData = Join-Path $InstallRoot "pgdata"

if (-not $Yes) {
  $ans = Read-Host "This deletes $InstallRoot including all game data. Type 'yes' to continue"
  if ($ans -ne "yes") { Write-Host "Aborted."; return }
}

if (Test-Path (Join-Path $PgBin "pg_ctl.exe")) {
  Write-Host "Stopping Postgres (if running)..."
  & (Join-Path $PgBin "pg_ctl.exe") -D $PgData -m fast -w stop 2>$null
}

$shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "SAGA.lnk"
if (Test-Path $shortcut) { Remove-Item $shortcut -Force }

# Step outside the tree before deleting it.
Set-Location $env:TEMP
Remove-Item -Recurse -Force $InstallRoot
Write-Host "SAGA removed." -ForegroundColor Green
