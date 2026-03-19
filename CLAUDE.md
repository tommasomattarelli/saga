# SAGA / Wyrd — AI-Driven Tabletop RPG

## Project Overview

An open-source, AI-powered single-player tabletop RPG that replicates D&D with an expert AI Dungeon Master. The AI DM has authority over the world — the player proposes actions, the DM adjudicates through dice rolls and narrative logic. NPCs have psychology models, companions feel human, and the world moves forward independently of the player.

**Distribution model:** Open source (AGPL-3.0) + hosted premium cloud version.
**Name:** Working titles — SAGA or Wyrd (final name TBD post-prototype).

---

## Tech Stack

### Frontend
- **Framework:** React 18 + TypeScript
- **Styling:** Tailwind CSS
- **State management:** Zustand (global) + React Query (server state)
- **i18n:** react-i18next (JSON locale files, English first)
- **Build:** Vite

### Backend
- **Language:** Python 3.12+
- **Framework:** FastAPI + Uvicorn (ASGI)
- **WebSocket:** FastAPI WebSockets or python-socketio
- **ORM:** SQLAlchemy 2.0 (async) + Alembic (migrations)
- **Validation:** Pydantic v2 (built into FastAPI)
- **Auth:** JWT with refresh tokens, bcrypt password hashing
- **API key storage:** AES-256 encrypted in DB, decrypted server-side only

### Database
- **Primary:** PostgreSQL 16+ with pgvector extension
- **Cache:** Redis (session cache, rate limiting, active game state)
- **Vector search:** pgvector for semantic memory (event embeddings)

### AI Engine
- **Architecture:** Multi-provider with intelligent routing
- **DM Narration (default):** OpenAI GPT-5.2
- **DM Narration (premium):** Anthropic Claude Sonnet 4.6 / Opus 4.6
- **Companion dialogue:** Google Gemini 2.5 Pro
- **NPC / World sim / Memory:** OpenAI GPT-4o-mini or Google Gemini 2.0 Flash
- **Embeddings:** Voyage AI API or local bge-small model
- **AI Router:** Custom Python module that selects model per call based on scene importance scoring

### Infrastructure
- **Containerization:** Docker + Docker Compose (one-command setup)
- **Frontend hosting (cloud):** Vercel
- **Backend hosting (cloud):** Fly.io
- **File storage:** Cloudflare R2
- **CI/CD:** GitHub Actions
- **Versioning:** Semantic versioning, automated changelog

---

## Project Structure

