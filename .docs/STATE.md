# Project State of the Art (STATE.md)

## Current Snapshot: Phase A+B Complete
The project has completed two major phases: Phase A ("Da chatbot a gioco") and Phase B ("World che vive"). We have **198 unit tests passing**. The backend streams LLM tokens in real-time, NPC respond independently via the Actor-Director pattern, memory compresses automatically, and facts are extracted in background after each turn.

### 💎 Core Implementations (Verified & Stable)

#### 1. AI Orchestration & Logic
- **Advanced AI Router**: Implemented in `ai/router.py`. Supports:
    - **Multi-provider**: OpenAI, Anthropic, Google Gemini.
    - **Importance Tiering**: Dynamically selects models (High/Medium/Low) based on scene importance score (0-10).
    - **Override Hierarchy**: YAML defaults -> Global Settings -> Env vars (e.g., `SAGA_MODEL_DM_NARRATION_HIGH`).
    - **Gameplay Config**: `get_gameplay_config()` reads `gameplay` section from `model_config.yaml` with env var overrides (`SAGA_GAMEPLAY_*`).
- **Semantic Resolver** (`ai/semantic_resolver.py`): Mini-call to budget model before Context Assembler. Resolves implicit references ("her" → "Grenda", "the nearby city" → "Neverwinter") using session context (companions, locations, recent NPCs). Returns `ResolverOutput(target_npcs, target_locations, time_estimate_minutes)`.
- **Structured DM Parser**: Pydantic-validated `DMResponse` schema (`ai/schemas/dm_response.py`) with JSON healing (`json-repair`). Pipeline: strip markdown fences → `repair_json()` → `json.loads()` → `DMResponse.model_validate()` → fallback narration. Reduces retries by ~70%.
- **Content Policy Handler**: Per-provider detection — OpenAI `content_filter`, Anthropic empty response, Google `SAFETY`. All raise `ContentPolicyError` → engine returns readable fallback narration to player.
- **Creation Mode**: Engine detects empty `character_data` → uses dedicated `CREATION_MODE_PROMPT`. DM generates stats via `character_generation` field → saved to campaign automatically.
- **Updated DM Prompt**: Full prompt with all 11 `scene_mood` values, `invoke_npcs`, `time_passed_minutes` guide values (dialogue 1-5, exploration 10-30, travel 30-480), dice rules (trivial → null, impossible → null, uncertain → DiceRequest). Includes "Story So Far" section from compressed turn summaries.

#### 2. Dice Engine (6-Level Outcomes)
- **`DiceOutcome` StrEnum**: `critical_failure` | `hard_failure` | `soft_failure` | `partial_success` | `full_success` | `critical_success`
- **Natural 1/20 overrides**: always critical regardless of DC
- **Thresholds**: ≤DC-5 → hard_failure, DC-4 to DC-1 → soft_failure, DC to DC+3 → partial_success, ≥DC+4 → full_success
- **Dice re-prompt pipeline**: backend rolls immediately → second LLM call with result → appended narration; frontend click-to-reveal animation masks the latency

#### 3. GameClock
- **`GameClock` Pydantic model** in `memory/world_state.py`: `total_minutes`, computed `current_hour`, `current_day`, `current_season`, `time_of_day`
- **`advance_game_clock()`**: increments `total_minutes` by `time_passed_minutes` from each `DMResponse`
- **World state schema v3**: migration pipeline v0→v3, adds `clock`, `npcs`, `companions`, `narrative` keys

#### 4. Real-Time Streaming Pipeline
- **`NarrationExtractor`** (`ai/stream_extractor.py`): state machine with 3 states (`DETECTING` → `IN_NARRATION` → `DONE`). Extracts only narration text from raw JSON token stream — filters JSON syntax, handles `\"` / `\n` / `\\` escape sequences, falls back to passthrough for plain-text responses (dice re-prompt). 15 unit tests.
- **`process_game_turn_streaming()`** (`core/engine.py`): async generator yielding `StreamEvent` objects in real-time. Types: `narration_chunk`, `dice_roll`, `dice_narration_chunk`, `scene_mood`, `npc_dialogue`, `turn_result`, `error`. Accumulates full response in parallel for JSON parsing after stream ends.
- **WebSocket handler** (`api/websocket.py`): iterates `StreamEvent` stream, dispatching `dm:narration:chunk` / `dice:roll` / `dice:narration:chunk` / `scene_mood` / `npc:dialogue` to client as they arrive. Turn persistence (Turn record + auto-save + embedding) happens after `turn_result` event. Fires background tasks for fact extraction and turn compression after commit.

