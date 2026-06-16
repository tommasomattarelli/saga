<#
.SYNOPSIS
  Assemble the pinned Postgres+pgvector bundle that the installer downloads.
  Run once by a maintainer; upload the resulting zip as a GitHub Release asset and
  set its URL as the installer's -BundleUrl / $env:SAGA_BUNDLE_URL.

.DESCRIPTION
  Produces a zip whose root is a `pgsql\` directory (bin/lib/share) with the
  pgvector `vector` extension dropped in. The installer expects exactly this
  layout (it unpacks to %LOCALAPPDATA%\SAGA\pg, then uses pg\pgsql\bin).

.PARAMETER PgBinaries
  URL or local path to the EnterpriseDB "binaries only" Windows x64 zip for
  Postgres 16.x (https://www.enterprisedb.com/download-postgresql-binaries).

.PARAMETER Pgvector
  URL or local path to precompiled pgvector for the SAME Postgres major (e.g. a
  release asset from https://github.com/andreiramani/pgvector_pgsql_windows).
  Must contain vector.dll, vector.control and vector--*.sql.
#>
[CmdletBinding()]
param(
  # URL or local path to the EDB Postgres "binaries only" zip.
  [Parameter(Mandatory)][string]$PgBinaries,
  # URL or local path to the precompiled pgvector zip (same PG major).
  [Parameter(Mandatory)][string]$Pgvector,
  [string]$OutZip = "saga-pg-bundle.zip"
)

$ErrorActionPreference = "Stop"

# Accept a URL or an already-downloaded local file (EDB's getfile.jsp can be
# awkward to script - download via browser and pass the path instead).
function Resolve-Zip($src, $dest) {
  if (Test-Path $src) { Copy-Item -LiteralPath $src -Destination $dest -Force }
  else { Invoke-WebRequest -Uri $src -OutFile $dest }
}
$work = Join-Path $env:TEMP ("saga-bundle-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $work | Out-Null

try {
  Write-Host "Fetching Postgres binaries..." -ForegroundColor Cyan
  $pgZip = Join-Path $work "pg.zip"
  Resolve-Zip $PgBinaries $pgZip
  Expand-Archive -Path $pgZip -DestinationPath $work -Force
  $pgsql = Join-Path $work "pgsql"
  if (-not (Test-Path (Join-Path $pgsql "bin\initdb.exe"))) {
    throw "Expected a 'pgsql' dir with bin\initdb.exe in the Postgres zip."
  }

  Write-Host "Fetching pgvector..." -ForegroundColor Cyan
  $vecZip = Join-Path $work "pgvector.zip"
  Resolve-Zip $Pgvector $vecZip
  $vecDir = Join-Path $work "pgvector"
  Expand-Archive -Path $vecZip -DestinationPath $vecDir -Force

  $dll = Get-ChildItem -Path $vecDir -Recurse -Filter "vector.dll" | Select-Object -First 1
  $ctl = Get-ChildItem -Path $vecDir -Recurse -Filter "vector.control" | Select-Object -First 1
  $sql = Get-ChildItem -Path $vecDir -Recurse -Filter "vector--*.sql"
  if (-not $dll -or -not $ctl -or -not $sql) {
    throw "pgvector zip is missing vector.dll / vector.control / vector--*.sql."
  }

  Write-Host "Installing pgvector into the bundle..." -ForegroundColor Cyan
  Copy-Item $dll.FullName (Join-Path $pgsql "lib")
  Copy-Item $ctl.FullName (Join-Path $pgsql "share\extension")
  $sql | ForEach-Object { Copy-Item $_.FullName (Join-Path $pgsql "share\extension") }

  Write-Host "Compressing bundle to $OutZip..." -ForegroundColor Cyan
  if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
  Compress-Archive -Path $pgsql -DestinationPath $OutZip
  Write-Host "[OK] Bundle ready: $OutZip" -ForegroundColor Green
  Write-Host "    Upload it as a Release asset and set its URL as the installer -BundleUrl." -ForegroundColor Gray
} finally {
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
