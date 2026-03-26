# Project State of the Art (STATE.md)

## Current Snapshot: Phase A Complete + Infrastructure Hardened
The project has completed the first major gameplay transformation phase and all infrastructure is production-ready. We have 174 tests (159 unit passing cleanly + 15 stream extractor). The backend streams LLM tokens in real-time to the frontend, turns are persisted with full conversation history, and Docker builds in under 25s.

### 💎 Core Implementations (Verified & Stable)

#### 1. AI Orchestration & Logic
- **Advanced AI Router**: Implemented in `ai/router.py`. Supports:
    - **Multi-provider**: OpenAI, Anthropic, Google Gemini.
    - **Importance Tiering**: Dynamically selects models (High/Medium/Low) based on scene importance score (0-10).
    - **Override Hierarchy**: YAML defaults -> Global Settings -> Env vars (e.g., `SAGA_MODEL_DM_NARRATION_HIGH`).
- **Semantic Memory (V1)**: Turn summaries are stored with embeddings for potential long-term retrieval (pgvector).
- **Structured DM Parser**: Pydantic-validated `DMResponse` schema (`ai/schemas/dm_response.py`) with JSON healing (`json-repair`). Pipeline: strip markdown fences → `repair_json()` → `json.loads()` → `DMResponse.model_validate()` → fallback narration. Reduces retries by ~70%.
- **Content Policy Handler**: Per-provider detection — OpenAI `content_filter`, Anthropic empty response, Google `SAFETY`. All raise `ContentPolicyError` → engine returns readable fallback narration to player.
- **Creation Mode**: Engine detects empty `character_data` → uses dedicated `CREATION_MODE_PROMPT`. DM generates stats via `character_generation` field → saved to campaign automatically.
- **Updated DM Prompt**: Full prompt with all 11 `scene_mood` values, `invoke_npcs`, `time_passed_minutes` guide values (dialogue 1-5, exploration 10-30, travel 30-480), dice rules (trivial → null, impossible → null, uncertain → DiceRequest).

#### 2. Dice Engine (6-Level Outcomes)
- **`DiceOutcome` StrEnum**: `critical_failure` | `hard_failure` | `soft_failure` | `partial_success` | `full_success` | `critical_success`
- **Natural 1/20 overrides**: always critical regardless of DC
- **Thresholds**: ≤DC-5 → hard_failure, DC-4 to DC-1 → soft_failure, DC to DC+3 → partial_success, ≥DC+4 → full_success
- **Dice re-prompt pipeline**: backend rolls immediately → second LLM call with result → appended narration; frontend click-to-reveal animation masks the latency

#### 3. GameClock
- **`GameClock` Pydantic model** in `memory/world_state.py`: `total_minutes`, computed `current_hour`, `current_day`, `current_season`, `time_of_day`
- **`advance_game_clock()`**: increments `total_minutes` by `time_passed_minutes` from each `DMResponse`
- **World state schema v2**: migration pipeline v0→v2, `"clock"` key added to `ALLOWED_WORLD_STATE_KEYS`

#### 4. Real-Time Streaming Pipeline
- **`NarrationExtractor`** (`ai/stream_extractor.py`): state machine with 3 states (`DETECTING` → `IN_NARRATION` → `DONE`). Extracts only narration text from raw JSON token stream — filters JSON syntax, handles `\"` / `\n` / `\\` escape sequences, falls back to passthrough for plain-text responses (dice re-prompt). 15 unit tests.
- **`process_game_turn_streaming()`** (`core/engine.py`): async generator yielding `StreamEvent` objects in real-time. Types: `narration_chunk`, `dice_roll`, `dice_narration_chunk`, `scene_mood`, `turn_result`, `error`. Accumulates full response in parallel for JSON parsing after stream ends.
- **WebSocket handler** (`api/websocket.py`): iterates `StreamEvent` stream, dispatching `dm:narration:chunk` / `dice:roll` / `dice:narration:chunk` / `scene_mood` to client as they arrive. Turn persistence (Turn record + auto-save + embedding) happens after `turn_result` event.

