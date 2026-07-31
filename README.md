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

| Route | Pick it if | Needs |
|---|---|---|
| [**Windows — one click**](#windows--one-click) | You just want to play | Windows 10/11 |
| [**Linux / macOS — one script**](#linux--macos--one-script) | You just want to play | Homebrew or apt |
| [**Docker**](#docker) | Anything else, or you already run containers | Docker Compose |
| [**From source**](#from-source) | You want to change the code | uv · Node 20 · Postgres 16 |

Every route needs **one AI provider key** — OpenAI, Anthropic, Google, OpenRouter, or a
local OpenAI-compatible server. Nothing else is a service you sign up for: the database,
the game and your campaigns all live on your machine.

The key goes in a `.env` file. The two installers create that file for you with the other
secrets already generated, so the only line you add is your key.

### Windows — one click

```text
download install/windows/install_saga.bat  →  double-click  →  desktop shortcut "SAGA"
```

The bootstrapper installs Git if it is missing, clones SAGA into `%LOCALAPPDATA%\SAGA\app`,
provisions uv, Node and a **portable PostgreSQL 16 + pgvector** (no system install, no
admin rights), builds the app and drops a desktop shortcut.

Then, once:

```powershell
notepad %LOCALAPPDATA%\SAGA\app\backend\.env    # add OPENAI_API_KEY=... (or another provider)
```

Double-click **SAGA** to play — it opens at <http://localhost:8000>. Closing the window
stops everything; Postgres starts and stops with the app.

> **Needs** Windows 10/11 · ~3–4 GB free · internet on first run.
> **Removes cleanly** with `windows\uninstall_saga.ps1`.

### Linux / macOS — one script

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga
bash install/linux-macos/install_saga.sh          # do not run as root

$EDITOR ~/.local/share/saga/app/backend/.env      # add your provider key
bash install/linux-macos/start_saga.sh            # every launch after that
```

Provisions uv + Node and installs PostgreSQL 16 + pgvector through your package manager.
Opens at <http://localhost:8000>; its private Postgres listens on `54320`, out of the way
of any Postgres you already run.

> **Needs** Homebrew (macOS) or apt (Debian/Ubuntu). Other package managers are not
> supported yet ([#58](https://github.com/tommasomattarelli/saga/issues/58)) — use Docker
> instead.

Full installer reference, including the maintainer bundle: [`install/README.md`](install/README.md).

### Docker

```bash
git clone https://github.com/tommasomattarelli/saga.git
cd saga
cp .env.example .env          # add your provider key + run openssl rand -hex 32 twice
docker compose up --build
```

| | |
|---|---|
| App | <http://localhost:3000> |
| API | <http://localhost:8000> |
| API docs | <http://localhost:8000/docs> |

> The shipped Compose stack is a **development** setup — bind mounts, hot reload, Vite dev
> server. Production images are not published yet.

### From source

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

> Two edits in that `.env`: point `DATABASE_URL` at `localhost:5432` (the shipped value is
> the Docker hostname `db`), and replace both `change-me` secrets with
> `openssl rand -hex 32` — startup rejects the defaults on purpose.
>
> Under Compose the **root** `.env` is used; outside it, the backend loads `.env` relative
> to its own working directory.

---

## What SAGA is

A tabletop campaign is not a chat. It has to hold continuity for hundreds of turns, keep a
world consistent while the player is looking somewhere else, and stay honest about what
actually happened. A language model on its own does none of that — it improvises, and
improvisation has no memory and no arithmetic. SAGA is the machinery around the model that
makes the difference.

**The DM is an agent, not a prompt.**
Each turn runs as a stateful graph: assemble context → call the DM model → execute the tools
it asked for → hand the results back → repeat, hard-capped at five steps. The DM does not
*describe* changes to the world, it *calls* them. Picking up a sword, moving to another
place, shifting how an NPC feels about you, advancing the clock — each is a typed tool call
against persisted state. Narration is what the player reads; the tool calls are what
happened. When the two disagree, that is a defect the engine can detect, not a story the
model got away with.

**The engine owns the numbers; the model owns the fiction.**
Everything a language model is unreliable at is taken away from it. Dice are rolled
server-side on a six-level outcome ladder — a natural 1 and a near-miss are different
events, and the model learns the result rather than choosing it. Damage, prices, loot and
progression are computed by the engine from world data. A model that picks the damage number
can be talked into picking zero; "sell it to me for one coin" stops being an attack surface
when the model never touches the price. What is left for the model is what it is genuinely
good at: voice, pacing, consequence, and making a failed roll interesting.

**The world runs whether or not you are in it.**
A world is authored data, not prompt text: a tree of YAML — regions, settlements, rooms,
roads, factions, NPCs, encounters — instantiated into per-campaign state that is persisted
every turn and versioned in git. Factions hold agendas, NPCs hold psychology on
world-defined axes, places hold status. The DM reads a scene out of that state; it does not
invent one and hope the next turn agrees.

**Memory is a pipeline, not a context window.**
Three tiers work together: the last eight turns verbatim, rolling summaries of everything
older, and pgvector semantic recall that pulls the handful of past facts relevant to *this*
action back into context. Above them sits a rolling ~200-word summary of the whole campaign
arc, rewritten every few turns. The DM can call back to something from turn 12 on turn 300
without it ever having been in the window.

**Models are measured, not chosen by reputation.**
`backend/eval/` drives the production prompts and tool schemas through probes taken from
real playtest failures: a present NPC has to answer through the NPC call, a turn that changes
the inventory has to record it, a passive turn still has to advance the clock. Tool
compliance is stochastic, so every probe runs repeatedly against both an empty context and a
saturated one, and the report prints the gap between them. That gap — how much worse a model
behaves once the context is full, which is where real play lives — is the number that decides
whether a cheap model is good enough.

<details>
<summary>More: the engine in detail</summary>

- **LangGraph agent loop**: the DM is a stateful graph (context → DM → tools → DM → …)
  capped at 5 steps, with meaningful-tool detection and a consecutive-empty-step guard so
  it cannot spin silently.
- **Dynamic tool loading**: 5 tool groups (core / combat entry / combat / social /
  inventory) activated by world state — the DM never sees more than ~12 tools at once.
- **6-level dice outcomes**: natural 1 → hard failure → soft failure → partial success →
  full success → natural 20. Rolled server-side, click-to-reveal in the UI.
- **NPCs answer for themselves**: personality, motivation, a secret, a fear and a
  disposition on a ±100 scale, with a dedicated NPC model called for their lines — shifts
  persist across turns.
- **Model routing by importance**: budget models for compression and background simulation,
  premium models for narrative peaks, every tier configurable in `saga.config.yaml`.
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

## Where it's going

The shipped alpha is the reactive half: a player acts, the DM adjudicates, the world records
it. The work in progress is the half that runs on its own. Each direction below is already a
written design decision — scope, open questions, and the alternatives that were rejected and
why.

- **A director behind the curtain.** A background agent above the DM that owns everything
  off-screen: absent NPCs go about their business, factions pursue agendas, distant places
  change hands, foreshadowing is planted and later paid off, events are scheduled ahead of
  time. The player meets it as rumors and consequences. The DM stays the only authority on
  the scene in front of you.
- **NPCs with lives, not moods.** Stable identity across a campaign, lifecycle and
  condition (wounded, missing, dead, gone somewhere), world-defined traits — and
  *promotion*: any NPC can be recruited, and a companion and a boss are the same object with
  opposite sign, a character that earns a real sheet and its own acting brain.
- **A relationship graph beside semantic recall.** Search answers "what past event fits this
  moment". A graph answers "who hates whom, who owes whom, and who told them" — with
  recency and salience so a campaign's pillar facts stay reachable and stale ones sink.
- **Combat that resolves instead of negotiating.** One unified check for everything, in and
  out of combat, on real statblocks, with damage and initiative owned by the engine.
- **Characters that grow.** A typed character sheet, skills and proficiencies, items as
  records rather than flavor text, equipment, and progression the model cannot inflate.
- **Special moves and structured input.** Active abilities with costs and cooldowns, on a
  rail where the engine resolves the effect and the model narrates it — free text stays the
  main channel, not the only one.
- **An economy.** Prices computed by the engine from world data, shops, services, and
  haggling that runs through an NPC's psychology and a real check instead of a menu.
- **Routing that reads the moment.** Importance scoring that works in any language, reusing
  the embedding each turn already computes, so the expensive model is spent on the turns
  that deserve it.
- **Deeper worlds.** More authored content, and the harder part: letting the DM draw on a
  large world without drowning its context in it.

Where this ends up: a single player can inhabit one world for hundreds of turns, and it
keeps its own continuity — the model narrates, the engine remembers and adjudicates, and
neither is asked to do the other's job.

Every decision above is recorded in [`docs/adr/`](docs/adr/), rejected alternatives
included.

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

- **Best experience**: a frontier model on the narration tier (Claude Opus 5, GPT-5-5/6...) with a cheap model on the background tiers.
- **Free tiers**: usable to try it out, but they saturate fast and the weakest models skip
  tool calls or drift out of English — a measured, known limitation, not a mystery.

---

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

Copyright © 2026 SAGA contributors. Licensed under the [GNU AGPL-3.0](LICENSE).

- **Playing, self-hosting, modifying, forking** — all fine, no permission needed.
- **Redistributing it**, modified or not, means shipping the complete source under the
  same licence.
- **Running a modified version as a network service** means the same: your users must be
  able to get your source. This is the clause plain GPL lacks, and the reason it is the
  licence here — hosting SAGA as a closed product is not a way around sharing the changes.

The name **SAGA** and the project's branding are not covered by the licence: fork the code
freely, don't ship it as if it were this project.
