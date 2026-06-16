# FASE 3 — Piano C: "Differenziatori"

> Tutte le modifiche apportate nella Fase C del progetto SAGA/Wyrd.
> Data: 2026-03-28
> Test: 198 → 230 passing (230 unit)

---

## Sommario

La Fase C implementa i tre sistemi che differenziano SAGA da ogni competitor narrativo: un Death System con tre modalità di gioco distinte, un Save System con guard anti-combattimento, e un Combat System DM-driven completo con stato persistente, tracker visuale e feedback UI di morte. Il backend acquisisce: schema world_state v4 con `combat_state` e `destino_lives`, tre handler tipizzati per il combattimento nel registry dell'updater, logica di morte in un modulo dedicato, `COMBAT_PROMPT` iniettato nel system prompt del DM, e propagazione eventi WebSocket. Il frontend acquisisce: `CombatTracker` overlay con HP bar e ordine di iniziativa, overlay di morte contestuale per ogni modalità, e store aggiornato per il nuovo stato.

---

## Added

### Backend — Nuovi file

#### `backend/app/core/death.py`
Modulo dedicato al death system — tutta la logica di morte è isolata qui.

- `DeathCheckResult(dataclass)`: `is_dead`, `death_mode`, `action` (`"alive" | "near_death" | "fate_intervention" | "dead"`), `narrative_instruction`, `destino_lives_remaining: int | None`.
- `check_player_death(character_data, death_mode, world_state)`: controlla se `hp.current <= 0` e restituisce il risultato appropriato in base alla modalità.
  - **Cronista**: HP resettato a 1, `action="near_death"`, istruzione narrativa per quasi-morte drammatica con conseguenze (cattura, ritirata, perdita equipaggiamento).
  - **Destino**: verifica `destino_lives` nel world state (default 3 se assente). Se `lives > 0`: `action="fate_intervention"`, `destino_lives_remaining = lives - 1`, istruzione con costo escalante per numero intervento (1°=Minor, 2°=Major, 3°=Severe). Se `lives == 0`: `action="dead"`, morte permanente.
  - **Ironman**: `action="dead"` immediato, istruzione per scena di morte memorabile + epilogo.

### Backend — Nuovi test

#### `backend/tests/unit/test_death_system.py` (16 test)
Copre: vivo con HP > 0 (no modifica), near_death Cronista (HP→1), Cronista con HP negativi, Destino fate_intervention con lives decrement, costo narrativo diverso per ogni intervento (1°/2°/3°), Destino senza lives è dead, Ironman permanent death, correttezza campo `death_mode` nel result.

#### `backend/tests/unit/test_combat_handlers.py` (17 test)
Copre: `combat_start` → active=True, round=1, player in initiative, nemici inclusi, ordine decrescente, type="player"; `combat_end` → active=False, initiative_order=[], round=0; `combat_damage` → nemico prende danno, HP non sotto zero, player danno riflesso in char_data, healing aumenta HP, capped a max_hp, target sconosciuto non solleva errore.

---

## Changed

### Backend

#### `backend/app/memory/world_state.py`
- `CURRENT_SCHEMA_VERSION`: 3 → 4.
- Aggiunta `"combat_state"` e `"destino_lives"` a `ALLOWED_WORLD_STATE_KEYS`.
- Aggiunta migration v3→v4:
  ```python
  @_register_migration(3)
  def _migrate_v3_to_v4(state: dict) -> dict:
      state.setdefault("combat_state", {
          "active": False, "round": 0,
          "initiative_order": [], "current_turn_index": 0,
      })
      state.setdefault("destino_lives", 3)
      state["meta"]["schema_version"] = 4
      return state
  ```

#### `backend/app/memory/updater.py`
Aggiunti 3 handler al registry dopo `event_log_entry`:

- **`combat_start`**: legge `change.enemies` dal world_update. Tira iniziativa player (1d20 + DEX modifier da `char_data.abilities`) e per ogni nemico (1d20). Ordina per iniziativa decrescente. Imposta `combat_state = {active: True, round: 1, initiative_order: [...], current_turn_index: 0}`.
- **`combat_end`**: resetta `combat_state` a stato inattivo (active=False, round=0, lista vuota).
- **`combat_damage`**: trova il combattente per nome (case-insensitive). Se `type=="player"`: modifica `char_data.hp.current` con clamp `[0, max_hp]` e sincronizza `combatant.hp`. Se enemy: modifica solo `combatant.hp` con clamp a 0.

