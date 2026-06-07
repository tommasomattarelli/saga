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



primo turno questi log: 
{"campaign_id": "0429f4cf-696b-415e-b236-f8a727709826", "tool_count": 10, "tools": ["add_item", "advance_time", "change_npc_disposition", "invoke_npc", "log_event", "move_to", "remove_item", "set_scene_mood", "start_combat", "update_quest"], "event": "tool_groups_resolved", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-12T20:18:29.951088Z"}
tommasomattarelli@LAPTOP-41P6SR3J:~/saga/backend$


 tool_calls=[{'name': 'start_combat', 'args': {'enemies': [{'hp': 12, 'max_hp': 12, 'name': 'Thug Leader'}, {'name': 'Thug Lackey 1', 'hp': 8, 'max_hp': 8}, {'name': 'Thug Lackey 2', 'hp': 8, 'max_hp': 8}]}}, {'name': 'set_scene_mood', 'args': {'mood': 'combat_fury'}}, {'name': 'advance_time', 'args': {'minutes': 1}}]




PERO NON CHIAMA MAI GLI ALTRI TOOL:


tommasomattarelli@LAPTOP-41P6SR3J:~/saga/backend$ grep "start_combat" logs/saga.log | tail -3
{"campaign_id": "0429f4cf-696b-415e-b236-f8a727709826", "tool_count": 10, "tools": ["add_item", "advance_time", "change_npc_disposition", "invoke_npc", "log_event", "move_to", "remove_item", "set_scene_mood", "start_combat", "update_quest"], "event": "tool_groups_resolved", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-12T20:21:49.799297Z"}
{"step": 0, "text_len": 530, "tool_calls": ["start_combat", "set_scene_mood", "advance_time"], "event": "agent_step", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-12T20:21:56.062557Z"}
{"step": 0, "raw_length": 530, "raw_preview": "Ti pari davanti la minaccia imminente, il pugnale che si muove in un arco disperato per intercettare il primo attacco. Il teppista a sinistra agita un pugno nodoso, ma tu riesci a deviarlo con l'avambraccio, sentendo una fitta di dolore per l'impatto. Il capo, pi\u00f9 astuto, cerca di afferrarti il pols", "tool_calls": [{"name": "start_combat", "args": {"enemies": [{"hp": 12, "name": "Capo dei Malviventi", "max_hp": 12}, {"name": "Scagnozzo Malvivente 1", "max_hp": 8, "hp": 8}, {"name": "Scagnozzo Malvivente 2", "max_hp": 8, "hp": 8}]}}, {"name": "set_scene_mood", "args": {"mood": "combat_fury"}}, {"name": "advance_time", "args": {"minutes": 1}}], "event": "ai_raw_response", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-12T20:21:56.063708Z"}
tommasomattarelli@LAPTOP-41P6SR3J:~/saga/backend$


e non si vede nemmeno la barra di combattimento iniziato anche. 
altra cosa, la persistenza dei nomi se sono di npc che non esistono. ma forse è dato dal fatto che non starta il combattimento


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
psql -c "SELECT turn_number, dice_rolls FROM turns ORDER BY turn_number DESC LIMIT 3"   -> non va comando, come devo fare?
grep "ai_raw_response" logs/saga.log | grep "request_dice" | tail -3
```


IL DADO PERSISTE ED è IN MEZZO AI CHUNK CORRETTAMNETE. UNICA COSA NON RIMANE RE-ROLLATO. quindi al refresh (che persiste) ritorna come se fosse appena creato, coin la possibilita di ricliccare. ma stesso risultato correttamente



tommasomattarelli@LAPTOP-41P6SR3J:~/saga/backend$ grep "ai_raw_response" logs/saga.log | grep "request_dice" | tail -3
{"step": 0, "raw_length": 386, "raw_preview": "Ignorando per un istante i due scagnozzi ai lati, concentri la tua attenzione sulla minaccia pi\u00f9 grande, il bruto sogghignante che li comanda. Ti spingi in avanti con il piede posteriore, un'esplosione di movimento nello spazio ristretto. Il vicolo \u00e8 angusto, il tuo bersaglio \u00e8 un muro di muscoli e ", "tool_calls": [{"name": "start_combat", "args": {"enemies": [{"name": "Thug Leader", "hp": 12, "max_hp": 12}, {"max_hp": 8, "hp": 8, "name": "Thug 1"}, {"max_hp": 8, "hp": 8, "name": "Thug 2"}]}}, {"name": "request_dice", "args": {"reason": "To stab the Thug Leader with the dagger.", "check": "Attack"}}, {"name": "set_scene_mood", "args": {"mood": "combat_fury"}}, {"name": "advance_time", "args": {"minutes": 1}}], "event": "ai_raw_response", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-12T20:24:41.787511Z"}
tommasomattarelli@LAPTOP-41P6SR3J:~/saga/backend$




dopo cliccato aprte la nuova stream correttamente, con esito coerente con quello successo. 
unica cosa, dopo questo turno è partito ol combat (non so come mai, forse perche è unico turno in cui ho fatto step 0 e poi step1? altri fermi a step 0) e ha emesso aplly damage, ma non vedo le modifiche, nemmeno al refresh





ANDANDO AVANTI UN PO NON USA MAI END COMBAT PERO. sono scappato dal combvattimento con successo (check su DEX) ma il box combattimento rimane in alto a destra e tutti i tool del combattimento sono disponibili




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




SI è inlin e mantenuto, ma come detto prima non rimane rollato al refresh



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





SI. perfetto questo va benissimo. appare tutto e DM non ripete nulla




trovato questo baco pero 
Al sentire il nome del Gran Maestro, un'emozione quasi impercettibile attraversa il volto della Sorella della Brace. I suoi occhi si fissano sui tuoi per un istante e le sue dita si stringono leggermente attorno alla candela che tiene in mano. Fa un cenno del capo, un gesto lento e deliberato, indicando una panca di legno poco distante.

Sister Ember
“Grand”

La donna si volta, il suo movimento è fluido e misurato. Il cappuccio le ricade leggermente all'indietro, rivelando un viso sereno incorniciato da ciocche di capelli scuri. I suoi occhi, del colore del miele riscaldato, ti scrutano con una gentilezza che non nasconde una profonda stanchezza. Solleva una mano per proteggere la fiamma di una candela appena accesa, il suo bagliore che danza sul suo volto.

Sister Ember
“I asked by whom you were sent”

Un'emozione complessa attraversa il volto della Sorella della Brace alla menzione del Gran Maestro. Le sue labbra si stringono in una linea sottile e per un momento i suoi occhi si spostano sulla grande Pietra Brace, come per trarne forza. Fa un cenno lento e deliberato verso una panca di legno vicina.

Sister Ember
“Grand”

Un sospiro quasi impercettibile le sfugge dalle labbra mentre si muove per posare la candela su un supporto di ferro battuto. Il gesto è stanco, carico di un peso che va oltre la semplice fatica fisica. Poi si volta di nuovo verso di te, indicando la panca con un cenno della mano. La luce ambrata della Pietra Brace proietta la sua ombra lunga e tremolante sul pavimento di pietra.

social intrigue


è un loop assurdo e inutile, e sbagliato soprattuto



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





si vengono chiamati in modo consistente.
unica cosa, add item e romevo item vengono chiamati ma nel fortnend in inventario non vedo modifiche, mi da sempre inventario vuoto






---

## 6. Auto-scroll

**Modifica**: `useEffect` → `useLayoutEffect` con dipendenza su `streamingVersion` (lunghezza totale del testo nei segments). Scrolla a ogni chunk streamato, non solo a cambio di state batchato.

**Procedura**: gioca 10+ turni riempendo la schermata, poi invia una nuova azione.

**Atteso**: durante lo streaming, la chat scrolla verso il basso automaticamente, mantenendo visibile l'ultimo testo.



AUTO SCROLL SI, ma quando risponde DM ok. quando manda messaggio user no auto scroll




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
