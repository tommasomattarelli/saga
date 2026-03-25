# FASE 1 — Piano A: "Da Chatbot a Gioco"

> Tutte le modifiche apportate nella Fase A del progetto SAGA/Wyrd.
> Commit: `7cfd0c4` · `d6dd5a2` · `63c7ee0` + fix post-commit
> Data: 2026-03-25 / 2026-03-26
> Test: 101 → 171 passing (169 + 2 fix playtest)

---

## Sommario

La Fase A trasforma SAGA da chatbot narrativo a RPG giocabile. Il backend acquisisce:
schema Pydantic validato per l'output del DM, JSON healing, rilevazione content policy per 3 provider, 6 livelli di outcome per i dadi, GameClock, pipeline di re-prompt sui dadi, e creazione narrativa del personaggio. Il frontend acquisisce: integrazione WebSocket reale, streaming token-by-token, animazione dadi click-to-reveal, sistema di scene mood con CSS custom properties, e wiring di suggested_actions.

---

## Added

### Backend — Nuovi file

#### `backend/app/ai/schemas/__init__.py`
Package init vuoto. Crea il modulo `ai.schemas` per contenere i Pydantic models dell'output DM.

#### `backend/app/ai/schemas/dm_response.py`
Schema Pydantic v2 completo per la risposta strutturata del DM.

Classi:
- **`SceneMood`** (`StrEnum`): 11 valori — `neutral`, `calm_exploration`, `tense_anticipation`, `combat_fury`, `mystery_intrigue`, `horror_dread`, `triumph_victory`, `grief_loss`, `romance_warmth`, `comic_relief`, `epic_climax`.
- **`DiceRequest`**: `name: str`, `dc: int`, `ability: str`, `reason: str`.
- **`CompanionAction`**: `companion_name: str`, `action: str`, `mood: str`.
- **`DMResponse`** (model principale):
  - `narration: str = ""`
  - `invoke_npcs: list[str] = []`
  - `dice_required: list[DiceRequest] | None = None`
  - `scene_mood: SceneMood = SceneMood.NEUTRAL`
  - `time_passed_minutes: int = 5`
  - `companion_actions: dict[str, str] | None = None`
  - `world_updates: dict | None = None`
  - `suggested_actions: list[str] | None = None`
  - `ambient_detail: str | None = None`
  - `scene_image_prompt: str | None = None`
  - `character_generation: dict | None = None`
  - `@field_validator("scene_mood", mode="before")`: fallback a `"neutral"` se valore non nell'enum o mancante.
  - `model_config = {"extra": "ignore"}`: campi sconosciuti ignorati silenziosamente.

#### `backend/app/ai/exceptions.py`
Eccezioni custom dell'AI layer.

- **`ContentPolicyError(SagaError)`**: raised quando un provider blocca la risposta per content policy. Attributi: `provider: str`, `message: str`. `status_code = 422`. Messaggio human-readable incluso.

#### `backend/tests/unit/conftest.py`
Override dei fixture di sessione per i test unitari.

- Sovrascrive `setup_database` e `clean_database` (definiti nella root conftest) come no-op.
- Impedisce che i test unitari tentino una connessione a PostgreSQL.
- Senza questo file, `pytest tests/unit` falliva con `ConnectionRefusedError` anche per test che non usano il DB.

### Backend — Nuovi test

#### `backend/tests/unit/test_dm_response_schema.py` (11 test)
Copre: parsing schema completo, fallback `scene_mood` per valori non validi/mancanti/None, `extra="ignore"` su campi sconosciuti, defaults di tutti i campi opzionali, `DiceRequest` e `CompanionAction`.

