# ADR 0000 — Distribution & deployment architecture

- **Status**: Accepted
- **Date**: 2026-06-16
- **Context items**: TODO "infra / distribuzione" (installer `.bat`/`.sh`), "roadmap / release" (CI)

> This is the foundational deployment decision — the first fully-implemented ADR,
> preceding the first public release. ADRs 0001–0011 record earlier or
> still-proposed decisions; this one fixes how SAGA is actually shipped and run.

## Context

SAGA must reach two very different audiences:

1. **Technical users** — comfortable with Docker. They clone the repo and run
   `docker compose up --build`. This path already exists (`docker-compose.yml`)
   and needs no installer wrapper.
2. **Casual users** — non-technical, want "download, double-click, play". This is
   the path that does not exist yet.

The hard constraint is the database. SAGA depends on **PostgreSQL 16 + pgvector**:
`models/turn.py` and `models/memory_fact.py` declare `embedding: Vector(384)`
(`pgvector.sqlalchemy.Vector`); `memory/semantic.py` runs
`MemoryFact.embedding.cosine_distance(...)` (the pgvector `<=>` operator) — this
*is* semantic recall; and five models use `JSONB`/`UUID` from the Postgres
dialect. Semantic memory is a core product pillar (Engineering Standard 5,
"Database First").

Comparison with the reference engine (NeverEndingQuest): its casual installer is
trivial *because it has no database* (flat JSON files). SAGA is the inverse — the
casual/no-Docker tier is the **hardest** path to make reliable, precisely because
pgvector has no official Windows binary (it requires either an MSVC build or a
community-precompiled artifact).

A non-negotiable goal: **the casual path must not change backend logic.** The
backend already reads `DATABASE_URL` and runs `Base.metadata.create_all` +
`seed_templates()` on lifespan startup (`dependencies.py:init_db`), identically
whether Postgres runs in a container or natively on `localhost`.

## Decision

### 1. Two-tier distribution

- **Technical tier** — unchanged: documented `docker compose up --build`. No
  installer is shipped for it (a Docker user does not need one).
- **Casual tier** — a native, no-Docker installer (Windows `.bat` first, then a
  POSIX `.sh`).

### 2. Database: portable Postgres + pgvector bundle

The casual installer provisions Postgres natively rather than dropping pgvector:

- A **pinned, precompiled Postgres+pgvector bundle** (Postgres "binaries-only"
  distribution + a matching precompiled `vector` extension) is assembled once and
  published as a **GitHub Release asset**. The installer downloads it from a
  **configurable URL** (so the wiring exists before the asset is published, and
  the asset can be re-pointed without code changes).
- The installer runs `initdb` into a data directory, creates the role/database,
  and runs `CREATE EXTENSION vector` **before** the backend first boots — otherwise
  `create_all` fails on the `vector(384)` columns. (In the Docker path this is
  done by `init.sql` mounted into the entrypoint; the native path replicates that
  one statement.)
- The bundled instance listens on a **non-default port** (e.g. `54320`) to avoid
  colliding with any pre-existing Postgres. `.env`'s `DATABASE_URL` points at it.

### 3. Frontend served by FastAPI

In production (casual) the built frontend (`npm run build` → `dist/`) is served by
**FastAPI via a guarded `StaticFiles` mount** (with an SPA catch-all for
react-router), not by a second Node process. This yields **one process, one port,
no runtime Node dependency, and no CORS**. The mount is guarded (only active when
`dist/` is present) so dev and Docker — which use the Vite dev server — are
untouched. This is the only backend change introduced by this ADR: ~a few additive
lines in `app/main.py`, no game logic.

### 4. Bootstrapper installer

`install_saga.bat` is a small bootstrapper, delivered as a single
download-and-run file (a `irm | iex` one-liner is documented as a power-user
alternative). It:

1. checks/installs **git** (winget), **uv**, **node** (winget); handles the
   post-winget PATH refresh (re-launch shell);
2. clones the repo to `%LOCALAPPDATA%\SAGA\app` (data lives beside it in
   `%LOCALAPPDATA%\SAGA\pgdata`, outside the git clone);
3. downloads + unpacks the Postgres bundle, `initdb`,
   `CREATE EXTENSION vector`;
4. copies `.env.example` → `.env`, **auto-generates** `JWT_SECRET` and
   `API_KEY_ENCRYPTION_KEY` (Engineering Standard 16 — never ship `change-me`),
   sets `DATABASE_URL`;
5. `uv sync --no-dev` (uv also provisions the required Python),
   `npm ci --legacy-peer-deps`, `npm run build`;
