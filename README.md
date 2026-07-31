# SAGA — AI-Driven Tabletop RPG

[![CI](https://github.com/tommasomattarelli/saga/actions/workflows/ci.yml/badge.svg?event=pull_request)](https://github.com/tommasomattarelli/saga/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/tommasomattarelli/saga?include_prereleases&sort=semver)](https://github.com/tommasomattarelli/saga/releases)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776ab)](backend/pyproject.toml)
[![Node 20+](https://img.shields.io/badge/node-20+-5fa04e)](frontend/package.json)

A single-player tabletop RPG run by an expert AI Dungeon Master. You propose actions in
plain language; the DM adjudicates them with dice and narrative logic. NPCs carry their
own psychology, the world keeps moving while you are elsewhere, and the DM remembers what
happened three hundred turns ago. Self-hosted, your own API keys, no cloud account.

> ### ⚠️ Alpha — `v0.2.0-beta.1`
>
> SAGA is playable end to end but pre-1.0 and under active development. Concretely:
>
> - **The schema and the API change without a migration path.** A pre-1.0 upgrade may
>   require wiping the database; campaigns are not guaranteed to survive a version bump
>   (export them — see [Data portability](#data-portability)).
> - **The UI is functional, not finished.** A visual pass is in progress.
> - **Output quality depends on the model you point it at.** Cheap free-tier models drift
>   out of language and skip tool calls; see [Choosing a model](#choosing-a-model).
> - Expect bugs. [Open an issue](https://github.com/tommasomattarelli/saga/issues/new/choose) —
>   that is what the alpha is for.

---

## Install

Three ways in, easiest first. All of them need an API key from at least one AI provider —
OpenAI, Anthropic, Google, OpenRouter, or a local OpenAI-compatible server. The key goes
in a `.env` file; each route below says which one.

### Windows — one click, no Docker

1. Download **[`install/windows/install_saga.bat`](install/windows/install_saga.bat)** and double-click it.
2. It installs Git if missing, clones SAGA into `%LOCALAPPDATA%\SAGA\app`, provisions uv,
   Node and a portable PostgreSQL 16 + pgvector, builds the app, and creates a **SAGA**
   desktop shortcut.
3. Put your provider key in `%LOCALAPPDATA%\SAGA\app\backend\.env` (the installer creates
   it with the secrets already generated), then double-click **SAGA**. Closing the window
   stops everything — Postgres starts and stops with the app.

Opens at <http://localhost:8000>. Windows 10/11, no admin rights, ~3–4 GB free, internet
on first run. To remove it all: `windows\uninstall_saga.ps1`.

### Linux / macOS — one script, no Docker

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga
bash install/linux-macos/install_saga.sh
```

Provisions uv + Node and installs PostgreSQL 16 + pgvector through your package manager —
**Homebrew on macOS, apt on Debian/Ubuntu**. Other package managers are not supported yet
([#58](https://github.com/tommasomattarelli/saga/issues/58)); on those, use Docker below.
Do not run it as root. The app listens on `8000`, its private Postgres on `54320`.

Put your provider key in `~/.local/share/saga/app/backend/.env` (created by the installer,
secrets already generated), then launch with `bash install/linux-macos/start_saga.sh`.

Full installer reference, including the maintainer bundle: [`install/README.md`](install/README.md).

### Docker

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga
cp .env.example .env          # add your provider key, generate the two secrets
docker compose up --build
```

- App: <http://localhost:3000>
- API: <http://localhost:8000> · docs: <http://localhost:8000/docs>

The shipped Compose stack is a **development** setup (bind mounts, hot reload, Vite dev
server). Production images are not published yet.

### From source (development)

```bash
# backend — needs PostgreSQL 16 + pgvector reachable at DATABASE_URL
cd backend
cp ../.env.example .env       # the backend reads .env from its own directory
uv sync
alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev
```

Two things to fix in that `.env`: `DATABASE_URL` points at the Docker host (`db:5432`) —
change it to `localhost:5432` — and the two `change-me` secrets are rejected at startup on
purpose. Under Compose the root `.env` is used instead; outside it, the backend loads
`.env` relative to its working directory.

---

## First run

1. Open the app and create an account. It is local — your database, your machine.
2. **New campaign**: pick the shipped world, *The Awakening* — you wake at a forest shrine
   with no memory, a wary ranger named Lyra at your side, and something stirring in the old
   mines. Choose a death mode, roll a character, play.
3. Type what you want to do in plain language. The DM decides whether it needs a roll,
   rolls it server-side, and narrates the outcome.

### Choosing a model

SAGA routes each call to a tier by importance, so you are not paying premium rates for
background world simulation — see [`docs/CONFIG.md`](docs/CONFIG.md). What matters in
practice:

- **Best experience**: a frontier model on the narration tier (Claude Opus, GPT-5,
  Gemini 2.5 Pro) with a cheap model on the background tiers.
- **Cheapest usable**: Gemini Flash across the board.
- **Free tiers**: usable to try it out, but they saturate fast and the weakest models skip
  tool calls or drift out of English — a measured, known limitation, not a mystery.

---

## What makes it different

- **Three-tier memory that actually recalls.** An 8-turn verbatim window, rolling batch
  summaries, and pgvector semantic recall that injects the three most relevant facts for
  *this* action. On top of it a ~200-word global story summary, rewritten every 5 turns, so
  the campaign arc is always in context — no amnesia after turn 8.
- **NPCs that are not the DM in a hat.** Every NPC carries personality, motivation, a
  secret, a fear and a disposition on a ±100 scale. The DM hands the scene to a dedicated
  NPC model, which answers in character; disposition shifts persist across turns.
- **A world that moves without you.** Factions, weather, NPC schedules and the game clock
  advance on their own. Full world state is persisted per turn.
- **Model routing by importance.** Budget models for compression and background sim,
  premium models for narrative peaks — every tier configurable in `saga.config.yaml`.
- **Worlds are data, not code.** A world is a tree of YAML — nodes, edges, factions, NPCs,
  encounters — versioned with git and editable in-app. Export and import as JSON.
- **Yours.** AGPL, self-hosted, your keys, your database, your campaigns.

<details>
<summary>More: the engine in detail</summary>

- **LangGraph agent loop**: the DM is a stateful graph (context → DM → tools → DM → …)
  capped at 5 steps, with meaningful-tool detection and a consecutive-empty-step guard so
  it cannot spin silently.
- **Dynamic tool loading**: 5 tool groups (core / combat entry / combat / social /
  inventory) activated by world state — the DM never sees more than ~12 tools at once.
- **6-level dice outcomes**: natural 1 → hard failure → soft failure → partial success →
  full success → natural 20. Rolled server-side, click-to-reveal in the UI.
- **Three death modes**: Ironman (permadeath), Destino (death at an escalating narrative
  cost), Cronista (story mode, no death).
- **Scene moods**: 11 states (`calm_exploration`, `tense_anticipation`, `combat_fury`,
  `dread_horror`, …) driving CSS custom properties for gradual UI shifts.
- **Persona presets**: each world ships a DM voice (grimdark / heroic / dark_fantasy /
  horror) injected as a `<persona>` block ahead of the rules, overridable per campaign.
- **JSON-enforced output**: NPC, companion and world-sim calls use provider JSON mode, so
  a malformed reply fails loudly instead of silently degrading.
- **Provider-failure honesty**: an upstream error surfaces as a `502` you can retry, and
  the turn is not persisted — the game never invents narration to paper over a failed call.

</details>

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Tailwind CSS, Zustand, React Query, Vite |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Database | PostgreSQL 16 + pgvector |
| AI | OpenAI · Anthropic · Google Gemini · any OpenAI-compatible endpoint — routed by importance in `ai/router.py`; agent loop on **LangGraph 1.0** |
| Transport | REST + JSON. Each turn is one independent POST returning the complete result; no WebSocket, no connection state |
| Auth | JWT + bcrypt; provider keys read from the environment, never sent anywhere but the provider |
| Infra | Docker Compose, GitHub Actions, native installers for Windows/Linux/macOS |

## Worlds

SAGA ships with one complete world, **The Awakening** (tutorial difficulty): a forest
shrine, the wary village of Thornhaven, and the old mines to the north.

A world lives in [`worlds/<slug>/`](worlds/) as a tree of YAML — `world.yaml` and
`scenario.yaml` at the root, then `nodes/` (nested by containment: region → settlement →
building → room), `edges/`, `factions/`, `npcs/` and `encounters/`. The in-app world
editor reads and writes the same files, and the directory is a git repository, so every
edit is versioned and revertible. See
[ADR 0008](docs/adr/0008-world-model-multilayer-yaml.md) for the model.

Building more worlds — and making the DM use deep world detail without saturating its
context — is the main open content track.

### Data portability

Worlds export and import as JSON from the world library in the app. Campaigns export over
the API (`GET /api/export/{campaign_id}`); a button for it in the UI is still to come.
Nothing you make is locked in.

## Configuration

Two sources, deliberately separate:

- **`.env`** — secrets and infrastructure: database URL, JWT secret, API-key encryption
  key, provider keys, optional global model overrides. Copy from `.env.example` and
  generate the two secrets with `openssl rand -hex 32` — the `change-me` defaults are
  rejected at startup on purpose. Provider keys are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GOOGLE_AI_API_KEY`, `OPENROUTER_API_KEY`; a local OpenAI-compatible server goes in
  `LOCAL_MODEL_URL`.
- **`saga.config.yaml`** — gameplay and AI cost knobs: model tier per call type, tool
  groups, memory sizes, rate limits. Full reference in [`docs/CONFIG.md`](docs/CONFIG.md).

## Project structure

```
saga/
├── frontend/           # React + TypeScript + Vite
│   └── src/
│       ├── features/       # game, character, combat, worlds, auth
│       ├── shared/         # Zustand stores, API client, UI primitives
│       └── i18n/           # internationalization
│
├── backend/            # Python + FastAPI
│   ├── app/
│   │   ├── api/            # REST endpoints (thin)
│   │   ├── core/           # game engine — dice, combat, death, DM graph
│   │   ├── ai/             # providers, routing, prompts, DM tools
│   │   ├── memory/         # semantic recall, compression, summaries, world state
│   │   ├── models/         # SQLAlchemy models
│   │   ├── security/       # JWT auth, encryption
│   │   └── services/       # business logic
│   └── eval/               # model-compliance harness (does a model obey the DM's tools?)
│
├── worlds/             # game worlds as YAML trees (git-versioned)
├── install/            # native no-Docker installers (Windows / Linux / macOS)
├── docs/               # architecture, config reference, ADRs
└── docker-compose.yml
```

## Documentation

| Document | Open it when you want to… |
|---|---|
| [`docs/README.md`](docs/README.md) | Find the right doc — the map |
| [`docs/AGENTIC_ARCHITECTURE.md`](docs/AGENTIC_ARCHITECTURE.md) | Understand the DM loop, memory pipeline and prompt structure |
| [`docs/CONFIG.md`](docs/CONFIG.md) | Look up a `saga.config.yaml` knob |
| [`docs/adr/`](docs/adr/) | Read *why* a design decision was made — 18 records so far |
| [`CHANGELOG.md`](CHANGELOG.md) | See what changed and when |
| [`TODO.md`](TODO.md) | See what is being worked on next |

## Tests

```bash
# backend unit — no infrastructure needed
cd backend && uv run python -m pytest tests/unit --noconftest

# backend integration — real PostgreSQL + pgvector, no mocks
make test-infra-up
cd backend && uv run python -m pytest tests/integration

# frontend
cd frontend && npm run test
```

`backend/eval/` additionally measures whether a candidate model honours the DM's tool
obligations under an empty vs. a saturated context — models are chosen on measurements,
not on reputation.

## Contributing

Issues and pull requests are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup,
conventions and how work is organised. Bug reports and feature requests go through the
[issue forms](https://github.com/tommasomattarelli/saga/issues/new/choose); open-ended
ideas belong in [Discussions](https://github.com/tommasomattarelli/saga/discussions).

## License

Copyright © 2026 SAGA contributors.

Licensed under the [GNU AGPL-3.0](LICENSE) — free to use, modify and self-host. If you run
a modified version as a network service, you must publish your source.