#### `backend/tests/unit/test_parser_healing.py` (13 test)
Copre: strip di markdown fences (` ```json ``` `, ` ``` ` senza tipo, mixed), `json-repair` su JSON troncato/malformato, fallback a `DMResponse(narration=raw)` se irrecuperabile, `parse_dm_response()` end-to-end con input valido/parziale/broken.

#### `backend/tests/unit/test_dice_outcomes.py` (10 test)
Copre: tutti i 6 outcome levels (`critical_failure`, `hard_failure`, `soft_failure`, `partial_success`, `full_success`, `critical_success`), override natural 1 e natural 20 indipendentemente dalla DC, advantage (2d20 take high) e disadvantage (2d20 take low), `is_critical` flag.

#### `backend/tests/unit/test_game_clock.py` (17 test)
Copre: `GameClock` computed fields (derivazione `current_hour` da `total_minutes`, `current_day`, `current_season` per tutti e 4, `time_of_day` per tutti i 6 slot), `advance_game_clock()` con accumulo progressivo, migrazione world state v1→v2 (aggiunta chiave `clock` con defaults), serializzazione/deserializzazione da JSONB.

#### `backend/tests/unit/test_content_policy.py` (5 test)
Copre: mock di risposta OpenAI con `finish_reason="content_filter"`, mock Anthropic con risposta vuota e `stop_reason="end_turn"`, mock Google con `finish_reason=SAFETY`, verifica che tutti e 3 i provider alzino `ContentPolicyError` con `provider` attribute corretto.

#### `backend/tests/unit/test_turn_pipeline_a1.py` (6 test async)
Copre: turno senza dadi (narrazione diretta), turno con `dice_required` (re-prompt), narrazione fallback da `ContentPolicyError`, salvataggio `character_generation` in `character_data`, `requires_player_action` True/False, avanzamento GameClock. Tutti i test patchano `app.ai.providers.base.get_provider` (non `app.core.engine.get_provider` — il provider è importato localmente).

### Frontend — Nuovi file

#### `frontend/src/styles/mood.css`
Sistema completo di theming per 11 scene moods.

- Selettori `[data-mood="<mood>"]` su `.mood-container` con CSS custom properties:
  - `--mood-bg`: colore di sfondo (dark, saturato).
  - `--mood-accent`: colore accent (bordi, highlights).
  - `--mood-text`: colore testo secondario.
- Transizione `background-color` e `color` in 1.5s `ease-in-out` sulla classe `.mood-container`.
- 6 classi `.dice-<outcome>` colorate: `critical_failure` (rosso scuro), `hard_failure` (rosso), `soft_failure` (arancio), `partial_success` (giallo), `full_success` (verde), `critical_success` (oro con glow).
- `@keyframes dice-counter`: animazione numerica cycling 0→20.
- `@keyframes dice-reveal`: animazione scale+opacity per il reveal finale.

---

## Changed

### Backend

#### `backend/pyproject.toml`
- **Aggiunto** `"json-repair>=0.30.0"` alle dipendenze runtime.
- **Spostato** `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx`, `ruff`, `mypy` da `[project.optional-dependencies] dev` a `[dependency-groups] dev`.
- **Motivo**: `uv sync` non installa `[project.optional-dependencies]` di default — ruff non era disponibile, causando "failed to spawn ruff" in `make lint`. `[dependency-groups]` è installato sempre da `uv sync`.

#### `backend/app/ai/parser.py`
Pipeline di parsing riscritta completamente.

Prima:
```python
data = json.loads(raw_output)
return ParsedDMResponse(**data)
```

Dopo (pipeline in 4 step):
1. `_strip_fences(raw)`: rimuove ` ```json ``` ` e ` ``` ``` ` via regex.
2. `re.search(r"\{[\s\S]*\}", stripped).group()`: estrae il blocco JSON.
3. `repair_json(json_str)`: chiama `json-repair` per sanare JSON troncato/malformato.
4. `DMResponse.model_validate(json.loads(repaired))`: validazione Pydantic con `extra="ignore"`.
5. Fallback: `DMResponse(narration=raw.strip())` se ogni step fallisce.

`ParsedDMResponse` dataclass rimossa — sostituita da `DMResponse` importata da `ai.schemas.dm_response`.

#### `backend/app/ai/prompts/dm.py`
- `BASE_DM_PROMPT` aggiornato con:
  - Schema JSON completo nell'esempio (ordine campi rispettato per streaming).
  - `scene_mood` enum completo con tutti 11 valori e descrizioni.
  - Regole per `invoke_npcs`: DM lista gli NPC che parlano nella scena.
  - Regole per `dice_required`: trivial → null (auto success), impossible → null (auto fail), incerto con posta → `DiceRequest`.
  - Guida `time_passed_minutes`: dialogo 1-5, esplorazione 10-30, viaggio locale 30-60, viaggio tra zone 120-480, riposo breve 60, riposo lungo 480.
  - Istruzione esplicita: `narration` DEVE essere il primo campo per ottimizzare lo streaming.
- **Aggiunta** costante `CREATION_MODE_PROMPT`: prompt speciale usato quando `character_data` è vuoto/assente. Guida il DM a chiedere il concept del personaggio e generare stats via campo `character_generation`.
- **Aggiunta** funzione `is_creation_mode(campaign)`: restituisce `True` se `character_data` è `None` o manca il campo `name`.
- **Modificata** `build_dm_system_prompt()`: include sempre il character sheet nel contesto, usa `CREATION_MODE_PROMPT` se `is_creation_mode()`.

#### `backend/app/ai/providers/openai.py`
- Dopo la chiamata LLM, controlla `choice.finish_reason == "content_filter"`.
- Se True: `raise ContentPolicyError("openai", "Content filtered by OpenAI safety systems")`.

#### `backend/app/ai/providers/anthropic.py`
- Controlla `response.stop_reason == "end_turn" and not response.content`.
- Se True: `raise ContentPolicyError("anthropic", "Response blocked by Anthropic content policy")`.

#### `backend/app/ai/providers/google.py`
- Controlla `str(candidate.finish_reason) == "SAFETY"` (string comparison necessaria per compatibilità con l'enum google-genai).
- Se True: `raise ContentPolicyError("google", "Response blocked by Google safety filters")`.

#### `backend/app/core/dice.py`
- **Aggiunto** `DiceOutcome` (`StrEnum`): `critical_failure`, `hard_failure`, `soft_failure`, `partial_success`, `full_success`, `critical_success`.
- **Aggiunta** funzione privata `_determine_outcome(total, dc, natural_roll)`:
  - Natural 1 → `critical_failure` (sempre, indipendentemente dalla DC).
  - Natural 20 → `critical_success` (sempre).
  - `total <= dc - 5` → `hard_failure`.
  - `dc - 4 <= total <= dc - 1` → `soft_failure`.
  - `dc <= total <= dc + 3` → `partial_success`.
  - `total >= dc + 4` → `full_success`.
- **Modificato** `DiceResult` dataclass: aggiunto `outcome: DiceOutcome`, aggiunto `is_critical: bool`.
- **Modificato** `ability_check()`: popola `outcome` e `is_critical` nel risultato. Mantiene `success: bool` per backward compatibility.

#### `backend/app/core/engine.py`
Modifiche al turn pipeline:

1. **Creation mode**: se `is_creation_mode(campaign)`, usa `CREATION_MODE_PROMPT`. Se `DMResponse.character_generation` è presente, salva il dict in `campaign.character_data`.
2. **Ability modifier da character_data**: quando `dice_required` è presente, cerca il nome del check (`dice_required[n].ability`) nelle keys di `campaign.character_data["abilities"]`. Se trovato, calcola il modifier come `(score - 10) // 2` e sovrascrive il modifier del dice request.
3. **Dice re-prompt**: dopo aver tirato i dadi, costruisce immediatamente la seconda call LLM con il formato: `"The player attempted {check}. They rolled {roll} + {modifier} = {total} vs DC {dc}. Outcome: {outcome}. Narrate the result in 2-3 sentences."`. La narrazione del re-prompt viene appendata a `processed.narration`.
4. **`ContentPolicyError` handler**: cattura `ContentPolicyError` → imposta `narration = "The DM refuses to narrate this scene as described. Try rephrasing your action."`.
5. **`advance_game_clock`**: chiamata dopo ogni turno con `processed.time_passed_minutes`.
6. **`requires_player_action`**: calcolato come `bool(processed.dice_required) or combat_active`. Aggiunto al `ProcessedTurn` result.

#### `backend/app/memory/world_state.py`
- **Aggiunto** `GameClock` (Pydantic BaseModel):
  - `total_minutes: int = 0`
  - `@computed_field current_hour: int` → `(total_minutes // 60) % 24`
  - `@computed_field current_day: int` → `total_minutes // 1440 + 1`
  - `@computed_field current_season: str` → mappa giorno → stagione (ogni 90 giorni: spring/summer/autumn/winter)
  - `@computed_field time_of_day: str` → 6 slot: dawn (5-7), morning (8-11), afternoon (12-16), evening (17-20), night (21-23), midnight (0-4)
- **Aggiunta** costante `CURRENT_SCHEMA_VERSION = 2`.
- **Aggiunta** `"clock"` a `ALLOWED_WORLD_STATE_KEYS`.
- **Aggiunta** funzione `_migrate_v1_to_v2(state)`: aggiunge `state["clock"] = GameClock().model_dump()` con defaults (`total_minutes=0`, orario di partenza: mattina).
- **Modificata** `migrate_world_state()`: catena v0→v1→v2. La v0→v1 aggiungeva `meta`; la v1→v2 aggiunge `clock`.
- **Aggiunta** funzione `advance_game_clock(world_state, minutes)`: deserializza `world_state["clock"]` in `GameClock`, incrementa `total_minutes += minutes`, riscrive con `model_dump()`.

#### `backend/app/schemas/campaign.py` — `TurnResponse`
Aggiunto al modello Pydantic:
- `invoke_npcs: list[str] = []`
- `time_passed_minutes: int = 5`
- `ambient_detail: str | None = None`
- `requires_player_action: bool = True`

#### `backend/app/services/turn_service.py`
- `process_turn()` ora passa i 4 nuovi campi a `TurnResponse`.

#### `backend/tests/unit/test_world_state.py`
- `test_migrate_v0_to_v1` → rinominato `test_migrate_v0_to_v2` (la migration ora va a v2).
- `test_migrate_up_to_date`: aggiornato per usare `schema_version: 2` e stato con `clock` presente.

#### `backend/tests/playtest/test_scenario_combat.py`
- `_make_mock_game_turn()`: aggiunti `invoke_npcs=[]`, `time_passed_minutes=5`, `ambient_detail=None`, `requires_player_action=True`.
- **Motivo del fix**: `TurnResponse` valida con Pydantic — `ambient_detail` deve essere `str | None`, non un `MagicMock`. Senza i valori espliciti, `MagicMock.__getattr__` restituisce un nuovo MagicMock → ValidationError.

### Frontend

#### `frontend/src/types/index.ts`
- **`CharacterData`**: aggiunto `equipped: EquippedItems`, `reputation: Record<string, number>`, `active_quests: string[]`.
- **Aggiunta** interfaccia `EquippedItems`: `weapon?: string`, `armor?: string`, `accessory?: string`.
- **`DiceRollResult`**: aggiunto `modifier: number`, `outcome: DiceOutcome`, `is_critical: boolean`.
- **Aggiunto** type alias `DiceOutcome`: union dei 6 valori stringa.
- **`TurnResponse`**: aggiunto `invoke_npcs: string[]`, `time_passed_minutes: number`, `ambient_detail: string | null`, `requires_player_action: boolean`.
- **`WorldState`**: aggiunto `clock?: GameClockState`.
- **Aggiunta** interfaccia `GameClockState`: `total_minutes`, `current_hour`, `current_day`, `current_season`, `time_of_day`.

#### `frontend/src/stores/game-store.ts`
- **Aggiunta** interfaccia `StreamingState`: `isStreaming: boolean`, `currentNarration: string`, `pendingDice: DiceRollResult | null`, `diceRevealed: boolean`, `currentMood: string`.
- **Aggiunto** slice `streaming` allo store Zustand con stato iniziale.
- **Aggiunte** actions: `setStreaming`, `appendNarration`, `setPendingDice`, `revealDice`, `resetStreaming`.
- **Aggiunto** `"clock"` a `ALLOWED_WORLD_STATE_KEYS` (sincronizza il clock dal `turn_complete` event).

#### `frontend/src/services/websocket.ts`
- **Aggiunto** flag `intentionalClose: boolean` — impedisce la riconnessione automatica quando si chiama `disconnect()` esplicitamente.
- **Aggiunto** `reconnectTimer: ReturnType<typeof setTimeout> | null` con cleanup in `disconnect()` — evita riconnessioni pendenti dopo la disconnessione.

#### `frontend/src/components/game-view.tsx`
- **Aggiunto** `wsRef = useRef<GameWebSocket | null>(null)`.
- **Aggiunto** `useEffect` per il lifecycle WebSocket: `connect()` al mount, `disconnect()` all'unmount, cleanup su cambio `campaignId`.
- **Registrati** event handler per:
  - `turn_start` → `resetStreaming()`
  - `dm:narration:chunk` → `appendNarration(chunk)`
  - `dice:roll` → `setPendingDice(result)`
  - `scene_mood` → `setStreaming({ currentMood: mood })`
  - `turn_complete` → aggiorna store con dati finali del turno
- **Aggiunto** `data-mood={currentMood}` sul div root → triggera le transizioni CSS.
- **Aggiunto** display GameClock nell'header: ora, giorno, stagione.
- **Passato** `wsRef` a `NarrativeStream` e `ActionInput`.

#### `frontend/src/components/narrative/narrative-stream.tsx`
- **Aggiunta** prop `wsRef: React.RefObject<GameWebSocket | null>`.
- **Aggiunto** `onSuggestedAction(action)`: invia `{ type: "player_action", action }` via `wsRef.current?.send()`.
- `suggested_actions`: renderizzati come `<button>` cliccabili che chiamano `onSuggestedAction`.
- `ambient_detail`: renderizzato come `<p className="italic text-secondary">` sotto la narrazione.
- **Aggiunto** live streaming block: se `isStreaming`, mostra `currentNarration` con cursore lampeggiante.
- **Aggiunto** `data-mood` per-turn-block (applicato a ogni blocco di turno storico).

#### `frontend/src/components/narrative/dice-roller.tsx`
Riscritta la logica del componente.

- **Aggiunto** `SingleDice` sub-component:
  - Stato: `revealed: boolean`, `displayValue: number`.
  - Click → avvia `setInterval` che cicla numeri 1-20 ogni 80ms per 1500ms → poi svela il valore reale e `setRevealed(true)`.
  - Riproduce `new Audio('/sounds/dice-roll.mp3').play()` al click.
  - Classe CSS `.dice-{outcome}` applicata dopo il reveal.
- **Aggiunta** mappa `OUTCOME_LABELS`: `critical_failure` → "Critical Fail!", `critical_success` → "Natural 20!", ecc.
- Pulsante "Roll!" visibile prima del click, sostituito dal valore numerico + label outcome dopo.

#### `frontend/src/components/input/action-input.tsx`
- **Modificato** submit: invia via `wsRef.current?.send({ type: "player_action", action: text })` invece di `POST /api/campaigns/:id/turn`.
- **Aggiunto** pulsante "Continue": visibile quando `!requires_player_action`. Al click invia `action: "wait"`.
- `suggested_actions` nella barra input: bottoni contestuali sopra l'input che popolano il campo testo.

#### `frontend/src/components/character/character-sheet.tsx`
- **Aggiunta** sezione **Equipped**: mostra `weapon`, `armor`, `accessory` da `character_data.equipped`.
- **Aggiunta** sezione **Reputation**: mostra le voci di `character_data.reputation` come lista.
- Gold e AC mostrati inline (non più come testo `"X gold"` ma come `<span>` separato).
- **Aggiunta** sezione background.

#### `frontend/src/main.tsx`
- **Aggiunto** `import "./styles/mood.css"` — carica il sistema di theming mood a livello globale.

### Frontend — Test aggiornati

I seguenti file di test sono stati aggiornati per allinearsi ai nuovi tipi e props:

| File | Modifica |
|------|----------|
| `campaign-select.test.tsx` | Mock `CharacterData` + `equipped: {}`, `reputation: {}`, `active_quests: []` |
| `character-sheet.test.tsx` | Stessi campi; asserzione `"0 gold"` → `"0"` (gold ora renderizzato come `<span>` separato) |
| `game-view.test.tsx` | Mock `CharacterData` + nuovi campi |
| `narrative-stream.test.tsx` | Aggiunta prop `wsRef`; mock `TurnResponse` + `invoke_npcs`, `time_passed_minutes`, `ambient_detail`, `requires_player_action` |
| `game-store.test.ts` | Mock `TurnResponse` + nuovi campi |
| `websocket.test.ts` | Rimosso secondo argomento `undefined` dall'asserzione su `WebSocket` constructor (il costruttore viene chiamato con 1 argomento, non 2) |

### Makefile (root)
- `test-backend`: `uv run pytest tests/unit` → `uv run python -m pytest tests/unit`.
- `test-all`: `uv run pytest tests/unit tests/integration tests/playtest` → `uv run python -m pytest tests/unit tests/integration tests/playtest`.
- **Motivo**: su Windows, `uv run pytest` fallisce con "Failed to canonicalize script path" perché uv non riesce a trovare l'entry point `pytest` come script. `python -m pytest` funziona sempre.

### Documentazione

#### `README.md`
- Features section aggiornata con: GameClock, 6-level dice, json-repair, content policy, narrative character creation, scene moods 11 stati.

#### `.docs/STATE.md`
- Snapshot aggiornato a "Phase A Complete".
- Test count: 101 → ~163.
- Documentate tutte le implementazioni A1-A4.
- Roadmap aggiornata a Phase B (Actor-Director + Semantic Memory).

#### `.docs/SAGA_v1_specs.md`
- Aggiunti checkmark `[x]` a tutti gli item completati nella Fase A:
  - Healing Parser, Content Policy Handler, `requires_player_action`, dice re-prompt, World State Updater + GameClock (§4.1)
  - Tutti i 6 livelli dice outcome, advantage/disadvantage, server-side roll (§4.2)
  - Schema DMResponse completo, scene_mood enum + fallback, healing + retry (§4.3)
  - WebSocket streaming + eventi DM e dice (§4.4)
  - Creazione narrativa personaggio, generazione stats da concept (§5.1)
  - World state versioning + GameClock JSONB (§9.1, §13.3)
  - NarrativeStream, DiceRoller, CharacterSheet components (§12.2)
  - Suono dadi (§12.4)
  - Content Policy Handler (§15)

---

## Removed

- **`ParsedDMResponse` dataclass** in `backend/app/ai/parser.py`: rimpiazzata da `DMResponse` Pydantic model.

---

## Fixed

### Post-commit fixes

- **`backend/tests/playtest/test_scenario_combat.py`**: `_make_mock_game_turn()` non includeva i 4 campi nuovi (`invoke_npcs`, `time_passed_minutes`, `ambient_detail`, `requires_player_action`). Pydantic rifiutava il `MagicMock` per `ambient_detail` che non è `str | None`. Fix: aggiunti valori espliciti al mock.
- **`backend/pyproject.toml`**: `ruff` non installato da `uv sync` di default (era in optional-extras). Fix: spostato in `[dependency-groups]`.

---
