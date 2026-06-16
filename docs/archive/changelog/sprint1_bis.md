# Sprint 1-bis — Bug Fix Playtest

**Data**: 2026-03-31
**Status**: Completato
**Obiettivo**: Risolvere tutti i bug critici emersi dal playtest di Sprint 1.

---

## Root Causes risolte

1. **Frontend non aggiornava mai stato post-turno** — campaign caricata una volta al mount, mai sincronizzata con backend
2. **HP structure mismatch** — DM creava `hp: 10` (flat), updater scriveva `hp: {current, max}` (nested), frontend leggeva flat
3. **CombatTracker wipeout** — `resetStreaming()` cancellava `combatState` ad ogni `turn_complete`
4. **Character creation AI-driven** — inaffidabile, rimosso in favore di form UI
5. **fact_extractor crash** — Gemini restituiva lista o stringa vuota invece di `{"facts": [...]}`

---

## Modifiche

### `backend/app/core/engine.py`
- `turn_result` StreamEvent ora include `character_data` e `world_state` aggiornati (post-apply)
- Log `world_updates_applying` ora mostra le singole keys applicate (es. `keys=["combat_start", "combat_damage"]`)

### `backend/app/services/character_service.py`
- Aggiunto `CLASS_PRESETS`: 6 classi (warrior, rogue, mage, ranger, cleric, bard) con stat bilanciate
- `create_default_character()` ora accetta `archetype` e `background`; calcola HP da CON modifier
- HP in formato nested: `{"current": N, "max": N}` — standard unificato per tutto lo stack

### `backend/app/ai/prompts/dm.py`
- Rimosso `CREATION_MODE_PROMPT` e `is_creation_mode()` — la creazione personaggio avviene ora via UI
- Il character JSON viene sempre incluso nel system prompt se presente

### `backend/app/memory/fact_extractor.py`
- Fix `JSONDecodeError`: check `if not cleaned.strip(): return` prima del parse
- Fix `AttributeError: list has no .get`: `facts = data if isinstance(data, list) else data.get("facts", [])`
- Aggiunto try/except annidato per `repair_json` con fallback su `logger.warning` + return

### `backend/app/ai/parser.py`
- Fix lint SIM102: `if isinstance(wu, dict) and "key" in wu` (singolo if invece di nested)

### `frontend/src/types/index.ts`
- `CharacterData.hp` ora `number | { current: number; max: number }`
- `max_hp` reso opzionale

### `frontend/src/components/character/character-sheet.tsx`
- Aggiunta funzione `getHP(char)` che normalizza entrambi i formati HP (flat e nested)
- Condizione `if (!char || !char.name)` per evitare render con dati vuoti

### `frontend/src/components/game-view.tsx`
- Aggiunto `updateWorldState` e `updateCharacter` all'hook del store
- Nel handler `turn_complete`: sincronizza `world_state` e `character_data` dal backend nel store locale
- `CombatTracker` ora legge da `campaign.world_state.combat_state` (persistente) invece di `streaming.combatState` (volatile)
- Import aggiornati: `CharacterData`, `WorldState`

### `frontend/src/components/new-campaign.tsx`
- Aggiunto **Step 3** di character creation UI (senza AI):
  - Selezione classe (6 opzioni con descrizione e stat)
  - Campo background (testo libero)
  - Preview stats in tempo reale
  - `buildCharacterData()` costruisce il `character_data` completo lato frontend
- Progress bar aggiornata a 3 step
- `character_data` completo inviato al backend alla creazione campagna

---

## Risultato

- 239 test passano
- Ruff lint + format clean
- ESLint clean
