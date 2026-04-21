# SAGA — Architecture & Game Flow

---

## 1. Stack tecnico (sintesi)

| Layer | Tech | Note |
|-------|------|------|
| Frontend | React 18 + TypeScript + Vite | Zustand store, TanStack Query, WebSocket |
| Backend | FastAPI + Python 3.12 (async) | SQLAlchemy 2.0 async, structlog |
| Database | PostgreSQL 16 + pgvector | JSONB per world_state/character_data, vector per semantic memory |
| AI | Google Gemini (configurabile) | Router multi-tier, streaming |
| Cache | Redis (opzionale) | Solo WS session cache v1, rimovibile |
| Infra | Docker Compose | backend, frontend, db, redis |

---

## 2. Architettura generale

```
┌──────────────────────┐
│     Frontend (React)  │
│  ┌────────┐ ┌──────┐ │        WebSocket
│  │GameView│ │Store │◄├────────────────────┐
│  └───┬────┘ └──────┘ │                    │
│      │ action         │                    │
│      ▼                │                    │
│  WebSocket.send()     │                    │
└──────────┬────────────┘                    │
           │                                 │
           ▼                                 │
┌──────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                    │
│                                                      │
│  websocket.py ─► engine.py ─► AI Provider            │
│       │              │              │                │
│       │              ▼              ▼                │
│       │         updater.py    Gemini/OpenAI          │
│       │              │                               │
│       │              ▼                               │
│       │         PostgreSQL                           │
│       │              │                               │
│       ◄──────────────┘                               │
│  (send turn_complete with updated state)             │
└──────────────────────────────────────────────────────┘
```

---

## 3. Game Flow — ciclo completo di un turno

### 3.1 Input del giocatore

Il frontend invia un messaggio WebSocket:
```json
{"action": "Attacco il goblin con la spada"}
```

**Sanitizzazione** (websocket.py):
1. `sanitize_player_input(action)` — strip HTML, trim, max length
2. `detect_injection(action)` — se positivo, sostituisce con azione generica

---

### 3.2 Semantic Resolver

**File**: `ai/semantic_resolver.py`

Prima di assemblare il contesto, il Semantic Resolver risolve riferimenti impliciti:
- "lei" → "Grenda la taverniera"
- "la spada" → "Iron Longsword"
- "quel posto" → "Taverna del Drago Nero"

**Input al resolver** (budget LLM, bassa temperatura):
- System prompt: istruzioni di risoluzione
- User message con:
  - `location` corrente
  - `companions` attivi
  - `recent_npcs` (ultimi 3 turni)
  - `recent_locations`
  - `action` del player

**Output**: `ResolverOutput(target_npcs=[], target_locations=[])`

---

### 3.3 Context Assembly

**File**: `ai/context.py` → `build_context()`

Assembla tutto ciò che il DM riceverà:

#### System Prompt (cosa riceve il DM)

Composto da blocchi concatenati in ordine:

1. **BASE_DM_PROMPT** — regole fondamentali:
   - Output SOLO JSON raw (no code fences)
   - Formato risposta con 10+ campi (narration primo per streaming)
   - 7 tipi di `world_updates` disponibili con esempi
   - 11 valori di `scene_mood`
   - Regole dadi (quando tirare, DC, critical)
   - Anti-player-speaking, anti-prompt-injection

2. **DEATH_MODE_PROMPT** — uno tra ironman/destino/cronista

3. **COMBAT_PROMPT** — regole combattimento:
   - Formato combat_start con enemies array
   - combat_damage con nomi esatti
   - combat_end
   - Esempi JSON concreti per ogni fase

4. **Player Character** (se presente):
   ```
   ## Player Character
   ```json
   {"name": "Aldric", "hp": {"current": 22, "max": 22}, "abilities": {...}, ...}
   ```
   ```

5. **Story So Far** (se ci sono turni compressi):
   ```
   ## Story So Far (Previous Events)
   [summary dei turni precedenti alla finestra attiva]
   ```

6. **Current World State** (se presente):
   ```
   ## Current World State
   ```json
   {"combat_state": {...}, "clock": {...}, "npcs": {...}, ...}
   ```
   ```

