# SAGA / Wyrd — Project Guide

## Overview
SAGA/Wyrd is an AI-driven tabletop RPG engine designed to replicate the infinite possibilities of D&D. An expert AI Dungeon Master (DM) maintains authority over the world, adjudicating player actions through complex narrative logic and dice-based mechanics.

### Core Pillars
- **Intelligent AI Routing**: Dynamically selects models (custom `ai/router.py`) based on importance (GPT-5/Opus for narrative peaks, Gemini Flash for background world-sim).
- **Semantic Memory**: Uses `pgvector` for "long-term storytelling recall" — the DM remembers thematically relevant past events.
- **Living World**: Full state persistence (JSONB) of world state, factions, and NPC psychology that moves forward independently.
- **Data Sovereignty**: Open-source, self-hostable, with full campaign export/import (JSON).

## Essential Commands
### Backend (uv based)
- **Install**: `cd backend && uv sync`
- **Run**: `cd backend && uv run uvicorn app.main:app --reload`
- **Test**: `cd backend && uv run pytest tests/unit tests/integration tests/playtest`
- **Lint/Format**: `cd backend && uv run ruff check . && uv run ruff format .`
- **Migrations**: `cd backend && alembic upgrade head`

### Frontend (npm based)
- **Install**: `cd frontend && npm install`
- **Run**: `cd frontend && npm run dev`
- **Test**: `cd frontend && npm run test`
- **Lint/Format**: `cd frontend && npm run lint && npm run format`

### Infrastructure (Docker)
- **Up**: `make test-infra-up` (Test DB/Redis) | `docker-compose up -d` (Prod-like)
- **Down**: `make test-infra-down` | `docker-compose down`

## Coding Rules & SOTA Standards
1. **TDD First**: Write failing integration/unit tests before implementation. Use 100% real DB for core flows.
2. **No Verbose Comments**: Code must be self-documenting. Comment ONLY "Why", never "What". No docstrings for internal logic.
3. **Type Safety**: Mandatory Python type hints and TypeScript interfaces. Zero `any` tolerance.
4. **Async Everything**: Non-blocking I/O for DB, AI, and WebSockets.
5. **Database First**: Use real PostgreSQL 16 features (pgvector, JSONB) over mock-heavy unit tests.
6. **Error Handling**: Fail fast, use specific HTTP exceptions, and return structured error JSON.
7. **Clean Architecture**: Services handle logic, Models handle schema, API handlers are thin wrappers.
8. **AI Engine**: All calls must go through `ai/router.py` for cost/importance scoring.
9. **Naming**: snake_case for Python (all files/vars/funcs), camelCase for TS (vars/funcs) and PascalCase for Components/Types.
10. **Commits**: Conventional Commits only (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
11. **Workflow**: Always `test-infra-up` -> Write failing Integration Test -> Implementation -> Refactor.
12. **NO GOD CLASSES** . no files with multiple logics, and files with 300+ liness

## File Locations
- **Game Engine**: `backend/app/core/`
- **AI Logic**: `backend/app/ai/`
- **Models**: `backend/app/models/`
- **REST API**: `backend/app/api/`
- **Templates**: `templates/` (YAML)
