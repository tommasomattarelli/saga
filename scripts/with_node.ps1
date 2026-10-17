# A param block would consume flags intended for the wrapped command.
$Command = $args[0]
$CommandArguments = @($args | Select-Object -Skip 1)
$ErrorActionPreference = "Stop"
$AppDir = Split-Path $PSScriptRoot -Parent
$InstallRoot = if ($env:SAGA_INSTALL_ROOT) {
  $env:SAGA_INSTALL_ROOT
} else {
  Join-Path $env:LOCALAPPDATA "SAGA"
}

. (Join-Path $AppDir "install\windows\ensure_node.ps1") -AppDir $AppDir -InstallRoot $InstallRoot
& $Command @CommandArguments
exit $LASTEXITCODE
