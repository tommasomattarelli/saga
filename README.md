# SAGA — AI-Driven Tabletop RPG

An open-source, AI-powered single-player tabletop RPG with an expert AI Dungeon Master. The AI DM has full authority over the world — you propose actions, the DM adjudicates through dice rolls and narrative logic. NPCs have psychology models, companions feel human, and the world moves forward independently of you.

## Features

- **Multi-provider AI routing**: Intelligent routing between OpenAI, Anthropic, Google Gemini — budget models (Gemini Flash) for NPC/compression, premium models (Gemini Pro, Claude Opus) for narrative peaks. All configurable in `saga.config.yaml`
- **Three-tier semantic memory**: Active Window (8 verbatim turns) + rolling summaries + pgvector recall (top-3 semantically relevant MemoryFacts injected per turn). The DM remembers plot details from hundreds of turns ago without them being in context
- **Global story summary**: A ~200-word rolling campaign arc paragraph, updated every 5 turns via anchored iterative LLM summarization. Always in the DM's context — no memory amnesia after turn 8
- **LangGraph agent loop**: DM runs as a stateful LangGraph graph (context → DM → tools → DM → ...) with max 5 steps, meaningful-tool detection, and consecutive-empty-step guard to prevent silent loops
- **NPC psychology system**: Each NPC has personality, motivation, secret, fear, and disposition (±100 scale). `invoke_npc` calls a dedicated NPC Director LLM — NPCs respond in-character, not as the DM. Disposition changes persist across turns
- **NPC auto-creation**: If the DM calls `invoke_npc` for an untracked NPC, the system auto-creates a profile with configurable detail (minimal/standard/rich). No broken tool calls
- **JSON-enforced output**: All NPC, companion, and world simulation calls use provider JSON mode (`response_mime_type`, `response_format`). No silent parse failures
- **Persona presets**: Campaign templates ship with a DM voice preset (grimdark/heroic/dark_fantasy/horror) injected as a `<persona>` XML block before the rules. Custom `persona_xml` override available
- **Dynamic tool loading**: 5 tool groups (core/combat/social/inventory + combat_entry) activated by world state. DM never sees more than ~12 tools simultaneously
- **Living world**: Factions, NPCs, weather, and game clock advance independently. Full world state persisted as JSONB per turn
- **6-level dice outcomes**: natural 1 (critical failure) → hard failure → soft failure → partial success → full success → natural 20 (critical success). Dice rolled server-side, click-to-reveal on frontend
- **Scene moods**: 11 mood states (`combat_fury`, `tense_anticipation`, `eerie`, ...) mapped to CSS custom properties for smooth UI transitions
- **Three death modes**: Ironman (permadeath), Destino (death with escalating narrative cost), Cronista (story mode, no death)
- **Campaign templates**: Extensible YAML-based template system. Ships with 3 built-in scenarios
- **Data portability**: Export/import campaigns as JSON
- **Self-hostable, BYOAK**: Run on your own hardware with your own API keys. No cloud dependency

## Quick Start (Docker)

```bash
git clone https://github.com/<org>/saga.git
cd saga
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Quick Start (Local)

### Backend

```bash
cd backend
uv sync            # or: pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Requires PostgreSQL 16+ with pgvector and Redis running locally.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Tailwind CSS, Zustand, React Query, Vite |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Database | PostgreSQL 16 + pgvector, Redis |
| AI | OpenAI, Anthropic Claude, Google Gemini, with intelligent routing |
| Auth | JWT + bcrypt, AES-256 encrypted API key storage |
| Infra | Docker Compose, GitHub Actions |

## Project Structure

```
saga/
├── frontend/          # React + TypeScript + Vite
│   └── src/
│       ├── components/    # UI components (narrative, character, combat, etc.)
│       ├── stores/        # Zustand state management
│       ├── services/      # API client, WebSocket client
│       └── i18n/          # Internationalization
│
├── backend/           # Python + FastAPI
│   └── app/
│       ├── api/           # REST + WebSocket endpoints
│       ├── core/          # Game engine (dice, combat, world sim, progression)
│       ├── ai/            # Multi-provider AI engine, prompts, routing
│       ├── memory/        # Semantic search, compression, recaps
│       ├── models/        # SQLAlchemy models
│       ├── security/      # JWT auth, encryption, RBAC
│       └── services/      # Business logic layer
│
├── templates/         # Campaign templates (YAML)
│   ├── tutorial/          # "The Awakening" — beginner scenario
│   ├── shattered_crowns/  # Political fantasy intrigue
│   └── last_light/        # Dark fantasy survival
│
└── docker-compose.yml # One-command local setup
```

## Campaign Templates

SAGA ships with three built-in templates:

| Template | Difficulty | Description |
|----------|-----------|-------------|
| **The Awakening** | 3/10 | Tutorial. Wake in a forest shrine with no memory. Learn the ropes. |
| **Shattered Crowns** | 7/10 | Political fantasy. Four houses vie for an empty throne. Every alliance has a cost. |
| **Last Light** | 9/10 | Dark survival. The sun is dying. Carry light through the dark, or be consumed. |

Create your own templates following the [Template SDK schema](templates/schema.json).

## Configuration

Copy `.env.example` to `.env` and configure:

- **Database**: PostgreSQL + Redis connection strings
- **Auth**: JWT secret keys
- **AI Providers**: API keys for OpenAI, Anthropic, Google (users can also configure their own via the UI)
- **App mode**: `community` (self-hosted) or `cloud` (hosted premium)

## Running Tests

```bash
# Backend unit tests (no infra required)
cd backend && uv run python -m pytest tests/unit --noconftest

# Backend integration tests (requires PostgreSQL + Redis)
make test-infra-up
cd backend && uv run python -m pytest tests/integration

# Automated playtest (AI plays the game)
cd backend && uv run python -m tests.playtest.bot --turns 100 --template tutorial

# Frontend tests
cd frontend && npm run test
```

## Architecture

See [AGENTIC_ARCHITECTURE.md](AGENTIC_ARCHITECTURE.md) for the full AI engine design: LangGraph graph, memory pipeline, system prompt structure, tool loop mechanics, and roadmap.

See [docs/CONFIG.md](docs/CONFIG.md) for complete `saga.config.yaml` reference.

## Contributing

Contributions welcome. Please follow:

- **Python**: PEP 8 via Ruff, type hints required, async for all I/O
- **TypeScript**: ESLint + Prettier, functional components only, no `any`
- **Git**: Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **Tests**: Required for backend business logic

## License

[AGPL-3.0](LICENSE) — free to use, modify, and self-host. If you run a modified version as a service, you must share the source.
