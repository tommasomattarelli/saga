# Project State of the Art (STATE.md)

## Current Snapshot: Sprint v1 Complete — Agentic DM
**309 tests passing** (unit + integration). The agentic DM loop is live: world state is seeded from templates, tools are filtered per-turn, NPCs have profiles from the template, the system prompt is XML-structured. The "wrapper around LLM" feeling is eliminated for new campaigns.

*Last updated: 2026-04-07*

---

## ✅ Sprint v1 — New Features (2026-04-07)

### 1. Template World Initialization
- `campaign_service.create_campaign()` seeds `world_state` from `template.content` at creation time
- YAML template → `locations`, `npcs`, `companions`, `factions` dicts; `meta.current_location`, `time_of_day`, `weather` from `opening`
- `campaign.quests` seeded from `template.content.opening.initial_quests`
- `migrate_world_state()` applied after seeding (idempotent, ensures schema v4, clock, combat_state, destino_lives)
- Unknown template slug → 404 with `detail: "Template '...' not found"`

### 2. DELETE /campaigns/{id}
- Ownership check: 403 if not owner, 404 if missing
- ORM cascade deletes turns; DB cascade deletes memory_facts
- Use for test data cleanup

### 3. saga.config.yaml (project root)
- Single root-level game-tunable config merging old `model_config.yaml` (deleted)
- Sections: `model_routing` (dm_narration low/medium/high, npc_behavior, companion_dialogue, memory_compression, embedding), `gameplay`, `features`, `tool_groups`
- `backend/app/config_loader.py` — `load_saga_config()` with `@lru_cache(maxsize=1)`
- `backend/app/ai/router.py` reads from `load_saga_config()` instead of file path
- `backend/app/ai/model_config.yaml` deleted

### 4. Dynamic Tool Groups
- `backend/app/ai/tools/tool_groups.py` — typed Python predicates, no eval
- `resolve_active_tools(campaign) -> set[str]` reads `saga.config.yaml` `tool_groups` section
- Predicates: `combat_active` (checks `combat_state.active`), `npcs_present` (checks `npcs` dict), `companion_active`
- Groups: `core` (always: move_to, advance_time, set_scene_mood, log_event, update_quest), `combat` (when: combat_active), `social` (when: npcs_present), `inventory` (always)
- `get_tool_schemas(allowed: set[str] | None)` filters tool list per turn
- Reduces tool count: ~9 out of combat, ~14 during combat

### 5. NPC Pre-Hook
- `_run_npc` in `agent.py` guards against NPCs not in `world_state.npcs`
- Unknown NPC → returns error string to DM: "NPC '...' is not defined in this world. Do not invoke them."
- `last_interactions` ring buffer (max 3) stored in `world_state.npcs[name].last_interactions` after each NPC invocation
- `npc.py` prompt builder handles both flat strings (template) and dict format (legacy personality/goals)

### 6. Location Post-Hook
- `MoveTo.execute` enriches tool result with `description` + `connections` from `world_state.locations`
- DM receives: `"Player moved to: X\nDescription: ...\nConnected to: ..."` instead of bare `"moved to X"`
- Updates `world_state.meta.current_location` on move

### 7. XML System Prompt
- `build_dm_system_prompt()` emits XML structure: `<instructions>`, `<character>`, `<scene>`, `<history>`, `<quests>`
- `<scene>` includes: `<location>` (description + connections), `<npcs_present>` (filtered to current location only), `<time>`, `<weather>`, `<combat>` (only when active)
- No `json.dumps(world_state)` anywhere — estimated 40-60% token reduction on populated campaigns
- `_npcs_at_current_location(world_state)` filters by `npc.location == meta.current_location`; returns all NPCs if no location set (fallback)

---

## ✅ Phase D — Agentic DM Architecture (2026-04-03)

- **`core/agent.py`** — `DmAgent.run()` agentic loop (max 5 steps), streams narration + tool calls
- **Tool execution**: regular tools parallel (`asyncio.gather`), special tools sequential (`request_dice`, `invoke_npc`)
- **`ai/tools/dm_tools.py`** — 14 typed tools, each as `ToolDef` class with `openai_schema()` + `execute()`
- **`api/websocket.py`** — WebSocket handler dispatches `StreamEvent` types to frontend
- **Dice flow**: server-side roll → `dice_roll` event → `await_player` pause → player clicks → `dice_revealed` message → DM continues
- **NPC director**: parallel NPC invocations via `invoke_npcs_parallel`, returns `NPCResult` per NPC
- **Semantic resolver**: mini-LLM call before turn to resolve implicit references

---

## ✅ Previous Phases (A-C, Sprint 1-2)

