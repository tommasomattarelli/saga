<#
.SYNOPSIS
  SAGA native (no-Docker) installer for Windows - provisioning stage.

.DESCRIPTION
  Run by install_saga.bat after the repo is cloned, or directly with -FromLocal
  against a checkout (CI / dev). Installs uv + node if missing, provisions a
  portable Postgres+pgvector bundle, initialises the database, writes backend/.env
  with generated secrets, builds backend and frontend, and creates a launcher
  shortcut. Backend logic is untouched (see docs/adr/0000).

.NOTES
  No admin required. Postgres is on-demand (started/stopped by start_saga.ps1).
#>
[CmdletBinding()]
param(
  # Use the current checkout instead of %LOCALAPPDATA%\SAGA\app (CI / dev testing).
  [switch]$FromLocal,
  # Pinned Postgres+pgvector bundle (zip of a `pgsql` dir), published as a Release asset.
  # $env:SAGA_BUNDLE_URL overrides; otherwise the published default below.
  [string]$BundleUrl = $(if ($env:SAGA_BUNDLE_URL) { $env:SAGA_BUNDLE_URL } else { "https://github.com/tommasomattarelli/saga/releases/download/bundle-pg16-v1/saga-pg-bundle-pg16.zip" }),
  [int]$PgPort = 54320,
  [int]$AppPort = 8000,
  # Pinned portable Node.js LTS (downloaded from nodejs.org, no admin).
  [string]$NodeVersion = "20.18.1",
  # Skip launching the app at the end (CI smoke).
  [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }

function Test-Tool($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

# 256-bit cryptographically-random secret, base64 (standard 16 - never ship change-me).
function New-Secret {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes)
}

# --- Resolve install layout -------------------------------------------------
$AppDir = if ($FromLocal) {
  (Resolve-Path "$PSScriptRoot\..\..").Path
} else {
  Join-Path $env:LOCALAPPDATA "SAGA\app"
}
if (-not (Test-Path (Join-Path $AppDir "backend"))) {
  throw "SAGA app directory not found at '$AppDir'. Run install_saga.bat (it clones the repo) or pass -FromLocal from a checkout."
}
$InstallRoot = Split-Path $AppDir -Parent
$PgDir   = Join-Path $InstallRoot "pg"       # extracted bundle (pgsql binaries)
$PgData  = Join-Path $InstallRoot "pgdata"   # database cluster
$PgBin   = Join-Path $PgDir "pgsql\bin"

Write-Step "Installing SAGA into $InstallRoot"

# --- Ensure uv (user-scope, no admin) ---------------------------------------
if (-not (Test-Tool "uv")) {
  Write-Step "Installing uv (user-scope, no admin)..."
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Test-Tool "uv")) { throw "uv install failed. Close this window and re-run install_saga.bat." }
Write-Ok "uv: $(uv --version)"

# --- Ensure node (portable zip, no admin) -----------------------------------
if (-not (Test-Tool "node")) {
  $nodeBin = Join-Path $InstallRoot "node\node-v$NodeVersion-win-x64"
  if (-not (Test-Path (Join-Path $nodeBin "node.exe"))) {
    Write-Step "Downloading portable Node.js $NodeVersion (no admin)..."
    $nodeZip = Join-Path $env:TEMP "node.zip"
    Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip" -OutFile $nodeZip
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "node") | Out-Null
    Expand-Archive -Path $nodeZip -DestinationPath (Join-Path $InstallRoot "node") -Force
    Remove-Item $nodeZip -Force
  }
  $env:Path = "$nodeBin;$env:Path"
}
if (-not (Test-Tool "node")) { throw "Node provisioning failed." }
Write-Ok "node: $(node --version)"

# --- Provision Postgres + pgvector bundle -----------------------------------
if (-not (Test-Path $PgBin)) {
  if (-not $BundleUrl) {
    throw "No Postgres bundle URL. Set -BundleUrl or `$env:SAGA_BUNDLE_URL to the published bundle (see install/README.md)."
  }
  Write-Step "Fetching Postgres+pgvector bundle..."
  $zip = Join-Path $env:TEMP "saga-pg-bundle.zip"
  # $BundleUrl may be a URL (public repo) or a local file (CI pre-downloads the
  # asset with gh, since a private repo's Release 404s for unauthenticated GETs).
  if (Test-Path $BundleUrl) { Copy-Item -LiteralPath $BundleUrl -Destination $zip -Force }
  else { Invoke-WebRequest -Uri $BundleUrl -OutFile $zip }
  Write-Step "Unpacking bundle..."
  New-Item -ItemType Directory -Force -Path $PgDir | Out-Null
  Expand-Archive -Path $zip -DestinationPath $PgDir -Force
  Remove-Item $zip -Force
}
if (-not (Test-Path (Join-Path $PgBin "initdb.exe"))) {
  throw "Postgres binaries not found under $PgBin after unpacking - check the bundle layout (expects pgsql\bin)."
}
Write-Ok "Postgres binaries ready"

