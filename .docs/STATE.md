# Project State of the Art (STATE.md)

## Current Snapshot: Phase A+B+C+Sprint1+Sprint2 Complete
**239 unit tests passing.** The backend streams LLM tokens in real-time, combat and death systems are functional, all critical playtest bugs from Sprint 1–2 are resolved. The engine has been refactored into 3 clean files (Rule 12 compliance). The frontend now shows chat history on reload, user message bubbles, auto-scroll, and persists world state correctly between turns.

*Last updated: 2026-03-31*

---

### ✅ Core Implementations (Verified & Stable)

#### 1. AI Orchestration & Logic
- **AI Router** (`ai/router.py`): Multi-provider (OpenAI, Anthropic, Google), importance tiering (High/Mid/Low), YAML config override, env var overrides (`SAGA_GLOBAL_MODEL_HIGH`, etc.).
- **Semantic Resolver** (`ai/semantic_resolver.py`): Mini-call before Context Assembler. Resolves pronouns and implicit references → `ResolverOutput(target_npcs, target_locations, time_estimate_minutes)`.
- **Healing Parser** (`ai/parser.py`): strip markdown fences → `json-repair` → Pydantic validation → `DMResponse`. Reduces retries ~70%.
- **Content Policy Handler**: Per-provider detection (OpenAI `content_filter`, Anthropic empty, Google `SAFETY`) → `ContentPolicyError` → readable fallback narration.
- **DM Prompt** (`ai/prompts/dm.py`): Full COMBAT_PROMPT, world_updates array format with examples, no creation mode (removed), rules for code fences, player agency, prompt injection defense, dice frequency, combat_start once.
- **Model config**: All providers set to `google` / `gemini-3-flash-preview` in `model_config.yaml`.

#### 2. Turn Pipeline — 3 files (engine split, Rule 12)
- **`core/engine.py`** (50 lines): `ProcessedTurn`, `StreamEvent` dataclasses + constants.
- **`core/turn.py`** (177 lines): `process_game_turn()` — non-streaming pipeline.
- **`core/streaming.py`** (294 lines): `process_game_turn_streaming()` — streaming pipeline with `NarrationExtractor`, dice re-prompt, NPC Actor-Director, death check, typed world updates.
- **AI request logging**: `ai_request` log before every LLM call (provider, model, temperature, importance, system_prompt_preview, messages_count).
- **AI response logging**: `ai_raw_response` log after every response.

#### 3. Dice Engine (6-Level Outcomes)
- `DiceOutcome` StrEnum: `critical_failure` → `critical_success`.
- Natural 1/20 overrides. Advantage/disadvantage. Re-prompt pipeline.
- Rolls computed server-side, animation client-side (click-to-reveal).

#### 4. GameClock
- `GameClock` Pydantic model: `total_minutes`, computed `current_hour/day/season/time_of_day`.
- `advance_game_clock()` increments from `time_passed_minutes` per turn.
- World state schema v4 with migration pipeline v0→v4.

#### 5. Real-Time Streaming
- `NarrationExtractor` state machine (`ai/stream_extractor.py`): extracts narration tokens from raw JSON stream in real time.
- WebSocket handler (`api/websocket.py`): iterates `StreamEvent`, dispatches typed WS events. `player_action` now included in `turn_complete` payload. Wrapped in try/except guards.

#### 6. World State & Typed Updater
- **11 handlers** in `memory/updater.py`: `npc_disposition`, `hp_change`, `inventory_change`, `quest_update`, `companion_loyalty`, `reputation_change`, `event_log_entry`, `combat_start`, `combat_end`, `combat_damage`, **`location`** (new, Sprint 2).
- `combat_damage`: name-match fallback for generic targets ("player"/"playername"), auto-advance `current_turn_index` after each damage (Sprint 2).
- Generic fallback for unknown types.

#### 7. HP Format
- Standardized to nested `{"current": N, "max": N}` everywhere — creation, updater, death check, frontend, character service.

#### 8. Death System (`core/death.py`)
- Ironman: death permanent, `campaign.status = COMPLETED`.
- Destino: 3 fate interventions with escalating costs (Minor/Major/Severe), `destino_lives` in world state.
- Cronista: HP reset to 1, narrative near-death consequences.
- `DEATH_MODE_PROMPTS` injected in system prompt.

#### 9. Combat System
- Initiative: d20 + DEX modifier, sorted descending, stored in `combat_state`.
- `combat_start` handler: rolls initiative, builds `initiative_order`.
- `combat_damage` handler: applies to player or enemy combatant.
- `combat_end` handler: resets `combat_state.active = false`.

