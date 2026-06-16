<#
.SYNOPSIS
  Launch SAGA: start Postgres, run the backend (which serves API + the built
  frontend), open the browser, and stop Postgres when the app exits.

.DESCRIPTION
  Coupled on-demand lifecycle (docs/adr/0000): Postgres is started for the
  session and stopped in `finally` when uvicorn exits (Ctrl+C, or window close).
  Ctrl+C is a clean stop; on a hard window close Windows' ~5s grace is best-effort,
  but Postgres is crash-safe.
#>
[CmdletBinding()]
param(
  [int]$PgPort = 54320,
  [int]$AppPort = 8000
)

$ErrorActionPreference = "Stop"

# uv installs to the user profile; make sure a fresh launcher shell sees it.
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

$AppDir = (Resolve-Path "$PSScriptRoot\..").Path
$InstallRoot = Split-Path $AppDir -Parent
$PgBin  = Join-Path $InstallRoot "pg\pgsql\bin"
$PgData = Join-Path $InstallRoot "pgdata"
$logFile = Join-Path $InstallRoot "pg.log"

if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) {
  throw "Postgres not found at $PgBin. Run install_saga first."
}

Write-Host "Starting Postgres..." -ForegroundColor Cyan
& (Join-Path $PgBin "pg_ctl.exe") -D $PgData -o "-p $PgPort" -l $logFile -w start

# Open the browser once the app answers (uvicorn blocks below).
$opener = Start-Job -ArgumentList "http://localhost:$AppPort" -ScriptBlock {
  param($url)
  for ($i = 0; $i -lt 60; $i++) {
    try {
      Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
      Start-Process $url
      break
    } catch { Start-Sleep -Seconds 1 }
  }
}

try {
  Write-Host "SAGA is starting at http://localhost:$AppPort  (close this window or press Ctrl+C to stop)" -ForegroundColor Green
  Push-Location (Join-Path $AppDir "backend")
  try {
    uv run uvicorn app.main:app --host 127.0.0.1 --port $AppPort
  } finally { Pop-Location }
} finally {
  Stop-Job $opener -ErrorAction SilentlyContinue
  Remove-Job $opener -ErrorAction SilentlyContinue
  Write-Host "Stopping Postgres..." -ForegroundColor Cyan
  & (Join-Path $PgBin "pg_ctl.exe") -D $PgData -m fast -w stop
}