#### `backend/app/ai/prompts/dm.py`
- Aggiunta costante `COMBAT_PROMPT` con istruzioni tipizzate per segnalare inizio/fine combattimento e danni:
  - `combat_start`: `change.enemies` con `name`, `hp`, `max_hp`.
  - `combat_damage`: `target` (nome combattente), `change` (numero negativo=danno, positivo=cura).
  - `combat_end`: nessun parametro aggiuntivo.
- `build_dm_system_prompt()`: `parts.append(COMBAT_PROMPT)` dopo i death mode prompts.

#### `backend/app/core/engine.py`
- Aggiunti import: `check_player_death`, `CampaignStatus`.
- Aggiunto `"combat_start"`, `"combat_end"`, `"death_event"` al Literal type di `StreamEvent`.
- In `process_game_turn_streaming()`, dopo l'applicazione dei world_updates:
  1. Se `combat_state` è nel nuovo world state e `active=True`: yield `StreamEvent(type="combat_start", data=combat_state)`.
  2. Se `active=False` e precedentemente era attivo: yield `StreamEvent(type="combat_end")`.
  3. Controlla HP player: se `<= 0` esegue `check_player_death(char_data, death_mode, world_state)`.
  4. Se Destino: decrementa `world_state["destino_lives"]`, persiste.
  5. Se morto (`is_dead=True`): imposta `campaign.status = CampaignStatus.COMPLETED`.
  6. Yield `StreamEvent(type="death_event", data={...DeathCheckResult fields...})`.
- `turn_result` include `combat_state` e `death_event` fields.
- Funzione non-streaming: `in_combat` letto da `combat_state.active` (non da campo legacy).

#### `backend/app/api/saves.py`
Guard anti-combattimento prima della creazione del manual save:
```python
combat_active = (campaign.world_state or {}).get("combat_state", {}).get("active", False)
if combat_active:
    raise HTTPException(status_code=400, detail="Cannot save during combat")
```

#### `backend/app/api/websocket.py`
Aggiunti 3 handler per i nuovi event type:
- `combat_start` → invia `{"type": "combat:start", ...combat_state_data}`.
- `combat_end` → invia `{"type": "combat:end"}`.
- `death_event` → invia `{"type": "death:event", ...death_result_data}`.

### Frontend

#### `frontend/src/types/index.ts`
- Aggiunte interfacce `CombatantInfo` e `CombatState`:
  ```ts
  interface CombatantInfo {
    name: string; initiative: number; hp: number; max_hp: number;
    type: "player" | "companion" | "enemy";
  }
  interface CombatState {
    active: boolean; round: number;
    initiative_order: CombatantInfo[]; current_turn_index: number;
  }
  ```
- Aggiunta interfaccia `DeathEvent`:
  ```ts
  interface DeathEvent {
    is_dead: boolean; death_mode: string;
    action: "alive" | "near_death" | "fate_intervention" | "dead";
    narrative_instruction: string; cost_hint?: string;
    destino_lives_remaining?: number;
  }
  ```
- `WorldState`: sostituito `in_combat?: boolean` con `combat_state?: CombatState`, aggiunto `destino_lives?: number`.

#### `frontend/src/components/combat/combat-tracker.tsx` (nuovo)
`CombatTracker` — overlay fisso in alto a destra, appare solo se `combat_state.active`.

- Intestazione rossa "COMBAT - Round N".
- Lista combattenti con: numero iniziativa (grigio), nome color-coded (blu=player, verde=companion, rosso=enemy), HP bar 60px con colore progressivo (verde >50%, giallo 25-50%, rosso <25%), contatore HP numerici.
- Combattente corrente: sfondo `rgba(cc3333, 0.2)` + bordo sinistro rosso.
- Combattenti morti: opacità 40% + strikethrough sul nome.