7. **Active Quests** (se presenti)

#### Messages Array (conversazione)

Array di messaggi alternati user/assistant che simula la storia recente:

```
[
  {"role": "user", "content": "[azione turno N-7]"},
  {"role": "assistant", "content": "[narrazione turno N-7]"},
  {"role": "user", "content": "[azione turno N-6]"},
  {"role": "assistant", "content": "[narrazione turno N-6]"},
  ...
  {"role": "user", "content": "[azione turno N-1]"},
  {"role": "assistant", "content": "[narrazione turno N-1]"},
  {"role": "user", "content": "[azione corrente del giocatore]"}   ← ULTIMA
]
```

- **Active Window**: ultimi N turni verbatim (default 8, configurabile via `SAGA_GAMEPLAY_CONTEXT_WINDOW_TURNS`)
- **Compressed summaries**: per i turni prima della finestra, vengono caricate fino a 5 summary compresse (generate da budget LLM in background)

#### Importance Score

`score_importance()` valuta l'azione (0-10):
- Base: 5
- +2 se keywords combat ("attack", "fight", "confront", "betray")
- -2 se keywords tranquilli ("look around", "rest", "inventory")
- +2 se `world_state.in_combat` è True
- Usato dal router per selezionare il tier del modello (low/medium/high)

---

### 3.4 AI Model Routing

**File**: `ai/router.py`

Seleziona modello in base a tipo di chiamata e importance:

| Tier | Importance | Modello (default) |
|------|-----------|-------------------|
| low | 0-3 | gemini-3-flash-preview |
| medium | 4-6 | gemini-3-flash-preview |
| high | 7-10 | gemini-3-flash-preview |

Override via env: `SAGA_GLOBAL_MODEL_HIGH`, `SAGA_GLOBAL_MODEL_MEDIUM`, `SAGA_GLOBAL_MODEL_LOW`

---

### 3.5 Streaming della risposta AI

**File**: `core/engine.py` → `process_game_turn_streaming()`

1. **provider.stream()** viene chiamato con `system_prompt` + `messages` + `model` + `temperature`
2. Per ogni chunk di token in arrivo:
   - Accumulato in `raw_response`
   - Passato a `NarrationExtractor.feed(chunk)`
   - L'extractor è una state machine che cerca `"narration": "...` nel JSON e estrae solo il testo
   - Ogni frammento di narrazione viene yieldato come `StreamEvent(type="narration_chunk")`
3. Il WebSocket invia immediatamente ogni chunk al frontend → testo appare in tempo reale

---

### 3.6 Parsing della risposta completa

**File**: `ai/parser.py` → `parse_dm_response(raw)`

Dopo che lo stream è completo, il `raw_response` intero viene parsato:

1. `_strip_fences(raw)` — rimuove eventuali ` ```json ``` `
2. `re.search(r"\{[\s\S]*\}", stripped)` — estrae il JSON
3. `repair_json(json_str)` — ripara JSON malformato (virgole, quote)
4. `DMResponse.model_validate(data)` — validazione Pydantic
5. `_normalize_world_updates(response)` — se `world_updates` è un dict con `"key"`, lo wrappa in lista

**Output**: `DMResponse` con tutti i campi:

```python
class DMResponse:
    narration: str                              # testo narrativo
    invoke_npcs: list[str]                      # NPC da far parlare
    dice_required: list[DiceRequest] | None     # richieste di tiro dado
    scene_mood: SceneMood                       # mood della scena (11 valori)
    time_passed_minutes: int                    # minuti passati in-game
    companion_actions: dict[str, str] | None    # azioni dei companion
    world_updates: list[dict] | dict | None     # aggiornamenti stato mondo
    suggested_actions: list[str] | None         # suggerimenti per il giocatore
    ambient_detail: str | None                  # dettaglio ambientale
    scene_image_prompt: str | None              # prompt per generazione immagine
    character_generation: dict | None           # (legacy) generazione personaggio via AI
```

---

### 3.7 Dice Rolls

Se `dice_required` non è null:

