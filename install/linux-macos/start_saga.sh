#!/usr/bin/env bash
# Launch SAGA on Linux/macOS: start Postgres, run the backend (API + built SPA),
# open the browser, stop Postgres on exit. Mirror of start_saga.ps1.
set -euo pipefail

# pg_ctl refuses to run as root; mirror the installer's guard.
if [ "$(id -u)" = "0" ]; then
  echo "Do not run SAGA as root. Re-run as your normal user: bash install/start_saga.sh"
  exit 1
fi

PG_PORT="${SAGA_PG_PORT:-54320}"
APP_PORT="${SAGA_APP_PORT:-8000}"
export PATH="$HOME/.local/bin:$PATH"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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
PG_BIN="$(find_pg_bin)"
[ -n "$PG_BIN" ] || { echo "Postgres not found. Run install_saga.sh first."; exit 1; }

open_url() { command -v xdg-open >/dev/null 2>&1 && xdg-open "$1" || (command -v open >/dev/null 2>&1 && open "$1"); }

echo "Starting Postgres..."
# -k /tmp: writable unix_socket dir; backend connects over TCP (localhost) anyway.
"$PG_BIN/pg_ctl" -D "$PGDATA" -o "-p $PG_PORT -k /tmp" -l "$INSTALL_ROOT/pg.log" -w start
trap '"$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true' EXIT

# Open the browser once the app answers (uvicorn blocks below).
(
  for _ in $(seq 1 60); do
    if curl -fsS "http://localhost:$APP_PORT" >/dev/null 2>&1; then open_url "http://localhost:$APP_PORT"; break; fi
    sleep 1
  done
) &

echo "SAGA at http://localhost:$APP_PORT  (Ctrl+C to stop)"
( cd "$APP_DIR/backend" && uv run uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" )
