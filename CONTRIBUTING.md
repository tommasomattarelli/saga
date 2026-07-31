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

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga

# backend
cd backend && uv sync && cp ../.env.example .env
# point DATABASE_URL at your local Postgres, generate the two secrets:
#   openssl rand -hex 32
alembic upgrade head

# frontend
cd ../frontend && npm install
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
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python -m pytest tests/unit --noconftest -q      # no infrastructure needed
make test-infra-up && uv run python -m pytest tests/integration

# frontend
cd frontend && npm run lint && npm run test
```

CI runs the same set on every pull request.

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
