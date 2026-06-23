# SAGA — Project Guide

## Overview
SAGA is an AI-driven tabletop RPG engine designed to replicate the infinite possibilities of D&D. An expert AI Dungeon Master (DM) maintains authority over the world, adjudicating player actions through complex narrative logic and dice-based mechanics.

### Core Pillars
- **Intelligent AI Routing**: Dynamically selects models (custom `ai/router.py`) based on importance (GPT-5/Opus for narrative peaks, Gemini Flash for background world-sim).
- **Semantic Memory**: Uses `pgvector` for "long-term storytelling recall" — the DM remembers thematically relevant past events.
- **Living World**: Full state persistence (JSONB) of world state, factions, and NPC psychology that moves forward independently.
- **Data Sovereignty**: Open-source, self-hostable, with full campaign export/import (JSON).

## Essential Commands
### Backend (uv based)
- **Install**: `cd backend && uv sync`
- **Run**: `cd backend && uv run uvicorn app.main:app --reload`
- **Test (unit, no infra)**: `cd backend && uv run python -m pytest tests/unit --noconftest -q`
- **Test (all)**: `cd backend && uv run python -m pytest tests/unit tests/integration tests/playtest`
- **Lint/Format**: `cd backend && uv run ruff check . && uv run ruff format .`
- **Migrations**: `cd backend && alembic upgrade head`

### Frontend (npm based)
- **Install**: `cd frontend && npm install`
- **Run**: `cd frontend && npm run dev`
- **Test**: `cd frontend && npm run test`
- **Lint/Format**: `cd frontend && npm run lint && npm run format`

### Infrastructure (Docker)
- **Up**: `make test-infra-up` (Test DB) | `docker-compose up -d` (Prod-like)
- **Down**: `make test-infra-down` | `docker-compose down`

## How We Work

Four principles that bias toward caution over speed. For trivial tasks, use judgment.

1. **Think before coding.** State assumptions explicitly. If multiple interpretations exist, surface them — don't pick silently. If a simpler approach exists, say so and push back when warranted. When something is genuinely unclear, stop and ask (use the question tool) *before* writing, not after the mistake.
2. **Simplicity first.** The minimum code that solves the problem, nothing speculative. No features beyond what was asked, no abstractions for single-use code, no unrequested configurability, no error handling for impossible scenarios. If 200 lines could be 50, rewrite. Test: "would a senior engineer call this overcomplicated?"
3. **Surgical changes.** Every changed line must trace to the request. Don't "improve" adjacent code, comments, or formatting; match existing style even if you'd do it differently. Remove only the orphans *your* change created. If you spot pre-existing dead code, mention it — don't delete it unasked.
4. **Verify before "done".** Turn the task into a checkable goal (a failing test made green, a passing suite) and loop until verified. Never claim done without running the check. Consult the `advisor` before substantial or architectural work and at checkpoints — but only when a second opinion genuinely changes the outcome, not as a reflex on trivial tasks.

## Engineering Standards

Non-negotiable technical constraints. Referenced elsewhere by number — keep the numbering stable.

