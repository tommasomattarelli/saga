# FASE 2 — Piano B: "World che vive"

> Tutte le modifiche apportate nella Fase B del progetto SAGA/Wyrd.
> Data: 2026-03-26
> Test: 174 → 198 passing (198 unit)

---

## Sommario

La Fase B trasforma il mondo di SAGA da statico a vivente. Il backend acquisisce: NPC Actor-Director con call LLM parallele, Semantic Resolver per riferimenti impliciti, typed World State Updater con handler registry, Fact Extractor background per fatti atomici, Active Window configurabile con compressione LLM, NPCProfile e CompanionProfile Pydantic, tabella `memory_facts` con pgvector, e configurazione gameplay in `model_config.yaml`.

---

## Added

### Backend — Nuovi file

#### `backend/app/ai/semantic_resolver.py`
Semantic Resolver — mini-call a budget model per risolvere riferimenti impliciti nel testo del player.

- `ResolverOutput(BaseModel)`: `target_npcs: list[str]`, `target_locations: list[str]`, `time_estimate_minutes: int`
- `resolve_player_action(action, campaign, db)`: estrae contesto dalla campagna (companions, locations, NPCs dal world_state), prompt al budget model via `route_ai_call(AICallType.NPC_BEHAVIOR)`, fallback a `ResolverOutput()` vuoto su errore.
- Integrato nel pipeline streaming prima di `build_context()`.

#### `backend/app/ai/npc_director.py`
NPC Actor-Director — sistema di call LLM parallele per NPC indipendenti.

- `NPCDialogue` dataclass: `npc_name`, `dialogue`, `action`, `disposition_change`, `reveals_secret`.
- `invoke_single_npc()`: singola call budget LLM per un NPC, con prompt da `build_npc_prompt()`.
- `invoke_npcs_parallel()`: lancia call NPC in parallelo via `asyncio.gather`, capped da `get_gameplay_config().max_npc_calls`.
- `format_npc_dialogues_for_turn()`: formatta dialoghi per append alla narrazione del turno.
- Fallback: se call fallisce, ritorna `NPCDialogue` con dialogo generico.

#### `backend/app/memory/schemas.py`
Pydantic models per NPC e Companion profiles.

- `NPCPersonality(BaseModel)`: `traits`, `values`, `fears`, `secrets` (tutti `list[str]`).
- `NPCProfile(BaseModel)`: `name`, `role`, `location`, `personality: NPCPersonality`, `disposition_toward_player` (clamped -100 to +100 via validator), `goals`, `memory`. `model_config = {"extra": "allow"}`.
- `CompanionProfile(NPCProfile)`: estende con `loyalty` (clamped 0-100), `personal_quest_stage`, `opinions: dict[str, str]`, `combat_style`, `backstory_hooks`.

#### `backend/app/memory/updater.py`
Typed World State Updater — handler registry per update strutturati.

- `_HANDLERS` dict con `@_register_handler` decorator.
- 7 handler: `npc_disposition`, `hp_change`, `inventory_change`, `quest_update`, `companion_loyalty`, `reputation_change`, `event_log_entry`.
- `apply_typed_updates(world_state, character_data, updates)`: applica update tipizzati, fallback a `merge_world_state()` per tipi sconosciuti. Returns `(updated_world_state, updated_character_data)`.
- `apply_typed_updates_to_campaign(campaign, updates, db)`: wrapper per applicazione diretta a campaign con flush.

#### `backend/app/memory/fact_extractor.py`
Background Fact Extractor — estrae fatti atomici da ogni turno.

- `FACT_EXTRACTION_PROMPT`: prompt per budget model, estrae 1-5 fatti atomici.
- `extract_and_store_facts(campaign_id, turn_number, player_action, narration, npc_dialogues)`: fire-and-forget via `asyncio.create_task`. Usa sessione DB indipendente (`async_session()`). Per ogni fatto: genera embedding via `generate_embedding()`, crea `MemoryFact`, bulk insert.
- Controllato da `get_gameplay_config().fact_extraction_enabled`.

#### `backend/app/models/memory_fact.py`
SQLAlchemy model per fatti atomici.

- `MemoryFact(Base, UUIDMixin, TimestampMixin)`: `campaign_id` (FK campaigns), `turn_number`, `entity_name` (String 200), `entity_type` (String 50: npc/location/quest/item/event/secret), `content` (Text), `embedding` (Vector 384), `search_vector` (TSVECTOR).
- Indici: GIN su `search_vector`, composite su `(campaign_id, entity_name)`.

#### `backend/alembic/versions/001_add_memory_facts.py`
Alembic migration per tabella `memory_facts` con indici GIN e composite.

### Backend — Nuovi test

#### `backend/tests/unit/test_updater.py` (18 test)
Copre: tutti i 7 handler tipizzati, clamp valori, fallback a merge generico, multi-update consecutivi, creazione NPC se non esiste.

#### `backend/tests/unit/test_npc_director.py` (8 test)
Copre: format dialoghi, invoke mock con budget model, cap NPC da config, null verbosity (0 NPC).

#### `backend/tests/unit/test_gameplay_config.py` (4 test)
Copre: defaults, mapping verbosity→int, verbosity sconosciuta, env var override.

#### `backend/tests/unit/test_memory_schemas.py` (9 test)
Copre: NPCProfile validazione, CompanionProfile validazione, clamp disposition (-100 to +100), clamp loyalty (0-100), NPCPersonality defaults, extra fields allowed.

---

## Changed

### Backend

#### `backend/app/ai/model_config.yaml`
Aggiunta sezione `gameplay`:
```yaml
gameplay:
  context_window_turns: 8
  npc_verbosity: "medium"    # null|minimal|low|medium|high|unlimited → 0|1|2|3|5|999
  compression_enabled: true
  fact_extraction_enabled: true
```