1. Per ogni `DiceRequest`:
   - Legge il modificatore dalle ability del personaggio (se applicabile)
   - Chiama `ability_check(modifier, dc, advantage, disadvantage)`
   - Genera `DiceRollResult` con roll, total, success, outcome, is_critical
   - Yield `StreamEvent(type="dice_roll")` → frontend mostra il dado

2. **Re-prompt al DM**: per ogni dado tirato, il motore costruisce un nuovo prompt:
   ```
   The player attempted "{check}". They rolled {roll} + {modifier} = {total} vs DC {dc}.
   Outcome: {outcome}. Narrate the result in 2-3 sentences.
   ```
   - Aggiunge il raw_response originale come messaggio assistant + il re-prompt come user
   - Chiama di nuovo `provider.stream()` per narrare il risultato
   - I chunk di narrazione del dado vengono yieldati come `dice_narration_chunk`

---

### 3.8 NPC Actor-Director

Se `invoke_npcs` contiene nomi:

1. Chiama `invoke_npcs_parallel()` — budget LLM, una chiamata per NPC
2. Ogni NPC ha il suo prompt con personalità, disposizione verso il player, contesto della scena
3. Output: `NPCDialogue(npc_name, dialogue, action, disposition_change)`
4. I dialoghi vengono yieldati come `StreamEvent(type="npc_dialogue")`
5. Disposition changes vengono applicati via `apply_typed_updates()`

---

### 3.9 World State Updates

**File**: `memory/updater.py` → `apply_typed_updates()`

Il DM emette `world_updates` come array di oggetti tipizzati. Ogni oggetto ha:
```json
{"key": "tipo", "target": "nome", "change": "valore"}
```

**Handler registrati**:

| Key | Effetto | Modifica |
|-----|---------|----------|
| `combat_start` | Inizia combattimento | `world_state.combat_state = {active: true, initiative_order: [...]}` |
| `combat_damage` | Danno/cura a combattente | `character_data.hp.current` o `combat_state.initiative_order[i].hp` |
| `combat_end` | Fine combattimento | `world_state.combat_state = {active: false}` |
| `hp_change` | Modifica HP fuori combat | `character_data.hp.current` |
| `npc_disposition` | Cambia disposizione NPC | `world_state.npcs[name].disposition_toward_player` |
| `inventory_change` | Aggiungi/rimuovi item | `character_data.inventory` |
| `quest_update` | Avanza/completa quest | `character_data.active_quests` |
| `companion_loyalty` | Cambia lealtà companion | `world_state.companions[name].loyalty` |
| `reputation_change` | Cambia reputazione fazione | `character_data.reputation[faction]` |
| `event_log_entry` | Aggiunge evento al log | `world_state.narrative.event_log` |

**Formato HP** (standard unificato): `{"current": N, "max": N}` (nested, mai flat)

**Fallback combat_damage**: se target è "player" o "playername" (generico), matcha automaticamente il combattente di tipo `"player"`.

---

### 3.10 Game Clock

**File**: `memory/world_state.py`

Dopo ogni turno, il clock avanza di `time_passed_minutes`:
- Aggiorna `current_hour`, `current_day`, `current_season`
- Calcola `time_of_day` (dawn, morning, noon, afternoon, dusk, evening, night)

---

### 3.11 Death Check

**File**: `core/death.py`

Dopo tutti gli update (incluso combat_damage), se `character_data.hp.current <= 0`:

| Death Mode | Comportamento |
|-----------|--------------|
| **Ironman** | Morte permanente. `campaign.status = COMPLETED` |
| **Destino** | Resurrezione con costo narrativo. Max 2-3 vite (tracked in `world_state.destino_lives`) |
| **Cronista** | Nessuna morte. HP resettato, near-death narrato |

Output: `DeathResult` → yield `StreamEvent(type="death_event")`

---

### 3.12 Turn Complete

Alla fine del turno, il backend:

1. **Persiste** il turno nel DB (narrazione, dadi, world_updates, mood, etc.)
2. **Auto-save** della campagna
3. **Invia** al frontend via WebSocket:

