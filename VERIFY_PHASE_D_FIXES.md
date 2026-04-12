# VERIFY_PHASE_D_FIXES.md

**Scope**: fix ai bug validati in `VERIFY_AGENTIC_MIGRATION.md`
**Data**: 2026-04-11

## Setup prima di testare

```bash
cd backend && alembic upgrade head   # applica migration 002_add_narration_segments
cd backend && uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

---

## 1. Combat bootstrap

**Modifica**: nuovo gruppo `combat_entry` in `saga.config.yaml` → `start_combat` sempre disponibile. Gli altri combat tools (`apply_damage`, `end_combat`, `update_hp`, `request_dice`) restano gated su `combat_active`. Prompt DM rafforzato: "you MUST call start_combat in the same step as your narration".

**Procedura**: crea campagna, digita `"I attack the bandit"`.

**Atteso**:
- Il DM chiama `start_combat` nello stesso step in cui narra l'attacco
- Il CombatTracker appare, bordo rosso (`combat_fury` mood)
- Dal turno successivo `apply_damage`/`end_combat`/`request_dice` sono accessibili

**Verifica**:
```bash
grep "tool_groups_resolved" logs/saga.log | tail -2
# Primo turno: tools include "start_combat" (via combat_entry)
# Dopo start_combat: tools include "apply_damage", "end_combat", "request_dice"
grep "start_combat" logs/saga.log | tail -3
```




--> start_combat è tra i tool che ci sono










---

## 2. Dice persistence + label

**Modifiche**:
- `websocket.py`: estrae `dice_roll` events in un dict e lo salva nel Turn (prima era `dice_rolls=None`)
- `dice-roller.tsx`: pre-reveal mostra ora `{Skill} DC {dc}` invece di solo "Roll!"
- `agent.py`: se il DM non passa `check`, fallback a `"{stat} check"`

**Procedura**: esegui azione con dado (`"I try to pick the lock"`), **NON cliccare** il dado, poi ricarica (F5). Ripeti cliccando per rivelare, poi F5 di nuovo.

**Atteso**:
- Pre-click: bottone mostra `PERCEPTION DC 15 Roll!` (non più solo "Roll!")
- Dopo F5 (sia revealed che non): il dado **riappare nella chat history**, nella posizione corretta (inline con il testo dello step in cui è stato chiamato)
- La stat/skill label è corretta

**Verifica**:
```bash
# Il DB ora ha dice_rolls popolato
psql -c "SELECT turn_number, dice_rolls FROM turns ORDER BY turn_number DESC LIMIT 3"
grep "ai_raw_response" logs/saga.log | grep "request_dice" | tail -3
```

---

## 3. Dice inline (non più in fondo)

**Modifiche**:
- `StreamEvent.step_index` aggiunto, taggato su ogni yield dell'agent loop
- Turn ha un nuovo campo JSONB `narration_segments: [{step, text, dice, npc_dialogues}]`
- `narrative-stream.tsx` renderizza per segments: `text → NPC bubbles → dice` per ogni step

**Procedura**: azione complessa che genera multi-step (es. `"I search the room then check the desk"`) con almeno un dado.

**Atteso**:
- Il dado appare **tra il testo dello step in cui è stato chiamato e il testo dello step successivo**, non più sempre in fondo al turno
- Al reload la posizione inline è mantenuta (letto da `narration_segments`)

**Verifica**:
```bash
psql -c "SELECT turn_number, jsonb_array_length(narration_segments) FROM turns WHERE narration_segments IS NOT NULL ORDER BY turn_number DESC LIMIT 3"
```

---

## 4. NPC dialogue bubble

**Modifiche**:
- Nuovo componente `npc-bubble.tsx`: icona User + nome NPC + dialogo tra virgolette + azione in corsivo
- NPC dialogues raggruppati per step in `narration_segments`
- Prompt DM: "NPC dialogue is ALREADY shown as dedicated bubble. Do NOT write dialogue in quotes, do NOT describe what the NPC said."
- Prompt DM: regola OBBLIGATORIA "if ANY NPC speaks → you MUST call invoke_npc"

**Procedura**: parla con un NPC (`"I talk to the innkeeper"`).

**Atteso**:
- Appare una bubble dedicata con icona User, nome NPC, dialogo tra virgolette, azione in corsivo (se presente)
- Il DM **non** ripete né parafrasa il dialogo nel testo successivo
- Il DM chiama `invoke_npc` (non risponde più direttamente narrando il dialogo)

**Verifica**:
```bash
grep "invoke_npc" logs/saga.log | tail -5
# Dovrebbe apparire a ogni interazione con NPC. Nei turni successivi, step_text
# del DM non dovrebbe contenere virgolette di dialogo.
```

---

## 5. Prompt tuning: items/mood/NPC consistency

**Modifica**: sezione "Tool usage guidance" del prompt DM riscritta con regole obbligatorie:
- Items → `add_item`/`remove_item` obbligatori a ogni cambio inventario
- Mood → `set_scene_mood` obbligatorio a ogni shift tonale
- NPC → `invoke_npc` obbligatorio se NPC parla
- Dice → sempre passare `check` label esplicito

**Procedura**: gioca 5+ turni vari (pickup, uso item, shift di mood, dialoghi).

**Atteso**: i tool vengono chiamati in modo più consistente rispetto al playtest precedente (prima erano ~30% dei casi skippati).

**Verifica**:
```bash
grep "agent_step" logs/saga.log | tail -10
# Conteggio: add_item/remove_item dovrebbero comparire ogni volta che il player
# interagisce con oggetti; set_scene_mood ogni transizione tonale significativa.
```

---

## 6. Auto-scroll

**Modifica**: `useEffect` → `useLayoutEffect` con dipendenza su `streamingVersion` (lunghezza totale del testo nei segments). Scrolla a ogni chunk streamato, non solo a cambio di state batchato.

**Procedura**: gioca 10+ turni riempendo la schermata, poi invia una nuova azione.

**Atteso**: durante lo streaming, la chat scrolla verso il basso automaticamente, mantenendo visibile l'ultimo testo.



AUTO SCROLL SI, 




---

## 7. Regressioni da verificare

| Area | Comportamento atteso |
|------|---------------------|
| Turni vecchi (pre-migration) | `narration_segments=NULL` → fallback al rendering legacy (`turn.narration` flat) |
| WS `await:dice_reveal` | Il server si mette in pausa finché non arriva `dice_revealed` dal client |
| Death system | Overlay appare correttamente (⚠️ pre-existing type errors in `game-view.tsx:284-310` non toccati) |
| Chat history reload | Turni precedenti si ricaricano via `/journal/{campaign_id}` con `narration_segments` popolato |

---

## Note

- **Migration obbligatoria**: `alembic upgrade head` prima del primo playtest, altrimenti i nuovi turni falliranno su `turns.narration_segments`.
- **request_dice fuori combat**: attualmente gated su `combat_active`. Se vuoi skill check sempre disponibili anche fuori combat (es. Perception su strada), va spostato in `core` o in un nuovo gruppo `dice` always-on. Non fatto in questo sprint.
- **suggest_actions tool** (bug #9 del vecchio verify): rimandato a sprint successivo.
