# FASE 0 — Stato Baseline (Pre-Fase A)

> Snapshot dello stato del progetto **prima** di qualsiasi modifica della Fase A.
> Commit di riferimento: `832a720` (2026-03-25)
> Test passing: 101 (unit + integration + playtest)

---

## Architettura generale

Stack: React 18 + TypeScript + Vite (frontend) / Python 3.12 + FastAPI + SQLAlchemy 2.0 async (backend) / PostgreSQL 16 + pgvector + Redis / Docker Compose.

Il progetto aveva un turn pipeline funzionante end-to-end ma mancava di struttura formale per l'output del DM, meccaniche RPG complete, e integrazione WebSocket reale nel frontend.

---

## Backend

### `app/ai/`

#### `parser.py`
- Classe `ParsedDMResponse` come dataclass Python semplice (non Pydantic).
- Parsing naive: `json.loads()` diretto sull'output LLM senza healing.
- Nessuna gestione di markdown fences (` ```json ``` `).
- Retry su eccezione generica, senza distinzione tra JSON malformato e altri errori.
- Fallback: restituisce `ParsedDMResponse` con `narration=raw_output`.
- Campi: `narration`, `dice_required`, `scene_mood`, `companion_actions`, `world_updates`, `suggested_actions`. Mancano: `invoke_npcs`, `time_passed_minutes`, `ambient_detail`, `scene_image_prompt`, `character_generation`.

#### `prompts/dm.py`
- `BASE_DM_PROMPT`: prompt DM funzionante ma incompleto.
- `scene_mood` con 6 valori nell'enum (mancavano 5 mood).
- Nessuna guida su `time_passed_minutes`.
- Nessuna logica per la creazione narrativa del personaggio (creation mode).
- `build_dm_system_prompt()`: costruisce il prompt senza includere sempre il character sheet.

#### `providers/openai.py`, `anthropic.py`, `google.py`
- Nessuna rilevazione di violazioni della content policy.
- Errori di content filtering propagati come eccezioni generiche non gestite.
- Il turn pipeline crashava o restituiva 500 in caso di blocco policy.

#### `schemas/` (directory)
- Non esisteva. Nessun modulo `schemas` nell'`ai/` package.

#### `exceptions.py`
- Non esisteva come file dedicato (o conteneva solo eccezioni base).

### `app/core/`

#### `dice.py`
- `DiceResult` dataclass con: `roll`, `modifier`, `total`, `dc`, `success` (bool).
- `ability_check()` restituiva solo `success: bool` — nessun livello di outcome.
- Nessun `DiceOutcome` enum.
- Nessun campo `is_critical`.
- Logica: `total >= dc` → success, altrimenti failure. Solo 2 livelli (pass/fail).

#### `engine.py`
- Turn pipeline funzionante ma senza:
  - Dice re-prompt (seconda call LLM dopo il tiro).
  - Aggiornamento GameClock.
  - Rilevamento creation mode.
  - Lettura del modifier da `character_data.abilities`.
  - `requires_player_action` calcolato.
  - Gestione `ContentPolicyError`.

### `app/memory/`

#### `world_state.py`
- Schema world state versione 1.
- Nessun `GameClock`.
- `ALLOWED_WORLD_STATE_KEYS`: lista senza `"clock"`.
- `migrate_world_state()`: migrava da v0 a v1 (aggiungeva solo `meta`).
- Nessuna funzione `advance_game_clock()`.

### `app/schemas/`

#### `campaign.py` — `TurnResponse`
- Campi: `turn_number`, `narration`, `dice_rolls`, `companion_actions`, `world_updates`, `scene_mood`, `suggested_actions`, `model_used`.
- Mancanti: `invoke_npcs`, `time_passed_minutes`, `ambient_detail`, `requires_player_action`.

### `app/services/`

#### `turn_service.py`
- `process_turn()` costruiva `TurnResponse` senza i nuovi campi.
- Mock nei playtest non includeva i nuovi campi → stabile rispetto alla struttura precedente.

### `pyproject.toml`
- `ruff` e gli altri tool dev in `[project.optional-dependencies] dev` — non installati da `uv sync` di default.
- `[dependency-groups] dev` conteneva solo `pytest-mock`.
- `json-repair` non presente nelle dipendenze.

---

## Frontend

### `src/types/index.ts`
- `CharacterData`: mancano `equipped`, `reputation`, `active_quests`.
- `DiceRollResult`: mancano `modifier`, `outcome`, `is_critical`.
- `TurnResponse`: mancano `invoke_npcs`, `time_passed_minutes`, `ambient_detail`, `requires_player_action`.
- `WorldState`: nessun campo `clock`.

### `src/stores/game-store.ts`
- Nessuno stato streaming (`StreamingState`).
- Nessuna action per `appendNarration`, `setPendingDice`, `revealDice`, `resetStreaming`.

### `src/services/websocket.ts`
- `GameWebSocket` funzionante ma senza:
  - Flag `intentionalClose` (reconnect non controllato).
  - `reconnectTimer` con cleanup in `disconnect()`.

### `src/components/game-view.tsx`
- Nessuna integrazione WebSocket reale.
- Nessun `wsRef`.
- Nessun event handler per `dm:narration:chunk`, `dice:roll`, `turn_complete`, `scene_mood`.
- Nessun display del GameClock nell'header.
- Nessun `data-mood` attribute.

### `src/components/narrative/narrative-stream.tsx`
- Nessuna prop `wsRef`.
- `suggested_actions`: non cliccabili / non inviavano azioni.
- `ambient_detail`: non renderizzato.
- Nessuno streaming live block.

### `src/components/narrative/dice-roller.tsx`
- Componente base senza animazione counter.
- Nessun click-to-reveal.
- Nessun suono.
- Nessun colore per outcome (solo pass/fail).

### `src/components/input/action-input.tsx`
- Submit via REST (`POST /api/campaigns/:id/turn`).
- Nessun invio via WebSocket.
- Nessun pulsante "Continue" per `requires_player_action`.

### `src/components/character/character-sheet.tsx`
- Schema CharacterData senza `equipped`, `reputation`, `active_quests`.
- Nessuna sezione equipped/reputation nel render.

### `src/styles/`
- Nessun file `mood.css`.
- Nessun sistema di CSS custom properties per scene mood.

### `src/main.tsx`
- Nessun import di `mood.css`.

---

## Tests

### Backend
- 101 test totali (unit + integration + playtest).
- `tests/unit/conftest.py`: non esisteva — i test unit venivano bloccati dal fixture `setup_database` della root conftest che richiedeva PostgreSQL.
- `tests/unit/test_world_state.py`: `test_migrate_v0_to_v1` testava migration a schema v1.

### Frontend
- Test esistenti su: `campaign-select`, `character-sheet`, `game-view`, `narrative-stream`, `game-store`, `websocket`.
- Mock di `CharacterData` senza `equipped`/`reputation`/`active_quests`.
- `websocket.test.ts`: assertiva che `WebSocket` venisse chiamato con `(url, undefined)` come secondo argomento.

---

## Makefile
- `test-backend` e `test-all`: usavano `uv run pytest` → falliva su Windows con "Failed to canonicalize script path".