#### `backend/app/ai/router.py`
- Aggiunto `GameplayConfig` dataclass con `context_window_turns`, `npc_verbosity`, `compression_enabled`, `fact_extraction_enabled`.
- Aggiunto `_NPC_VERBOSITY_MAP`: null→0, minimal→1, low→2, medium→3, high→5, unlimited→999.
- Aggiunta property `max_npc_calls` su `GameplayConfig`.
- Aggiunta funzione `get_gameplay_config()` con override da env vars (`SAGA_GAMEPLAY_*`).

#### `backend/app/memory/world_state.py`
- `CURRENT_SCHEMA_VERSION`: 2 → 3.
- Aggiunta `"narrative"` a `ALLOWED_WORLD_STATE_KEYS`.
- Aggiunta migration v2→v3: `state.setdefault("npcs", {})`, `state.setdefault("companions", {})`, `state.setdefault("narrative", {"event_log": []})`.

#### `backend/app/memory/compressor.py`
Riscritta per supportare compressione LLM.
- Aggiunta `compress_turns_batch_llm(turns)`: comprime batch di turni via budget model in 2-3 frasi.
- Aggiunta `ensure_compression(campaign_id, current_turn, db)`: trova turni oltre Active Window senza summary, comprimi in batch di 5.
- `should_compress()` usa `context_window_turns` configurabile.

#### `backend/app/ai/context.py`
- `build_context()` usa `context_window_turns` da GameplayConfig.
- Carica summary compressi per turni prima della finestra, deduplica batch.
- Passa `summary_context` a `build_dm_system_prompt()`.

#### `backend/app/ai/prompts/dm.py`
- `build_dm_system_prompt()` accetta `summary_context: str = ""`.
- Inietta sezione "Story So Far (Previous Events)" tra character context e world state.

#### `backend/app/ai/prompts/npc.py`
- Prompt NPC aggiornato con contesto turno: `player_action`, `dm_narration`, `traits`, `disposition/100`.
- `build_npc_prompt()`: aggiunti parametri `player_action=""`, `dm_narration=""`.
- Legge da dict NPCProfile-compatible (personality.traits, personality.fears, personality.secrets, goals).

#### `backend/app/core/engine.py`
- Aggiunto `"npc_dialogue"` al Literal type di `StreamEvent`.
- Pipeline `process_game_turn_streaming()` aggiornato:
  1. Semantic Resolver call prima di `build_context()`.
  2. Dopo DM response + dice: NPC Actor-Director via `invoke_npcs_parallel()`.
  3. Yield `StreamEvent(type="npc_dialogue")` per ogni NPC.
  4. Applica NPC disposition changes via `apply_typed_updates()`.
  5. Append NPC dialogue text a `full_narration`.
  6. Gestisce sia dict (legacy) che list (typed) per `world_updates`.
  7. `turn_result` include `npc_dialogues` list.

#### `backend/app/api/websocket.py`
- Gestisce nuovo evento `npc_dialogue` → invia `{"type": "npc:dialogue", ...}`.
- Raccoglie NPC dialogues per fact extraction.
- Dopo commit: lancia due background tasks:
  - `asyncio.create_task(extract_and_store_facts(...))`
  - `asyncio.create_task(_background_compression(...))`
- Aggiunta helper `_background_compression()` con sessione DB indipendente.

#### `backend/app/models/__init__.py`
- Aggiunto import e export di `MemoryFact`.

### Test aggiornati

| File | Modifica |
|------|----------|
| `test_world_state.py` | schema_version 2→3, rinominato v2_state→v3_state, assertion v3 fields |
| `test_game_clock.py` | schema_version 2→3, aggiunti check per npcs/companions/narrative |
| `test_prompts.py` | NPC prompt test aggiornato per nuovo formato (personality dict, goals, disposition_toward_player) |

---

## Architettura — Decisioni chiave

### NPC Actor-Director Pattern
- DM è il Regista: decide chi parla via `invoke_npcs`.
- NPC sono Attori indipendenti: call LLM budget separate via `asyncio.gather`.
- Dialoghi NPC vanno direttamente al frontend, **mai** tornano al DM.
- Cap configurabile via `npc_verbosity` in `model_config.yaml`.

### Memoria a budget costante
- Active Window: ultimi N turni verbatim (configurabile, default 8).
- Turni oltre la finestra: compressi in summary 2-3 frasi via budget LLM (batch di 5).
- I summary **sostituiscono** i turni verbatim → budget token fisso (~4000 token per memoria).
- Fact Extractor: fatti atomici estratti in background, non bloccanti.

### World State Updater tipizzato
- Handler registry con decorator `@_register_handler`.
- Ogni tipo di update ha il suo handler con validazione e clamp.
- Tipi sconosciuti → fallback a `merge_world_state()` generico.
- Separation of concerns: character_data (HP, inventory, quests) vs world_state (NPCs, narrative, companions).

### Gameplay Config
- Sezione `gameplay` in `model_config.yaml` per configurazione runtime.
- Tutti i valori overridable via env vars `SAGA_GAMEPLAY_*`.
- `npc_verbosity` mappato a cap intero: null=0, minimal=1, low=2, medium=3, high=5, unlimited=999.

---

## Non implementato (rinviato)

- **Hybrid Search** (pgvector + tsvector query): tabella e indici pronti, query in Phase D.
- **Contextual Loading**: Semantic Resolver pronto, ma Context Assembler non fa ancora loading selettivo.
- **Template System (B4)**: spostato a Phase D.
- **Companion Bar frontend**: non implementato.
- **Token budget check esplicito**: non necessario — budget costante by design.