- **AI Router**: multi-provider, importance tiering, env var overrides
- **Memory system**: active window (8 turns), turn compression, fact extractor, pgvector embeddings
- **Death system**: Ironman / Destino / Cronista modes
- **Combat system**: initiative, apply_damage, end_combat
- **Character creation**: 3-step UI, 6 class presets
- **Frontend**: streaming chat, dice click-to-reveal, CombatTracker, CharacterSheet, scene moods, auto-scroll, history on reload, death overlays, save/load, export/import
- **World state**: schema v4, migration pipeline v0→v4, GameClock
- **Security**: AES-256-GCM API key encryption, JWT auth, injection detection

---

## 🚩 Technical Debt

### Dead Code (safe to delete)
| File | Lines | Why dead |
|------|-------|----------|
| `backend/app/core/streaming.py` | 294 | Not imported anywhere in `app/`; frontend uses WebSocket→agent, not this pipeline |
| `backend/app/core/stream_extractor.py` | ~80 | Only used by dead `streaming.py` |
| `backend/app/ai/prompts/companion.py` | ~40 | Not imported in `app/`; only referenced in tests |
| `backend/app/ai/prompts/world.py` | ~30 | Not imported in `app/`; only referenced in tests |

### Dual Pipeline (tech debt, not dead)
- HTTP `POST /turn` → `turn_service.py` → `core/turn.py` → old non-agentic pipeline
- WebSocket → `agent.py` → current agentic pipeline (what frontend uses)
- `core/turn.py` and `turn_service.py` are still live (endpoint exists, some integration tests use it)
- Should be retired once old HTTP pipeline tests are migrated to WebSocket tests

### Size Violations (Rule 12: ≤300 lines)
| File | Lines | Action |
|------|-------|--------|
| `backend/app/core/agent.py` | 452 | Split into `agent_loop.py` (streaming loop), `agent_tools.py` (tool executors), `agent_dice.py` (dice handling) |
| `backend/app/core/streaming.py` | 294 | Delete (dead) |

### Other
- `backend/app/ai/model_config.yaml` — **deleted** in v1; if referenced anywhere → error (intentional)
- `dm_response.py` — `DMResponse` Pydantic schema used by old pipeline only; can delete when old pipeline retired

---

## 🗺️ Future Steps

### v1.5 — World Depth (next sprint)
- **Global story summary**: rule-based (every 5 turns) + LLM hybrid compression. Currently `features.global_summary.enabled: false` in saga.config.yaml
- **`suggest_actions` tool**: re-add as proper tool call (removed from `DMResponse`, not yet re-added)
- **NPC location filtering**: already have `npc.location` in template YAML; need `_npcs_at_current_location` wired into `social` tool group predicate so `invoke_npc` only shows NPCs at current location
- **NPC movement types**: `static` (stay in place), `wandering` (move every N turns via world_sim), `scheduled` (scripted routes)
- **Companion dialogue tools**: `ask_companion`, `command_companion` — companion in `world_state.companions` but no tools yet
- **Narrative tension score**: track escalation across turns, influence model temperature
- **Refactor `agent.py`**: split 452-line file into 3 focused modules (Rule 12)
- **Delete dead files**: `streaming.py`, `stream_extractor.py`, `companion.py` prompt, `world.py` prompt

### v2 — Living World
- **World Simulator**: NPC agents that move, plot, and react to player actions between turns (currently `features.world_sim.enabled: false`)
- **Faction dynamics**: reputation changes trigger faction events
- **Second/third templates**: The Shattered Crowns, The Last Light
- **Hybrid search**: pgvector + tsvector wired in `memory/semantic.py` (table + indexes ready, query not implemented)
- **Player journal**: auto-generated turn summaries in JournalView
- **Recap system**: compressed history shown in UI + injected as `<history>` in prompt

### v3 — Platform
- **Multiplayer**: shared campaigns, spectator mode
- **API Keys UI**: frontend settings panel for provider keys
- **CI/CD**: GitHub Actions (lint + test on push)
- **Mobile/PWA**: responsive layout
- **Achievement system**, Save Browser UI, Timeline Forking UI
- **Cost Dashboard**: token usage tracking per campaign

---

## ⚠️ Partial / Needs Validation
- `suggest_actions` removed from `DMResponse` but not yet re-added as tool — buttons don't appear in frontend
- HTTP `/turn` endpoint still active but uses stale pipeline (not tested in playtest guide)
- NPC `wandering` / `scheduled` movement type field exists in YAML spec but predicate not implemented
- pgvector hybrid search table+indexes ready, `memory/semantic.py` query not wired

---

## 📋 Test Coverage
```
309 tests — unit + integration (as of Sprint v1)
New in v1:
  tests/integration/test_campaign_creation.py   (3 tests — template seeding)
  tests/integration/test_campaign_delete.py      (4 tests — cascade, auth)
  tests/unit/test_tool_groups.py                 (8 tests — predicate resolver)
  tests/unit/test_dm_prompt_xml.py               (13 tests — XML structure)
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/unit tests/integration -q`