6. creates a desktop shortcut and opens the browser.

A `SAGA_INSTALL_FROM_LOCAL` mode skips the clone and uses the current checkout, so
the installer is testable in CI and locally without re-cloning.

The installer **does not** prompt for AI provider keys: keys are entered later via
the UI (BYOAK, AES-256 at rest). The installer only stands up the stack.

### 5. Runtime lifecycle: on-demand, a single coupled launcher

Postgres is **not** a Windows service and runtime needs **no admin**. A single
desktop shortcut **"SAGA"** runs one launcher that couples both processes:
`pg_ctl start` → uvicorn in the foreground (serving API + `dist/`) → on uvicorn
exit, `pg_ctl stop`. So opening "SAGA" starts the database and the app together,
and **closing the window (or Ctrl+C) stops both** — no separate stop script, and
nothing left running in the background between sessions.

Stop is reliable on Ctrl+C. On a hard window close Windows grants only ~5s before
killing the process, so a graceful `pg_ctl stop -m fast` is best-effort there —
but Postgres is crash-safe (WAL), so data is never at risk. The launcher is a
small PowerShell wrapper (`try/finally`) rather than a bare `.bat`, to make the
coupled teardown as reliable as Windows allows. An `uninstall_saga` script removes
`%LOCALAPPDATA%\SAGA`.

The desktop shortcut (`.lnk`) carries a custom SAGA icon, so the user sees a
branded launcher, not a `.bat`. Wrapping the downloaded bootstrapper itself as a
`.exe` with an embedded icon is possible but deferred: it still triggers
SmartScreen/AV warnings without paid code signing.

### 6. CI validates both paths

CI (`.github/workflows/`) runs on PR + push to `main`: ruff, backend unit, backend
integration against a `pgvector/pgvector:pg16` service container, the full
frontend pipeline, and a Docker build-smoke. No AI keys are needed — every LLM
call on the test path is mocked. The installer is lint-checked on every PR and
smoke-tested on a scheduled `windows-latest` job (the realistic clean-machine
proxy). CD (publishing images) is deferred until a stable release.

## Rejected alternatives

- **SQLite for the casual tier.** Superficially attractive (bundled with Python,
  no DB install) but it would fork the backend: replace `Vector(384)` and
  `cosine_distance` (rewriting `semantic.py`), swap every `JSONB`/`UUID` Postgres
  type, change the driver (`asyncpg` → `aiosqlite`), and maintain a second DB
  dialect forever — violating Engineering Standards 1 and 5 and degrading the
  semantic-memory pillar *for the very users we are trying to help*. Vector search
  on SQLite (`sqlite-vec`) is itself a native C extension, so it does not even
  remove the "native binary on Windows" problem — it just moves it while also
  forking the backend. Rejected.
- **An installer for the Docker tier.** A Docker user can run
  `docker compose up --build`; a wrapper adds nothing.
- **Postgres as an always-on Windows service.** Considered (admin-at-install was
  acceptable), but it leaves the database running in the background between
  sessions and decouples its lifecycle from the app. Rejected in favour of the
  coupled on-demand launcher (§5), which starts and stops Postgres together with
  uvicorn and needs no admin.
- **CD / image publishing now.** Deferred to a stable release.

## Consequences

- **Positive**: backend logic is unchanged (one guarded `StaticFiles` mount aside);
  the casual user gets the *real* product, semantic memory included; the same
  codebase runs in dev, Docker, CI, and casual installs; complexity is quarantined
  in the installer and a pinned bundle, not smeared across the backend.
- **Trade-off**: the casual dependency surface is large (git + uv + node + native
  Postgres + pgvector) — many more failure points than NeverEndingQuest's
  git + Python. The scheduled Windows CI smoke job is the mitigation.
- **Trade-off**: we maintain the Postgres+pgvector bundle across version bumps,
  and host it as a Release asset.
- **Trade-off**: graceful Postgres shutdown on a hard window close is best-effort
  (Windows' ~5s grace); mitigated by Postgres being crash-safe and by the
  PowerShell `try/finally` launcher. Ctrl+C is always clean.

## Notes

- `init.sql` is a single statement, `CREATE EXTENSION IF NOT EXISTS vector;` — the
  exact SQL the native path replicates before first boot.
- The bundle asset does not exist yet; the installer consumes it from a
  configurable URL, and an explicit binary manifest will be prepared for whoever
  assembles and uploads the Release.
- The `.sh` (Linux/macOS) installer follows once the `.bat` is solid.