```
saga/
├── CLAUDE.md                    # This file
├── LICENSE                      # AGPL-3.0
├── README.md                    # Project overview, install guide
├── docker-compose.yml           # One-command local setup
├── .env.example                 # Environment variable template
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── public/
│   │   └── sounds/              # Dice rolls, ambience, effects
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── narrative/       # NarrativeStream, DiceRoller, CompanionBubble
│   │   │   ├── character/       # CharacterSheet, InventoryPanel, QuestLog
│   │   │   ├── world/           # WorldMap, LocationInfo, TimeWeather
│   │   │   ├── combat/          # CombatTracker, InitiativeOrder, HPBars
│   │   │   ├── input/           # ActionInput, QuickActions, ActionSuggester
│   │   │   ├── companion/       # CompanionBar, CompanionPanel, MoodIndicator
│   │   │   ├── meta/            # ProfileView, Achievements, CampaignHistory
│   │   │   ├── settings/        # APIKeyConfig, MaturitySettings, SoundSettings
│   │   │   └── auth/            # LoginForm, RegisterForm, UserMenu
│   │   ├── stores/              # Zustand stores
│   │   │   ├── gameStore.ts     # Active game state
│   │   │   ├── uiStore.ts       # Panel visibility, theme
│   │   │   └── authStore.ts     # User session
│   │   ├── hooks/               # Custom React hooks
│   │   ├── services/            # API client, WebSocket client
│   │   ├── types/               # TypeScript type definitions
│   │   ├── utils/               # Helpers, formatters
│   │   ├── i18n/
│   │   │   ├── en.json
│   │   │   └── ...              # Future locale files
│   │   └── assets/              # Images, fonts
│   └── tests/
│
├── backend/
│   ├── pyproject.toml           # Python deps (uv/poetry)
│   ├── alembic.ini
│   ├── alembic/                 # DB migrations
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Settings from env vars
│   │   ├── dependencies.py      # FastAPI dependency injection
│   │   │
│   │   ├── api/                 # REST + WebSocket endpoints
│   │   │   ├── auth.py          # Login, register, refresh token
│   │   │   ├── campaigns.py     # CRUD campaigns, turn submission
│   │   │   ├── characters.py    # Character sheet, progression
│   │   │   ├── templates.py     # Campaign template listing
│   │   │   ├── saves.py         # Save/load management
│   │   │   ├── journal.py       # Adventure log
│   │   │   ├── settings.py      # User preferences, API keys
│   │   │   ├── export.py        # Data portability (export/import)
│   │   │   └── websocket.py     # Game WebSocket handler
│   │   │
│   │   ├── core/                # Game engine
│   │   │   ├── engine.py        # Turn processing pipeline
│   │   │   ├── dice.py          # Dice engine (d20 system, RNG)
│   │   │   ├── combat.py        # Combat resolution, initiative
│   │   │   ├── world_sim.py     # Off-screen world simulation
│   │   │   └── progression.py   # Classless XP, proficiency-by-use
│   │   │
│   │   ├── ai/                  # AI engine layer
│   │   │   ├── router.py        # Model selection per call (importance scoring)
│   │   │   ├── providers/       # Provider-specific clients
│   │   │   │   ├── base.py      # Abstract provider interface
│   │   │   │   ├── openai.py    # GPT-5.2, GPT-4o, GPT-4o-mini
│   │   │   │   ├── anthropic.py # Claude Opus, Sonnet
│   │   │   │   ├── google.py    # Gemini Pro, Flash
│   │   │   │   └── local.py     # Future: self-hosted Qwen via vLLM
│   │   │   ├── prompts/         # System prompts and templates
│   │   │   │   ├── dm.py        # DM system prompt builder
│   │   │   │   ├── companion.py # Companion personality prompts
│   │   │   │   ├── npc.py       # NPC behavior prompts
│   │   │   │   └── world.py     # World simulation prompts
│   │   │   ├── context.py       # Context assembler (prompt budgeting)
│   │   │   ├── parser.py        # Structured DM output parser
│   │   │   ├── sanitizer.py     # Anti prompt-injection layer
│   │   │   └── embeddings.py    # Embedding generation for pgvector
│   │   │
│   │   ├── memory/              # Memory and persistence
│   │   │   ├── world_state.py   # World state manager (JSON updates)
│   │   │   ├── compressor.py    # Tiered memory compression
│   │   │   ├── semantic.py      # pgvector similarity search
│   │   │   └── recap.py         # Session recap generator
│   │   │
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── user.py          # User, roles, API key vault
│   │   │   ├── campaign.py      # Campaign, status
│   │   │   ├── turn.py          # Turn, dice rolls, embedding
│   │   │   ├── save.py          # Save points
│   │   │   ├── template.py      # Campaign templates
│   │   │   └── meta.py          # Achievement, profile stats
│   │   │
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── security/            # Auth, encryption, RBAC
│   │   │   ├── auth.py          # JWT creation/verification
│   │   │   ├── encryption.py    # AES-256 for API keys
│   │   │   └── rbac.py          # Role-based access control
│   │   │
│   │   └── services/            # Business logic layer
│   │       ├── campaign_service.py
│   │       ├── turn_service.py
│   │       ├── character_service.py
│   │       ├── save_service.py
│   │       ├── export_service.py
│   │       └── analytics_service.py  # Telemetry (opt-in)
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── playtest/            # Automated playtest bot
│           ├── bot.py           # AI player that plays the game
│           ├── consistency.py   # World state integrity checker
│           └── scorer.py        # Narrative quality scorer
│
├── templates/                   # Campaign templates (JSON/YAML)
│   ├── schema.json              # Template SDK schema definition
│   ├── tutorial/                # "The Awakening" tutorial scenario
│   │   └── template.yaml
│   ├── shattered_crowns/        # Political fantasy template
│   │   └── template.yaml
│   ├── last_light/              # Dark fantasy survival
│   │   └── template.yaml
│   └── README.md                # Template creation guide
│
└── docs/
    ├── INSTALL.md               # Step-by-step installation
    ├── ARCHITECTURE.md          # Technical architecture overview
    ├── CONTRIBUTING.md          # Contributor guide
    ├── TEMPLATE_SDK.md          # How to create campaign templates
    ├── API.md                   # Backend API reference
    └── TROUBLESHOOTING.md       # Common issues and fixes
```

---

## Coding Conventions

### Python (Backend)
- **Style:** Follow PEP 8, enforced via Ruff
- **Type hints:** Required on all function signatures
- **Async:** Use async/await for all I/O operations (DB, API calls, WebSocket)
- **Docstrings:** Google style on all public functions and classes
- **Error handling:** Custom exception classes in `app/exceptions.py`, caught by FastAPI exception handlers
- **Naming:** snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants
- **Imports:** stdlib → third-party → local, enforced by isort

