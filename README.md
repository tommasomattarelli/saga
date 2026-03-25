# SAGA — AI-Driven Tabletop RPG

An open-source, AI-powered single-player tabletop RPG with an expert AI Dungeon Master. The AI DM has full authority over the world — you propose actions, the DM adjudicates through dice rolls and narrative logic. NPCs have psychology models, companions feel human, and the world moves forward independently of you.

## Features

- **Multi-provider AI**: Intelligent routing between OpenAI, Anthropic, Google Gemini — budget models for background tasks, premium models for narrative peaks
- **Semantic memory**: The DM remembers your story through pgvector embeddings, recalling thematically relevant events even hundreds of turns later
- **Living world**: Factions plot, NPCs act, weather changes, rumors spread — all independently of the player. GameClock tracks in-game time (minutes, hours, days, seasons) and advances every turn
- **Structured DM output**: Pydantic-validated JSON schema with JSON healing (`json-repair`) for robust parsing. Content policy violations are caught per-provider and returned as readable messages
- **6-level dice outcomes**: natural 1 (critical failure) → hard failure → soft failure → partial success → full success → natural 20 (critical success). Dice are rolled server-side; frontend shows click-to-reveal animation
- **Narrative character creation**: No separate form — the DM guides character creation through conversation on first play
- **Scene moods**: 11 mood states mapped to CSS custom properties for smooth UI transitions
- **Classless progression**: No classes. Your character improves the skills they actually use
- **Companion AI**: Companions with loyalty, trust, moods, and their own opinions — they may disagree with you
- **Three death modes**: Ironman (permadeath), Destino (death with narrative cost), Cronista (story mode)
- **Campaign templates**: Extensible YAML-based template system for community-created adventures
- **Data portability**: Export/import your campaigns as JSON
- **Self-hostable**: Run entirely on your own hardware with your own API keys

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
# Backend unit tests
cd backend && pytest tests/unit

# Backend integration tests
cd backend && pytest tests/integration

# Automated playtest (AI plays the game)
cd backend && python -m tests.playtest.bot --turns 100 --template tutorial

# Frontend tests
cd frontend && npm run test
```

## Contributing

Contributions welcome. Please follow:

- **Python**: PEP 8 via Ruff, type hints required, async for all I/O
- **TypeScript**: ESLint + Prettier, functional components only, no `any`
- **Git**: Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`)
- **Tests**: Required for backend business logic

## License

[AGPL-3.0](LICENSE) — free to use, modify, and self-host. If you run a modified version as a service, you must share the source.