#### 5. Turn Pipeline
1. Sanitizer + injection detection → **Semantic Resolver** (resolve implicit references) → Context Assembler (character sheet + compressed summaries always included)
2. `provider.stream()` → `NarrationExtractor` feeds chunks → `dm:narration:chunk` events to frontend
3. After stream: `parse_dm_response(full_buffer)` with JSON healing
4. If `dice_required`: roll → `dice:roll` event → second stream (re-prompt) → `dice:narration:chunk` events
5. **NPC Actor-Director**: if `invoke_npcs` present → parallel LLM calls via `asyncio.gather` → `npc:dialogue` events → disposition changes applied immediately
6. Advance GameClock, apply `world_updates` (typed handlers + generic fallback), persist Turn + auto-save to DB
7. **Background tasks**: `extract_and_store_facts()` + `ensure_compression()` fired as `asyncio.create_task` after commit
8. `turn_complete` with full turn data including NPC dialogues
- **`requires_player_action`**: deterministic backend flag — `True` if combat active or dice pending
- **Turn persistence fixed**: WebSocket handler now saves `Turn` + `Save` records — previously missing, causing DM to have no conversation history

#### 6. NPC Actor-Director System (Phase B)
- **Actor-Director Pattern**: DM is the Director (decides who speaks via `invoke_npcs`), NPCs are independent Actors with their own LLM calls.
- **`npc_director.py`**: `invoke_npcs_parallel()` launches budget model calls via `asyncio.gather`, capped by `npc_verbosity` config (null=0, minimal=1, low=2, medium=3, high=5, unlimited=999).
- **`NPCDialogue` dataclass**: `npc_name`, `dialogue`, `action`, `disposition_change`, `reveals_secret`.
- **NPC Profile Schema** (`memory/schemas.py`): `NPCProfile` Pydantic model with `NPCPersonality` (traits, values, fears, secrets), `disposition_toward_player` (clamped -100 to +100), `goals`, `memory`. `CompanionProfile` extends with `loyalty` (clamped 0-100), `personal_quest_stage`, `opinions`, `combat_style`, `backstory_hooks`.
- **Disposition changes** applied immediately to `world_state["npcs"]` via typed updater after each NPC dialogue.
- **NPC dialogues appended** to turn narration for persistence.

#### 7. Memory & Compression System (Phase B)
- **Typed World State Updater** (`memory/updater.py`): Handler registry with `@_register_handler` decorator. 7 handlers: `npc_disposition`, `hp_change`, `inventory_change`, `quest_update`, `companion_loyalty`, `reputation_change`, `event_log_entry`. Unknown types fall back to generic `merge_world_state()`.
- **Fact Extractor** (`memory/fact_extractor.py`): Fire-and-forget `asyncio.create_task` after turn commit. Budget LLM extracts 1-5 atomic facts → stored in `memory_facts` table with embeddings (`text-embedding-3-small`). Uses independent DB session.
- **`MemoryFact` model** (`models/memory_fact.py`): `campaign_id`, `turn_number`, `entity_name`, `entity_type` (npc/location/quest/item/event/secret), `content`, `embedding` (Vector 384), `search_vector` (TSVECTOR). GIN index on `search_vector`, composite index on `(campaign_id, entity_name)`.
- **Active Window**: Configurable via `context_window_turns` (default 8). Last N turns loaded verbatim in context.
- **Turn Compression** (`memory/compressor.py`): Turns beyond the Active Window are compressed via budget LLM into 2-3 sentence summaries (batches of 5). Summaries replace verbatim turns — constant token budget (~4000 tokens for memory). Heuristic fallback if LLM disabled.
- **Context Assembler** (`ai/context.py`): Loads compressed summaries as "Story So Far" section in system prompt. Deduplicates batch summaries.
- **Gameplay Config** in `model_config.yaml`: `context_window_turns`, `npc_verbosity`, `compression_enabled`, `fact_extraction_enabled`. All overridable via `SAGA_GAMEPLAY_*` env vars.

