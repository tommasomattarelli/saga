#!/usr/bin/env bash
# Remove a SAGA native install: stop Postgres and delete the install root
# ($HOME/.local/share/saga by default). Game data is deleted - export first.
set -euo pipefail

INSTALL_ROOT="${SAGA_INSTALL_ROOT:-$HOME/.local/share/saga}"
PGDATA="$INSTALL_ROOT/pgdata"

find_pg_bin() {
  for d in \
    "$(command -v pg_ctl 2>/dev/null | xargs -r dirname)" \
    /usr/lib/postgresql/16/bin \
    "$(brew --prefix postgresql@16 2>/dev/null)/bin"; do
    [ -n "$d" ] && [ -x "$d/pg_ctl" ] && { echo "$d"; return; }
  done
}

if [ "${1:-}" != "--yes" ]; then
  read -r -p "This deletes $INSTALL_ROOT including all game data. Type 'yes': " ans
  [ "$ans" = "yes" ] || { echo "Aborted."; exit 0; }
fi

PG_BIN="$(find_pg_bin || true)"
if [ -n "${PG_BIN:-}" ] && [ -d "$PGDATA" ]; then
  "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true
fi
rm -rf "$INSTALL_ROOT"
echo "SAGA removed."