#### `frontend/src/stores/game-store.ts`
- Aggiunti import `CombatState`, `DeathEvent`.
- Aggiunto `"combat_state"` e `"destino_lives"` a `ALLOWED_WORLD_STATE_KEYS`.
- Aggiunti `combatState: CombatState | null` e `deathEvent: DeathEvent | null` a `StreamingState`.

#### `frontend/src/components/game-view.tsx`
- Import `CombatTracker`, `CombatState`, `DeathEvent`.
- Store selectors per `combatState` e `deathEvent`.
- WebSocket handlers: `combat:start` → `setStreaming({combatState})`, `combat:end` → `setStreaming({combatState: null})`, `death:event` → `setStreaming({deathEvent})`.
- **Rendering `<CombatTracker combatState={combatState} />`**: montato nell'albero JSX condizionalmente se `combatState?.active`.
- **Overlay di morte**: modale full-screen condizionale su `deathEvent`:
  - Cronista → titolo "Near Death!" giallo, sottotitolo narrativo, pulsante "Continue".
  - Destino → titolo "Fate Intervenes!" viola, `cost_hint` come sottotitolo, pulsante "Continue".
  - Ironman → titolo "You Have Fallen" rosso, senza pulsante (campagna terminata).

### Test aggiornati

| File | Modifica |
|------|----------|
| `test_world_state.py` | schema_version 3→4, aggiunto `test_migrate_v3_to_v4`, assertions per `combat_state` e `destino_lives` nella migrazione v0→latest, fixture v4 per test up-to-date |
| `test_game_clock.py` | schema_version 3→4, rinominato `test_v0_to_v3_full_migration` → `test_v0_to_v4_full_migration`, aggiunto check `combat_state`/`destino_lives`, `test_v3_not_modified` → `test_v3_migrates_to_v4` |

---

## Architettura — Decisioni chiave

### DM-driven combat
Il DM controlla completamente il combattimento via narrazione + `world_updates` tipizzati. Non esiste un parser di azioni di combattimento separato — il DM riceve il `COMBAT_PROMPT` con le istruzioni sui tipi di update (`combat_start`, `combat_damage`, `combat_end`) e li emette autonomamente. Il backend gestisce lo stato, il frontend lo visualizza. Questo approccio è più robusto di un parser rule-based e produce narrativa più ricca.

### World State schema v4
`combat_state` e `destino_lives` sono chiavi top-level nel world state (non annidati in `narrative` o `player`). Scelto per:
- Accesso diretto senza deep traversal nel codice engine.
- Coerenza con `clock` che è già top-level.
- La migration v3→v4 è idempotente e aggiunge i default corretti.

### Death system modulare
`death.py` è un modulo puro (nessuna dipendenza da DB, LLM, o framework). Prende dati, restituisce un dataclass. L'engine gestisce gli effetti collaterali (decremento destino_lives, campaign status). Questo rende il death system testabile in isolamento senza mock e facilmente estendibile (es. death saving throws in v2).

### Save guard
Il blocco del salvataggio durante il combattimento è implementato nel layer API (`saves.py`), non nell'engine. Scelta corretta: è una business rule dell'endpoint, non della logica di gioco.

---

## Non implementato (rinviato)

- **Death saving throws (Ironman)**: la spec originale descriveva 3 turni di death saving throws. Implementato invece come morte diretta a 0 HP con istruzione narrativa per il DM. I death saving throws sono candidati per Phase D o v2 — aggiungono complessità UX non necessaria per il playtest.
- **Enemy AI comportamenti** (carica/hit-and-run/ranged): delegato completamente al DM via narrazione. Non esiste logica AI separata per i nemici in v1 — il DM è il loro cervello.
- **Companion agisce autonomamente in combattimento**: i companion esistono nell'ordine di iniziativa ma la loro azione è narrata dal DM, non da una call LLM separata. Actor-Director per companion combat è candidato per Phase D.
- **Auto-save post-turno**: la tabella e gli endpoint esistono (da Fase A), ma il trigger automatico post-turno non è stato aggiunto in questa fase — in Phase D insieme alla UI Save Browser.
- **Timeline forking UI**: l'endpoint `POST /saves/:id/load` esiste già. L'albero di fork nella lista campagne è Phase D.
- **Toggle suono** e altri fix UX: rimandati a Phase D (vedi `memory/project_playtest_bugs.md`).
