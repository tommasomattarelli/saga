# SAGA installer (no Docker)

For **casual users** who want to run SAGA without Docker. Technical users should
just `docker compose up --build` (see the root README). Rationale and the full
design are in [`docs/adr/0000-distribution-and-deployment-architecture.md`](../docs/adr/0000-distribution-and-deployment-architecture.md).

Per-platform scripts live in `windows/` and `linux-macos/`; the maintainer bundle
recipe (`build_bundle.ps1`) stays at the `install/` root.

## For players (Windows)

1. Download **`windows/install_saga.bat`** and double-click it.
2. It installs Git (if missing), clones SAGA into `%LOCALAPPDATA%\SAGA\app`, then
   installs uv + Node, provisions a portable Postgres+pgvector, builds the app,
   and creates a **SAGA** desktop shortcut.
3. From then on: double-click **SAGA** to play. Closing the window (or Ctrl+C)
   stops everything — Postgres starts and stops together with the app.

The app opens at `http://localhost:8000`. The installer never asks for an AI provider key:
add it yourself to `%LOCALAPPDATA%\SAGA\app\backend\.env` (created with the other secrets
already generated) and restart.

Requirements: Windows 10/11, an internet connection on first run, ~3–4 GB free.
No admin rights needed. To remove everything, run `windows\uninstall_saga.ps1`.

## For players (Linux/macOS)

Run `linux-macos/install_saga.sh`. It provisions uv + Node and installs
Postgres 16 + pgvector via the OS package manager (brew on macOS, apt on Debian/
Ubuntu), then builds and launches via `linux-macos/start_saga.sh`. The provider key
goes in `~/.local/share/saga/app/backend/.env`, same as on Windows.

## Files

| File | Role |
|---|---|
| `windows/install_saga.bat` | Downloadable bootstrapper: ensures Git, clones, hands off to the `.ps1`. |
| `windows/install_saga.ps1` | Provisioning: uv/Node, Postgres bundle, DB init, `.env`, build, shortcut. Use `-FromLocal` to run against a checkout (CI/dev). |
| `windows/start_saga.ps1` | Launcher: starts Postgres → runs the backend (serves API + frontend) → stops Postgres on exit. |
| `windows/uninstall_saga.ps1` | Stops Postgres and removes `%LOCALAPPDATA%\SAGA`. |
| `linux-macos/*.sh` | The same three scripts for Linux/macOS. |
| `build_bundle.ps1` | Maintainer-only: assembles the Postgres+pgvector bundle zip. |

## For maintainers — the Postgres+pgvector bundle

The installer downloads a pinned bundle from `-BundleUrl` (or `$env:SAGA_BUNDLE_URL`).
Assemble and publish it once per Postgres/pgvector bump:

```powershell
install\build_bundle.ps1 `
  -PgBinaries "<EDB Postgres 16.x binaries-only zip — URL or local path>" `
  -Pgvector "<precompiled pgvector for PG 16 — URL or local path>" `
  -OutZip saga-pg-bundle-pg16.zip
```

Then upload `saga-pg-bundle-pg16.zip` as a GitHub Release asset and use its URL.
**At the same release**, bump `REF` in `windows/install_saga.bat` and
`linux-macos/install_saga.sh` to the new tag — the installer checks out that ref
(casual users get the published release, not `main`; override with `SAGA_REF`).
Known-good sources (June 2026): PG 16.14 binaries from EDB, pgvector v0.8.2 for
PG16 (`vector.v0.8.2-pg16.zip`).

### Bundle manifest (pinned)

- **Postgres**: 16.x, Windows x64, "binaries only" distribution from EnterpriseDB
  (<https://www.enterprisedb.com/download-postgresql-binaries>).
- **pgvector**: precompiled `vector` extension matching the **same** Postgres major
  (e.g. <https://github.com/andreiramani/pgvector_pgsql_windows> releases). Must
  contain `vector.dll`, `vector.control`, `vector--*.sql`.
- **Layout**: the zip root is a `pgsql\` directory (`bin/`, `lib/`, `share/`) with
  `vector.dll` in `lib/` and the control/SQL files in `share\extension\`.

> The exact Postgres patch and pgvector version are pinned at publish time; record
> them in the Release notes so the bundle is reproducible.
