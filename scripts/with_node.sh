#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    exec powershell.exe -NoProfile -ExecutionPolicy Bypass \
      -File "$(cygpath -w "$APP_DIR/scripts/with_node.ps1")" "$@"
    ;;
esac

INSTALL_ROOT="${SAGA_INSTALL_ROOT:-$HOME/.local/share/saga}"
source "$APP_DIR/install/linux-macos/ensure_node.sh"
exec "$@"
