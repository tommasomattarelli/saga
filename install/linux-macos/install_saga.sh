#!/usr/bin/env bash
# SAGA native (no-Docker) installer for Linux/macOS.
# Mirror of install_saga.ps1. Postgres+pgvector come from the OS package manager
# (the Windows portable-bundle trick is Windows-specific); everything else matches.
set -euo pipefail

# initdb/pg_ctl refuse to run as root; fail fast before touching the system.
if [ "$(id -u)" = "0" ]; then
  echo "Do not run this installer as root. It uses sudo only for the Postgres package."
  echo "Re-run as your normal user: bash install/linux-macos/install_saga.sh"
  exit 1
fi

FROM_LOCAL="${SAGA_FROM_LOCAL:-0}"
PG_PORT="${SAGA_PG_PORT:-54320}"
APP_PORT="${SAGA_APP_PORT:-8000}"
NODE_VERSION="${SAGA_NODE_VERSION:-20.18.1}"
NO_LAUNCH="${SAGA_NO_LAUNCH:-0}"
REPO="https://github.com/tommasomattarelli/saga.git"
# Release the installer checks out. Bumped per release. Override with SAGA_REF.
REF="${SAGA_REF:-v0.1.0-beta.3}"

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '[OK] %s\n' "$1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${SAGA_INSTALL_ROOT:-$HOME/.local/share/saga}"
if [ "$FROM_LOCAL" = "1" ]; then
  APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
  APP_DIR="$INSTALL_ROOT/app"
  if [ ! -d "$APP_DIR/.git" ]; then
    step "Cloning SAGA $REF into $APP_DIR"
    git clone --branch "$REF" "$REPO" "$APP_DIR"
  else
    step "Updating SAGA to $REF"
    git -C "$APP_DIR" fetch --tags origin
    git -C "$APP_DIR" checkout "$REF"
  fi
fi
[ -d "$APP_DIR/backend" ] || { echo "SAGA app not found at $APP_DIR"; exit 1; }

mkdir -p "$INSTALL_ROOT"
PGDATA="$INSTALL_ROOT/pgdata"
OS="$(uname -s)"

# --- uv ---------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  step "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv: $(uv --version)"

# --- node (portable tarball) ------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  case "$OS" in
    Linux)  NODE_PLAT="linux-x64"; NODE_EXT="tar.xz" ;;
    Darwin) NODE_PLAT="darwin-$([ "$(uname -m)" = arm64 ] && echo arm64 || echo x64)"; NODE_EXT="tar.gz" ;;
    *) echo "Unsupported OS: $OS"; exit 1 ;;
  esac
  NODE_DIR="$INSTALL_ROOT/node/node-v$NODE_VERSION-$NODE_PLAT"
  if [ ! -x "$NODE_DIR/bin/node" ]; then
    step "Downloading portable Node.js $NODE_VERSION..."
    mkdir -p "$INSTALL_ROOT/node"
    curl -L "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-$NODE_PLAT.$NODE_EXT" \
      -o "$INSTALL_ROOT/node/node.tar"
    tar -xf "$INSTALL_ROOT/node/node.tar" -C "$INSTALL_ROOT/node"
    rm -f "$INSTALL_ROOT/node/node.tar"
  fi
  export PATH="$NODE_DIR/bin:$PATH"
fi
ok "node: $(node --version)"

# --- Postgres + pgvector (OS package manager) -------------------------------
find_pg_bin() {
  for d in \
    "$(command -v pg_ctl 2>/dev/null | xargs -r dirname)" \
    /usr/lib/postgresql/16/bin \
    "$(brew --prefix postgresql@16 2>/dev/null)/bin"; do
    [ -n "$d" ] && [ -x "$d/initdb" ] && { echo "$d"; return; }
  done
}
# Install both unconditionally (idempotent): pgvector is a separate package and
# may be missing even when Postgres itself is already present.
step "Ensuring Postgres 16 + pgvector..."
if command -v brew >/dev/null 2>&1; then
  brew install postgresql@16 pgvector
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y postgresql-16 postgresql-16-pgvector
else
  echo "No supported package manager (brew/apt). Install Postgres 16 + pgvector manually."; exit 1
fi
PG_BIN="$(find_pg_bin)"
[ -n "${PG_BIN:-}" ] || { echo "Postgres binaries not found after install."; exit 1; }
ok "Postgres binaries: $PG_BIN"

# --- init cluster (once) ----------------------------------------------------
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  step "Initialising database cluster..."
  "$PG_BIN/initdb" -D "$PGDATA" -U saga -E UTF8 --auth=trust >/dev/null
  # -k /tmp: the default unix_socket dir (/var/run/postgresql) is not writable by
  # a non-root user on CI/most boxes; createdb/psql then connect over TCP.
  "$PG_BIN/pg_ctl" -D "$PGDATA" -o "-p $PG_PORT -k /tmp" -l "$INSTALL_ROOT/pg-init.log" -w start
  trap '"$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop >/dev/null 2>&1 || true' EXIT
  "$PG_BIN/createdb" -h localhost -p "$PG_PORT" -U saga saga
  "$PG_BIN/psql" -h localhost -p "$PG_PORT" -U saga -d saga -c "CREATE EXTENSION IF NOT EXISTS vector;"
  "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop
  trap - EXIT
  ok "Database initialised"
else
  ok "Database cluster already initialised"
fi

# --- backend/.env -----------------------------------------------------------
ENV_FILE="$APP_DIR/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  step "Writing configuration..."
  JWT="$(openssl rand -base64 32)"
  ENC="$(openssl rand -base64 32)"
  sed -e "s#^DATABASE_URL=.*#DATABASE_URL=postgresql+asyncpg://saga:saga@localhost:$PG_PORT/saga#" \
      -e "s#^JWT_SECRET=.*#JWT_SECRET=$JWT#" \
      -e "s#^API_KEY_ENCRYPTION_KEY=.*#API_KEY_ENCRYPTION_KEY=$ENC#" \
      "$APP_DIR/.env.example" > "$ENV_FILE"
  {
    echo "SAGA_ENVIRONMENT=prod"
    echo "SAGA_FRONTEND_DIST=$APP_DIR/frontend/dist"
  } >> "$ENV_FILE"
  ok "Created backend/.env with generated secrets"
fi

# --- build ------------------------------------------------------------------
step "Installing backend dependencies..."
( cd "$APP_DIR/backend" && uv sync --no-dev )
step "Building frontend..."
( cd "$APP_DIR/frontend" && npm ci --legacy-peer-deps && npm run build )
ok "Build complete"

ok "Installation complete. Start SAGA with: install/start_saga.sh"
if [ "$NO_LAUNCH" != "1" ]; then
  SAGA_PG_PORT="$PG_PORT" SAGA_APP_PORT="$APP_PORT" "$APP_DIR/install/linux-macos/start_saga.sh"
fi