#### 10. Character Creation (UI Form, no AI)
- 3-step `new-campaign.tsx`: template → hero name + death mode → character form.
- 6 class presets in `character_service.py` (`CLASS_PRESETS`): warrior, rogue, mage, ranger, cleric, bard.
- HP computed from CON modifier: `BASE_HP + (con - 10) // 2`.
- Full `character_data` built client-side, sent to backend at campaign creation.

#### 11. Memory System
- **Active Window**: configurable, default 8 turns verbatim, older turns compressed.
- **Turn Compression** (`memory/compressor.py`): batches of 5 turns, budget model summary.
- **Fact Extractor** (`memory/fact_extractor.py`): fire-and-forget `asyncio.create_task` after turn commit. Handles list output and empty response (Sprint 1 fix).
- `memory_facts` table with embedding (Vector 384) + tsvector index.

#### 12. Logging (`logging_setup.py`)
- Structlog dual output: console (ConsoleRenderer key=value) + rotating file JSON lines (`logs/saga.log`, 10MB × 3 backups).
- `ai_request` log before every AI call with full context preview.
- `location_updated` log when location changes.

#### 13. Security
- AES-256-GCM encryption for API keys.
- `detect_injection()` + `sanitize_player_input()` in websocket handler.
- JWT auth, cascade delete, multi-tenant isolation.

#### 14. Frontend — Game View
- **Chat history**: hydrated from `campaign.turns` on mount (Sprint 2, `setTurnHistory`).
- **User message bubbles**: `pendingAction` shown immediately as gold bubble before DM responds, `player_action` shown in historical turns (Sprint 2).
- **Auto-scroll**: `bottomRef` + `scrollIntoView` on narration/turn updates (Sprint 2).
- **Dice below narration**: `DiceRoller` moved after narration text in both TurnBlock and streaming (Sprint 2).
- **WebSocket isMounted guard**: all handlers wrapped in `guard()`, cleanup sets `isMountedRef.current = false` (Sprint 2).
- **Error handler**: `ws.on("error")` resets `isProcessing`/`isStreaming` (Sprint 2).
- **Back button**: `←` in header, `useNavigate` to `/` (Sprint 2).
- **Season**: `world_state.meta.current_season` shown in header (Sprint 2).
- **world_state + character_data** synced from `turn_complete` via `updateWorldState` / `updateCharacter`.
- **CombatTracker** reads from `campaign.world_state.combat_state` (persistent, survives `resetStreaming`).
- **CharacterSheet** with HP normalization helper `getHP()` for nested/flat format.
- **DiceRoller**: click-to-reveal, 1.5s counter animation, 6 outcome CSS classes, sound.
- **Scene moods**: 11 moods in CSS, 1.5s smooth transitions.
- **ActionInput**: suggested actions only on last turn, "Continue" button for auto-continue.
- **Death overlays**: Near Death / Fate Intervenes / You Have Fallen.
- **New Campaign** (3 steps): template → hero name → character creation form.

#### 15. Save System
- `POST /api/campaigns/:id/saves` — manual save endpoint.
- Auto-save after every turn (overwrite single slot per campaign).
- Save blocked during active combat.
- `POST /api/campaigns/:id/saves/:save_id/load` — fork endpoint.

#### 16. Export/Import
- Full JSON export of campaign + turns.

---

### ⚠️ Partial / Needs Playtest Validation
- Hybrid Search (pgvector + tsvector query) — table and indexes ready, query not implemented (Phase E)
- Contextual Loading guided by Semantic Resolver — resolver works, selective loading deferred (Phase E)
- DM sometimes doesn't emit combat_damage spontaneously — monitor with log file
- B4 Template System — templates work partially, full system deferred (Phase E)

---

### ❌ Not Started
- pgvector Hybrid Search query (`memory/semantic.py`)
- Recap System (dual role: system prompt + JournalView)
- API Keys UI (frontend settings panel)
- Cost Dashboard
- Second and third templates (The Shattered Crowns, The Last Light)
- CI/CD (GitHub Actions)
- Responsive / Mobile / PWA
- Achievement System
- Save Browser UI
- Timeline Forking UI
- World Simulator logic (schema exists, logic in v2)
- **Phase D: Agentic DM** (tool-calling architecture — planned next)

---

### 🚩 Technical Debt
- `websocket.py` (~236 lines) — mixes game logic with transport; consider moving turn orchestration to a service layer (Phase E)
- `turn_service.py` — mixes I/O with business logic (Phase E)
- Hybrid search not yet wired despite table being ready
- Frontend: no Vitest/RTL tests yet (structure in place)