```json
{
  "type": "turn_complete",
  "turn_number": 5,
  "narration": "...",
  "dice_rolls": {...},
  "world_updates": [...],
  "scene_mood": "combat_fury",
  "suggested_actions": ["Attacca", "Difendi", "Fuggi"],
  "character_data": { "name": "Aldric", "hp": {"current": 17, "max": 22}, ... },
  "world_state": { "combat_state": {"active": true, ...}, "clock": {...}, ... },
  "combat_state": {"active": true, "initiative_order": [...]},
  "death_event": null
}
```

4. **Background tasks** (fire-and-forget, dopo commit):
   - `extract_and_store_facts()` — estrae fatti atomici dal turno (budget LLM)
   - `ensure_compression()` — comprime turni vecchi fuori dalla finestra attiva

---

### 3.13 Frontend — ricezione e aggiornamento

Il frontend (`game-view.tsx`) riceve gli eventi WebSocket in ordine:

| Evento WS | Azione frontend |
|-----------|-----------------|
| `turn_start` | Mostra indicatore "DM sta pensando..." |
| `dm:narration:chunk` | Appende testo alla narrazione in streaming |
| `dice:roll` | Mostra risultato dado |
| `dice:narration:chunk` | Appende narrazione post-dado |
| `scene_mood` | Aggiorna mood (colori, atmosfera) |
| `npc:dialogue` | Mostra dialogo NPC |
| `combat:start` | (Legacy) segnale combat inizio |
| `combat:end` | (Legacy) segnale combat fine |
| `death:event` | Mostra overlay morte |
| `turn_complete` | **Sync finale**: `updateWorldState()` + `updateCharacter()` → store Zustand aggiornato |

**CombatTracker**: legge da `campaign.world_state.combat_state` (persistente nello store, non da streaming volatile).

**CharacterSheet**: legge da `campaign.character_data`. HP normalizzato via `getHP()` (supporta sia flat `hp: 10` che nested `hp: {current, max}`).

---

## 4. Struttura dati principali

### 4.1 character_data (JSONB)

```json
{
  "name": "Aldric",
  "level": 1,
  "xp": 0,
  "hp": {"current": 22, "max": 22},
  "ac": 10,
  "abilities": {
    "strength": 16,
    "constitution": 14,
    "dexterity": 12,
    "wisdom": 10,
    "intelligence": 8,
    "charisma": 10
  },
  "skills": {},
  "inventory": [{"name": "Iron Sword", "quantity": 1, "description": "..."}],
  "gold": 10,
  "background": "Un ex soldato in cerca di riscatto",
  "archetype": "warrior",
  "notes": "",
  "reputation": {"Thieves Guild": -10},
  "active_quests": [{"name": "Dragon Hunt", "description": "..."}]
}
```

### 4.2 world_state (JSONB)

```json
{
  "meta": {"schema_version": 4, "world_name": "Eldoria", "current_season": "autumn"},
  "clock": {"total_minutes": 720, "current_hour": 12, "current_day": 1, "time_of_day": "noon"},
  "combat_state": {
    "active": true,
    "round": 2,
    "initiative_order": [
      {"name": "Aldric", "initiative": 18, "hp": 17, "max_hp": 22, "type": "player"},
      {"name": "Goblin Scout", "initiative": 14, "hp": 7, "max_hp": 15, "type": "enemy"}
    ],
    "current_turn_index": 0
  },
  "npcs": {
    "Grenda": {"name": "Grenda", "disposition_toward_player": 25}
  },
  "companions": {},
  "destino_lives": 3,
  "narrative": {
    "event_log": [{"description": "Player discovered the hidden passage"}]
  }
}
```

---

## 5. Logging

**File**: `app/logging_setup.py`

- **Console**: formato `key=value` (human-readable, stdout)
- **File**: `logs/saga.log` — JSON lines, rotating 10 MB x 3 backup
- Log chiave per debug turni:
  - `ai_raw_response` — risposta grezza del DM (primi 500 char in console, completa nel file)
  - `dm_response_parsed` — esito parsing (has_world_updates, world_updates_type, count, has_dice, scene_mood)
  - `world_updates_applying` — format, count, keys applicate
  - `combat_damage_target_not_found` — target non matchato (warning)
  - `turn_completed` — numero turno, modello usato
  - `facts_extracted` — numero fatti estratti