#### 8. Security & Data Sovereignty
- **API Key Vault**: User API keys are NEVER stored in plaintext. Implemented **AES-256-GCM** with **HKDF-SHA256** key derivation (`security/encryption.py`).
- **Data Portability**: Full JSON export/import of the campaign "Universe" (Campaign metadata + full Turn history).
- **Multi-tenant isolation**: Every query is filtered by `user_id` from day zero.

#### 9. Frontend Architecture (React 18 + Zustand)
- **WebSocket Integration**: `GameWebSocket` wired in `game-view.tsx` with full event lifecycle. Events: `turn_start`, `dm:narration:chunk`, `dice:roll`, `dice:narration:chunk`, `scene_mood`, `npc:dialogue`, `turn_complete`.
- **Streaming State**: `StreamingState` in `game-store.ts` — `isStreaming`, `currentNarration`, `pendingDice`, `diceRevealed`, `currentMood`.
- **DiceRoller**: Click-to-reveal animation — counter cycles 1-20 for 1.5s then reveals real result. 6 outcome CSS classes. Sound on click.
- **Scene Moods**: 11 moods in `styles/mood.css` with CSS custom properties (`--mood-bg`, `--mood-accent`) and 1.5s smooth transitions via `data-mood` attribute.
- **Suggested Actions**: Buttons wired in `narrative-stream.tsx` — click inserts and sends action via WebSocket.
- **Ambient Detail**: Italic text rendered below narration.
- **Action Input**: Submits via WebSocket. "Continue" button sends `"wait"` when `requires_player_action` is false.
- **Character Sheet**: Unified schema with `equipped`, `reputation`, `active_quests`.
- **i18n Support**: Ready-to-use internationalization framework (`react-i18next`) with separate `en.json` logic.

#### 10. Adventure SDK & Content
- **Template Schema**: Robust JSON schema (`templates/schema.json`) for adventure validation.
- **Built-in Adventures**: Three ready-to-play YAML templates (`tutorial`, `last_light`, `shattered_crowns`) with lore and story branching.

### 🚩 Technical Debt & Structural Issues

#### 1. Backend
- **`engine.py` (The God Function)**: The central processing loop is dense. Needs split into Orchestrator/Resolver/Synthesizer.
- **`websocket.py` (Transport Overload)**: Currently handles game logic that should be in the engine.
- **`turn_service.py` (Service Bloat)**: Mixing I/O (embeddings, DB) with business logic (sanitization, game flow).

#### 2. Test & Quality
- [x] **Linting & Type Safety**: ZERO warnings in Frontend; Resolved all Python warnings in backend tests.
- [x] **Unit Test Isolation**: `tests/unit/conftest.py` overrides session-scoped DB fixtures as no-ops — pure unit tests run without PostgreSQL.
- **AI Playtest Realism**: Playtest bots use fixed patterns; need randomized "chaos" input tests for LLM stability.

#### 3. Phase B Gaps
- **Hybrid Search** (pgvector + tsvector): `memory_facts` table and `search_vector` column exist but hybrid search query not yet implemented (planned for Phase D).
- **Contextual Loading**: Context Assembler doesn't yet use Semantic Resolver output for selective NPC/location loading — loads full context always.
- **Template System (B4)**: Moved to Phase D — templates already work partially.

### 🚀 Roadmap: Phase C (Combat + Death Modes)
1. **Combat Tracker**: Turn-based initiative, HP bars, action economy.
2. **Death Modes**: Ironman / Destino / Cronista.
3. **Combat AI**: Enemy behavior, flee/surrender logic.
4. **HP/Inventory live updates**: Frontend reflects combat changes in real-time.

---
*Last updated: March 26, 2026 — 198 Tests Passing. Phase A (A1-A4) + Phase B (B0-B3) complete.*
