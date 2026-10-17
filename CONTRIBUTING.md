# Contributing to SAGA

SAGA is an alpha. The most useful thing you can do is **play it and report what broke** —
bug reports from real sessions are worth more than patches right now.

## Reporting

- **Bugs and user-visible asks** → [open an issue](https://github.com/tommasomattarelli/saga/issues/new/choose).
  The forms ask for four things only: version, how you installed it and which AI provider,
  what happened, and how to reproduce. Don't worry about the title format or labels — those
  are set at triage.
- **Ideas, questions, "would it be possible to…"** → [Discussions](https://github.com/tommasomattarelli/saga/discussions).
- **Security issues** → do not open a public issue. Use GitHub's private vulnerability
  reporting (**Security** tab → *Report a vulnerability*).

Design directions and refactors live in [`TODO.md`](TODO.md) for now, not in the issue tracker —
check there before proposing one, it may already be planned.

## Setting up

Use the runtime patches in [`backend/.python-version`](backend/.python-version) and
[`frontend/.node-version`](frontend/.node-version). `uv` provisions Python automatically;
install/select the pinned Node with your version manager first. Python is limited to
3.12 and Node to 24 LTS, matching the supported lines in CI, Docker and the installers.

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga

# backend
cd backend && uv sync --locked && cp ../.env.example .env
# point DATABASE_URL at your local Postgres, generate the two secrets:
#   openssl rand -hex 32
uv run --locked alembic upgrade head

# frontend
cd ../frontend && npm ci
```

You need PostgreSQL 16 with pgvector. `make test-infra-up` starts a throwaway one in
Docker for the integration tests.

Install the git hooks once — they run format, lint, unit tests and the commit-message
check locally, so you find out before CI does:

```bash
pre-commit install
```

## Running the checks

```bash
# backend
cd backend
uv run --locked ruff check . && uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked vulture app --min-confidence 80
uv run --locked python -m pytest tests/unit --noconftest -q
make -C .. test-infra-up
uv run --locked python -m pytest tests/integration tests/playtest

# frontend
cd ../frontend
npm run lint
npx prettier --check "src/**/*.{ts,tsx,json,css}"
npx tsc --noEmit
npm run knip
npm run test:coverage -- --run
npm run build
```

CI runs these checks on every pull request, plus Docker builds, installer syntax
checks and cross-platform Node provisioning tests. To run provisioning tests locally,
select the pinned Node and run from the repository root:

```bash
cd backend
uv run --locked python -m pytest ../install/tests --noconftest -q
```

These download real Node archives and need internet access. Full native installer
smoke is manual/scheduled.

## House rules

The full working agreement — engineering standards, session protocol, architecture
constraints — is in [`CLAUDE.md`](CLAUDE.md). The short version:

- **Tests first.** Integration tests hit a real PostgreSQL; core flows are not mocked.
- **Types are mandatory.** Python type hints, TypeScript interfaces, no `any`.
- **Async everywhere** for I/O — database, AI calls, HTTP.
- **Comment the *why*, never the *what*.** The code says what it does.
- **Thin API handlers.** Logic in services, schema in models.
- **No file over ~300 lines**, no file mixing responsibilities.
- **New tunable behaviour goes in `saga.config.yaml`**, never hardcoded.
- **Never hold a database session across an LLM call.** Read, close, call, reopen, write.
- **All model calls go through `ai/router.py`** so cost and importance stay in one place.

## Commits and branches

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) with a
**mandatory scope**:

```
type(scope): subject
```

`type` is one of `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`, `ci`.
`scope` is the area touched (`api`, `core`, `dm`, `combat`, `memory`, `ai`, `auth`,
`config`, `frontend`, `docs`, …). Subject in imperative mood, lowercase, no trailing
period. When a commit closes an issue, name it: `fix(dm): stop the npc resolver looping (#42)`.

- **One logical change per commit.** A feature lands as a *series* of small commits, not
  one large one — the branch exists to hold the series.
- **A branch is one reviewable unit of work**, not one issue. Related issues share a branch
  and close together.
- Branch off `main` as `feat/*` or `fix/*`. Pull requests are merged with a **merge
  commit** — the series is the point, so nothing is squashed.
- **No co-author or tool-attribution trailers.** Plain messages.

## What ships with a change

- A [`CHANGELOG.md`](CHANGELOG.md) entry under `[Unreleased]`, in the same commit —
  `### Highlights` if a player would notice, `### Internal` otherwise.
- An ADR in [`docs/adr/`](docs/adr/), in the same commit, for any architectural decision.
  ADRs are append-only: never edit an accepted one, write a new one that supersedes it.
- `Closes #NN` in the pull request body for every issue it closes.

## License

By contributing you agree that your contributions are licensed under the
[AGPL-3.0](LICENSE), like the rest of the project.