### TypeScript (Frontend)
- **Style:** ESLint + Prettier
- **Components:** Functional components only, no class components
- **State:** Zustand for global state, React Query for server data, local useState for component state
- **Naming:** camelCase for variables/functions, PascalCase for components/types, kebab-case for files
- **Props:** Explicit interface for all component props, no `any` types
- **CSS:** Tailwind utility classes only, no custom CSS files except for animations

### General
- **Git:** Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- **Branches:** `main` (stable), `dev` (integration), `feat/xxx` (feature branches)
- **PRs:** Required for all changes to `main`, at least description + screenshot for UI changes
- **Tests:** Required for all backend business logic, recommended for frontend hooks/stores
- **Secrets:** Never commit API keys. Use `.env` files (gitignored) and `.env.example` for templates

---

## Key Architectural Decisions

### Multi-provider AI with routing
Every LLM call goes through `ai/router.py` which scores scene importance (0-10) and selects the appropriate provider/model. Budget models for background tasks, premium models for narrative peaks. This is the most cost-critical component — get it wrong and costs explode.

### pgvector for semantic memory
Turn summaries are embedded and stored alongside structured data in PostgreSQL. The context assembler runs both structured queries (active quests, faction state) and semantic similarity search (find relevant past events by meaning) in parallel. This gives the DM "intuitive" recall of thematically relevant history.

### User model from day zero
Every DB table has a `user_id` foreign key. Even in single-user self-hosted mode, there's an admin user. This enables future multi-user, multiplayer, and enterprise features without schema refactoring.

### Structured DM output
The DM always returns JSON with defined fields: `narration`, `dice_required`, `companion_actions`, `world_updates`, `scene_mood`, `suggested_actions`. The game engine parses this deterministically. If JSON is malformed, retry up to 3 times with simplified prompt.

### Death modes in game
Three modes chosen at campaign creation (no default, player must choose): Ironman (permad3ath), Destino (d3ath with narrative cost, 2-3 resurrections then permad3ath), Cronista (story mode, d3ath impossible for player). Mode affects DM prompt tone and behavior.

### Save system
Auto-save every turn (only latest, overwritten). Manual saves are user-named, browsable with preview (turn number, date, scene summary), and create timeline forks on load. Self-hosted: unlimited saves. Cloud: capped per tier.

---

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/saga
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET=<random-256-bit-key>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
API_KEY_ENCRYPTION_KEY=<random-256-bit-key>

# AI Providers (users configure their own in the UI, these are fallback/cloud defaults)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_AI_API_KEY=

# App
APP_MODE=community  # "community" (self-hosted) or "cloud" (hosted premium)
DEFAULT_LANGUAGE=en
TELEMETRY_ENABLED=false
LOG_LEVEL=info

# Cloud-only
CLOUDFLARE_R2_ACCESS_KEY=
CLOUDFLARE_R2_SECRET_KEY=
CLOUDFLARE_R2_BUCKET=
```

---

## Development Workflow

### First-time setup
```bash
git clone https://github.com/<org>/saga.git
cd saga
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API docs: http://localhost:8000/docs
```

### Running locally without Docker
```bash
# Backend
cd backend
uv sync  # or pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Running tests
```bash
# Backend
cd backend
pytest tests/unit
pytest tests/integration
python -m tests.playtest.bot --turns 100 --template tutorial  # Automated playtest

# Frontend
cd frontend
npm run test
npm run test:e2e
```

---

## Useful Commands

```bash
# DB migrations
cd backend
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                                # Apply migrations
alembic downgrade -1                                # Rollback one step

# Linting
cd backend && ruff check . && ruff format .
cd frontend && npm run lint && npm run format

# Build for production
cd frontend && npm run build
cd backend && docker build -t saga-backend .
```

---

## AI Prompt Development

System prompts live in `backend/app/ai/prompts/`. Each prompt file exports a function that builds the prompt dynamically based on campaign state.

When modifying DM prompts:
1. Test with the automated playtest bot first (`tests/playtest/bot.py`)
2. Run the narrative quality scorer (`tests/playtest/scorer.py`)
3. Test across at least 2 providers (GPT-5.2 and Gemini) to verify cross-provider compatibility
4. Keep prompts under 2,000 tokens for cacheability

Template prompts live in `templates/*/template.yaml` and follow the Template SDK schema (`templates/schema.json`).
