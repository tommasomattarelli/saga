# Project State of the Art (STATE.md)

## Current Snapshot: Phase 2 "Safety Net" Complete
The project is in a highly stable pre-refactoring phase. We have 101 tests (Unit + Integration + Playtest) ensuring that any structural change to the engine will be caught immediately.

### 💎 Core Implementations (Verified & Stable)

#### 1. AI Orchestration & Logic
- **Advanced AI Router**: Implemented in `ai/router.py`. Supports:
    - **Multi-provider**: OpenAI, Anthropic, Google Gemini.
    - **Importance Tiering**: Dynamically selects models (High/Medium/Low) based on scene importance score (0-10).
    - **Override Hierarchy**: YAML defaults -> Global Settings -> Env vars (e.g., `SAGA_MODEL_DM_NARRATION_HIGH`).
- **Semantic Memory (V1)**: Turn summaries are stored with embeddings for potential long-term retrieval (pgvector).
- **Structured DM Parser**: Reliable JSON parsing of DM responses including narration, dice requests, and world updates.

#### 2. Security & Data Sovereignty
- **API Key Vault**: User API keys are NEVER stored in plaintext. Implemented **AES-256-GCM** with **HKDF-SHA256** key derivation (`security/encryption.py`).
- **Data Portability**: Full JSON export/import of the campaign "Universe" (Campaign metadata + full Turn history).
- **Multi-tenant isolation**: Every query is filtered by `user_id` from day zero.

#### 3. Frontend Architecture (React 18 + Zustand)
- **Component Kit**: Functional components for `NarrativeStream`, `CharacterSheet`, `DiceRoller`, etc.
- **Global State**: Minimalist stores (`game-store`, `auth-store`, `ui-store`) used consistently.
- **i18n Support**: Ready-to-use internationalization framework (`react-i18next`) with separate `en.json` logic.

#### 4. Adventure SDK & Content
- **Template Schema**: Robust JSON schema (`templates/schema.json`) for adventure validation.
- **Built-in Adventures**: Three ready-to-play YAML templates (`tutorial`, `last_light`, `shattered_crowns`) with lore and story branching.

### 🚩 Technical Debt & Structural "God Modules"

#### 1. Backend Bottlenecks
- **`engine.py` (The God Function)**: The central processing loop is too dense. Needs split into Orchestrator/Resolver/Synthesizer.
- **`websocket.py` (Transport Overload)**: Currently handles game logic that should be in the engine.
- **`turn_service.py` (Service Bloat)**: Mixing I/O (embeddings, DB) with business logic (sanitization, game flow).

#### 2. Test & Quality Debt
- **Frontend Type Safety**: Too many `as any` in tests. Shared types between Python (Pydantic) and TS (Interfaces) are not synchronized.
- **AI Playtest Realism**: Playtest bots use fixed patterns; need randomized "chaos" input tests for LLM stability.
- **Missing Cascades**: (Fixed during Phase 2) — Verified that deleting users/campaigns now cleans up orphaned records.

### 🚀 Roadmap: Phase 3 (Modular Refactoring)
1. **Engine Decoupling**: Isolate dice logic and state updates from the AI prompt logic.
2. **WebSocket Thinning**: Move turn-processing to the `TurnOrchestrator`.
3. **Type Generation**: Automated TS type generation from Rust/Python models.

---
*Last updated: March 24, 2026 — 101/101 Tests Passing.*