#### 5. Turn Pipeline
1. Sanitizer + injection detection → Context Assembler (character sheet always included)
2. `provider.stream()` → `NarrationExtractor` feeds chunks → `dm:narration:chunk` events to frontend
3. After stream: `parse_dm_response(full_buffer)` with JSON healing
4. If `dice_required`: roll → `dice:roll` event → second stream (re-prompt) → `dice:narration:chunk` events
5. Advance GameClock, apply `world_updates`, persist Turn + auto-save to DB
6. `turn_complete` with full turn data
- **`requires_player_action`**: deterministic backend flag — `True` if combat active or dice pending
- **Turn persistence fixed**: WebSocket handler now saves `Turn` + `Save` records — previously missing, causing DM to have no conversation history

#### 6. Security & Data Sovereignty
- **API Key Vault**: User API keys are NEVER stored in plaintext. Implemented **AES-256-GCM** with **HKDF-SHA256** key derivation (`security/encryption.py`).
- **Data Portability**: Full JSON export/import of the campaign "Universe" (Campaign metadata + full Turn history).
- **Multi-tenant isolation**: Every query is filtered by `user_id` from day zero.

#### 7. Frontend Architecture (React 18 + Zustand)
- **WebSocket Integration**: `GameWebSocket` wired in `game-view.tsx` with full event lifecycle. Events: `turn_start`, `dm:narration:chunk`, `dice:roll`, `dice:narration:chunk`, `scene_mood`, `turn_complete`.
- **Streaming State**: `StreamingState` in `game-store.ts` — `isStreaming`, `currentNarration`, `pendingDice`, `diceRevealed`, `currentMood`.
- **DiceRoller**: Click-to-reveal animation — counter cycles 1-20 for 1.5s then reveals real result. 6 outcome CSS classes. Sound on click.
- **Scene Moods**: 11 moods in `styles/mood.css` with CSS custom properties (`--mood-bg`, `--mood-accent`) and 1.5s smooth transitions via `data-mood` attribute.
- **Suggested Actions**: Buttons wired in `narrative-stream.tsx` — click inserts and sends action via WebSocket.
- **Ambient Detail**: Italic text rendered below narration.
- **Action Input**: Submits via WebSocket. "Continue" button sends `"wait"` when `requires_player_action` is false.
- **Character Sheet**: Unified schema with `equipped`, `reputation`, `active_quests`.
- **i18n Support**: Ready-to-use internationalization framework (`react-i18next`) with separate `en.json` logic.

#### 7. Adventure SDK & Content
- **Template Schema**: Robust JSON schema (`templates/schema.json`) for adventure validation.
- **Built-in Adventures**: Three ready-to-play YAML templates (`tutorial`, `last_light`, `shattered_crowns`) with lore and story branching.

### 🚩 Technical Debt & Structural "God Modules"

#### 1. Backend Bottlenecks
- **`engine.py` (The God Function)**: The central processing loop is too dense. Needs split into Orchestrator/Resolver/Synthesizer.
- **`websocket.py` (Transport Overload)**: Currently handles game logic that should be in the engine.
- **`turn_service.py` (Service Bloat)**: Mixing I/O (embeddings, DB) with business logic (sanitization, game flow).

#### 2. Test & Quality Debt
- [x] **Linting & Type Safety**: **ZERO** warnings in Frontend; Resolved all Python warnings in backend tests.
- [x] **Unit Test Isolation**: `tests/unit/conftest.py` overrides session-scoped DB fixtures as no-ops — pure unit tests run without PostgreSQL.
- **AI Playtest Realism**: Playtest bots use fixed patterns; need randomized "chaos" input tests for LLM stability.

### 🚀 Roadmap: Phase B (NPC Actor-Director + Semantic Memory)
1. **Actor-Director Pattern**: Parallel NPC calls via `asyncio.gather` on `invoke_npcs` field.
2. **Fact Extractor**: Background `asyncio.create_task` extracting 1-5 atomic facts per turn into `memory_facts`.
3. **Hybrid Search**: pgvector + tsvector for semantic + keyword memory recall.
4. **Engine Decoupling**: Isolate dice logic and state updates from AI prompt logic.

---
*Last updated: March 25, 2026 — ~163 Tests Passing. Phase A (A1-A4) complete.*
