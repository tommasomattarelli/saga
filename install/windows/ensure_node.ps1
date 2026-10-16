param(
  [string]$AppDir,
  [string]$InstallRoot
)

$NodeVersion = (Get-Content (Join-Path $AppDir "frontend\.node-version") -Raw).Trim()
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or (node --version) -ne "v$NodeVersion") {
  $nodeBin = Join-Path $InstallRoot "node\node-v$NodeVersion-win-x64"
  if (-not (Test-Path (Join-Path $nodeBin "node.exe"))) {
    Write-Host "Downloading portable Node.js $NodeVersion..."
    $nodeZip = Join-Path $env:TEMP "saga-node.zip"
    Invoke-WebRequest -Uri "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip" -OutFile $nodeZip
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot "node") | Out-Null
    Expand-Archive -Path $nodeZip -DestinationPath (Join-Path $InstallRoot "node") -Force
    Remove-Item $nodeZip -Force
  }
  $env:Path = "$nodeBin;$env:Path"
}

if ((node --version) -ne "v$NodeVersion") {
  throw "Node provisioning failed: expected v$NodeVersion."
}