# --- Initialise the cluster (once) ------------------------------------------
if (-not (Test-Path (Join-Path $PgData "PG_VERSION"))) {
  Write-Step "Initialising database cluster..."
  & (Join-Path $PgBin "initdb.exe") -D $PgData -U saga -E UTF8 --auth=trust | Out-Null
  Write-Step "Starting Postgres to create the database..."
  & (Join-Path $PgBin "pg_ctl.exe") -D $PgData -o "-p $PgPort" -l (Join-Path $InstallRoot "pg-init.log") -w start
  try {
    & (Join-Path $PgBin "createdb.exe") -p $PgPort -U saga saga
    & (Join-Path $PgBin "psql.exe") -p $PgPort -U saga -d saga -c "CREATE EXTENSION IF NOT EXISTS vector;"
  } finally {
    & (Join-Path $PgBin "pg_ctl.exe") -D $PgData -m fast -w stop
  }
  Write-Ok "Database initialised (role 'saga', db 'saga', extension 'vector')"
} else {
  Write-Ok "Database cluster already initialised"
}

# --- Write backend/.env -----------------------------------------------------
Write-Step "Writing configuration..."
$envPath = Join-Path $AppDir "backend\.env"
if (-not (Test-Path $envPath)) {
  $lines = Get-Content (Join-Path $AppDir ".env.example")
  $lines = $lines -replace '^DATABASE_URL=.*', "DATABASE_URL=postgresql+asyncpg://saga:saga@localhost:$PgPort/saga"
  $lines = $lines -replace '^JWT_SECRET=.*', "JWT_SECRET=$(New-Secret)"
  $lines = $lines -replace '^API_KEY_ENCRYPTION_KEY=.*', "API_KEY_ENCRYPTION_KEY=$(New-Secret)"
  # Forward slashes: dotenv reads the value literally and pathlib accepts them;
  # a backslash path risks silent escape mangling -> blank page, no error.
  $dist = (Join-Path $AppDir "frontend\dist").Replace('\', '/')
  $lines += "SAGA_ENVIRONMENT=prod"
  $lines += "SAGA_FRONTEND_DIST=$dist"
  # UTF-8 without BOM: a BOM would corrupt the first key (the DATABASE_URL line).
  [System.IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding $false))
  Write-Ok "Created backend/.env with generated secrets"
} else {
  Write-Ok "backend/.env already exists - left untouched"
}

# --- Build backend + frontend ----------------------------------------------
Write-Step "Installing backend dependencies (uv sync)..."
Push-Location (Join-Path $AppDir "backend")
try { uv sync --no-dev } finally { Pop-Location }

Write-Step "Building frontend (npm ci + build)..."
Push-Location (Join-Path $AppDir "frontend")
try {
  npm ci --legacy-peer-deps
  npm run build
} finally { Pop-Location }
Write-Ok "Build complete"

# --- Desktop shortcut -------------------------------------------------------
Write-Step "Creating desktop shortcut..."
$shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "SAGA.lnk"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($shortcut)
$lnk.TargetPath = "powershell.exe"
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $AppDir 'install\windows\start_saga.ps1')`""
$lnk.WorkingDirectory = $AppDir
$lnk.Description = "Launch SAGA"
$ico = Join-Path $AppDir "install\windows\saga.ico"
if (Test-Path $ico) { $lnk.IconLocation = $ico }
$lnk.Save()
Write-Ok "Desktop shortcut 'SAGA' created"

Write-Host ""
Write-Ok "Installation complete. Launch SAGA from the desktop shortcut."
Write-Host "    The app opens at http://localhost:$AppPort" -ForegroundColor Gray

if (-not $NoLaunch) {
  & (Join-Path $AppDir "install\windows\start_saga.ps1") -PgPort $PgPort -AppPort $AppPort
}