1. **TDD First**: Write failing integration/unit tests before implementation. Use 100% real DB for core flows.
2. **No Verbose Comments**: Code must be self-documenting. Comment ONLY "Why", never "What". No docstrings for internal logic.
3. **Type Safety**: Mandatory Python type hints and TypeScript interfaces. Zero `any` tolerance.
4. **Async Everything**: Non-blocking I/O for DB, AI, and WebSockets.
5. **Database First**: Use real PostgreSQL 16 features (pgvector, JSONB) over mock-heavy unit tests.
6. **Error Handling**: Fail fast, use specific HTTP exceptions, and return structured error JSON.
7. **Clean Architecture**: Services handle logic, Models handle schema, API handlers are thin wrappers.
8. **AI Engine**: All calls must go through `ai/router.py` for cost/importance scoring.
9. **Naming**: snake_case for Python (all files/vars/funcs), camelCase for TS (vars/funcs) and PascalCase for Components/Types.
10. **Commits**: Conventional Commits only (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`). One logical change per commit.
11. **Workflow**: Always `test-infra-up` -> Write failing Integration Test -> Implementation -> Refactor.
12. **No god classes**: No files mixing multiple responsibilities, and no files over ~300 lines.
13. **LLM-readable errors**: Tool error messages must never expose Python stack traces, exception types, or internal paths. Sanitize to a short human-readable sentence before feeding back to the LLM (see `execute_tool` in `dm_tools.py`).
14. **Config-first for new behavior**: Any new gameplay parameter, feature toggle, or AI cost knob goes in `saga.config.yaml` with a sensible default. Never hardcode tunable values in Python.
15. **DB sessions must not span LLM calls**: Open session → read data → close → call LLM → open session → write result. Never hold a DB session open across an LLM invocation.
16. **Validate credentials at startup**: `jwt_secret` and any security credential MUST be validated at startup — a `"change-me"` default is not acceptable in production. Use a Pydantic validator or fail-fast check in `config.py`.
17. **JWT not in query parameters**: JWT tokens must never be passed as query parameters (exposed in logs and browser history). Use `Authorization: Bearer` header or an initial WS handshake.
18. **Auth tokens not in localStorage**: Frontend auth tokens (access + refresh) must not be stored in localStorage (XSS vulnerable). Use httpOnly cookies or a memory-only store.
19. **Hard cap on agent loops**: Every LangGraph coordinator loop MUST have a `max_iterations` hard cap. No open-ended loops.

## Session Protocol

Every working session follows the same ritual so state is never lost between them.

- **Start** (`/catchup`): reconstruct state — skim `CHANGELOG.md` `[Unreleased]` and the `## NOW` items in `TODO.md`. Load the latest ADRs or `docs/AGENTIC_ARCHITECTURE.md` on demand (`/catchup deep`). Confirm the tree is green before changing anything.
- **During**: work on a **feature branch, never commit directly to `main`** — branch at the first commit of the session (`/catchup` already surfaces the current branch at Start; if it's `main`, branch before changing anything). Land work via PR, as the git history does. Then: one commit per logical change (standard 10); add a `CHANGELOG.md` `[Unreleased]` entry in the same commit; any architectural decision → a new ADR in `docs/adr/` in that same commit (docs-as-code).
- **End** (`/wrap-up`): ensure `[Unreleased]` reflects what shipped, move/tick the corresponding `TODO.md` items, and leave the suite green. Run unit + integration/playtest before declaring the session done.

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/) with a **mandatory scope**. Keep messages short.

- **Format**: `type(scope): subject (BACKLOG-ID)` — e.g. `refactor(api): split DB session lifecycle (A-3)`.
- **Type**: one of `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`, `ci`.
- **Scope**: always present — the area touched (`api`, `core`, `dm`, `combat`, `memory`, `ai`, `auth`, `config`, `frontend`, `docs`, …).
- **Subject**: imperative mood, lowercase, no trailing period, ~50 chars.
- **Backlog ID**: when a commit closes an `AUDIT` item, suffix it in parens — `(A-3)`, `(B-M11)`, `(F-L10)`.
- **Body**: only when the *why* isn't obvious from the subject — 1–3 short lines. Substantial rationale goes in an ADR, not the commit body.
- **Never** add co-author trailers (`Co-Authored-By`, tool attribution, etc.). Plain messages only.
- One logical change per commit (standard 10).

## Versioning & Releases

[SemVer](https://semver.org), still pre-1.0 (schema/API churns freely until `1.0.0`).

- **Tags**: `v`-prefixed, on `main` only — `v0.2.5`, pre-releases `v0.2.5-beta.1` / `-rc.1` (mark them "pre-release" on GitHub).
- **0.x bumps**: features *and* breaking changes → **minor** (`0.2`→`0.3`); bug fixes → **patch** (`0.2.5`→`0.2.6`).
- **Branching**: GitHub Flow — short-lived `feat/*`/`fix/*` off `main`, squash-merge via PR. No long-lived `develop`/release branches; a release is a **tag on `main` after merge**, not a branch.
- **Release**: promote `[Unreleased]` → `[vX.Y.Z]`, tag `main`, then a GitHub Release whose notes are the version's **user-facing** section only.

## Documentation

- **Where things go**: see [`docs/README.md`](docs/README.md) for the full map. Active docs use `UPPER_SNAKE_CASE.md`; ADRs use `NNNN-kebab-title.md`.
- **CHANGELOG.md**: hand-curated ([Keep a Changelog](https://keepachangelog.com/) + SemVer), not a `git log` dump. Entries accrue under `[Unreleased]`, split into **`### Highlights`** (user-facing: UI/UX, gameplay, fixes — these become the GitHub Release notes) and **`### Internal`** (ADRs, CI, refactors). The root file keeps `[Unreleased]` + the last 1–2 versions; older versions move to `docs/archive/changelog/CHANGELOG-vX.Y.Z.md`.
- **ADRs are append-only**: never edit an accepted decision — write a new one that supersedes it.
- **Archive, don't delete**: superseded docs move to `docs/archive/`, keeping naming and history.

## File Locations
- **Game Engine**: `backend/app/core/`
- **AI Logic**: `backend/app/ai/`
- **Models**: `backend/app/models/`
- **REST API**: `backend/app/api/`
- **Templates**: `templates/` (YAML)
