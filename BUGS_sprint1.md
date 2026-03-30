# Test Plan — Sprint 1-bis

---

## Setup

- [ ] `docker-compose down && docker-compose up --build -d`
- [ ] Aspetta che i container siano up (backend, db, redis)
- [ ] Apri il frontend su `http://localhost:5173`
- [ ] Tieni aperto il terminale con `docker-compose logs -f backend`

---

## TEST 1 — Character Creation UI (nuovo flow)

**Obiettivo**: verificare che la creazione personaggio avvenga tramite form UI senza AI

**Azioni**:
1. Clicca "New Saga"
2. **Step 1**: seleziona un template qualsiasi → clicca
3. **Step 2**: inserisci nome eroe (es. "Aldric"), lascia campaign name vuoto, seleziona death mode "Cronista" → clicca "Next: Create Character"
4. **Step 3**: verifica che appaia il form character creation
   - [ ] Vedi 6 classi selezionabili (Warrior, Rogue, Mage, Ranger, Cleric, Bard)
   - [ ] Cliccando su una classe, il **preview stats cambia in tempo reale**
   - [ ] Il preview mostra nome, HP, e la griglia delle 6 ability con modificatore
   - [ ] Campo background (testo libero)
5. Seleziona "Warrior", inserisci background "Un ex soldato in cerca di riscatto"
6. Clicca "Begin the Saga"
7. **Nei log backend**: cerca `character_data` nella richiesta POST `/campaigns`
   - [ ] `character_data` contiene `name`, `hp: {current: 22, max: 22}`, `abilities: {strength: 16, ...}`
   - [ ] **NON** appare `character_generation` nei log del primo turno

---

## TEST 2 — Character Sheet visibile e popolato

**Obiettivo**: verificare che il character sheet mostri i dati creati nel form

**Azioni** (dopo TEST 1, nella schermata di gioco):
1. Guarda il pannello laterale sinistro

**Verifiche**:
- [ ] Nome personaggio visibile ("Aldric")
- [ ] HP bar mostra `22/22` con barra rossa piena
- [ ] Level 1, XP 0
- [ ] AC: 10, Gold: 10
- [ ] Griglia Abilities mostra STR 16 (+3), CON 14 (+2), DEX 12 (+1), etc.
- [ ] **NON** appare "No character data"

---

## TEST 3 — HP si aggiorna dopo combat_damage

**Obiettivo**: verificare che il character sheet rifletta i danni ricevuti

**Azioni**:
1. Invia azione aggressiva: `"Attacco il goblin con la spada"`
2. Continua il combattimento per 2-3 turni

**Nei log backend**:
- [ ] `world_updates_applying format=list keys=[...]` mostra le keys effettive (es. `["combat_start", "combat_damage"]`)
- [ ] Dopo ogni turno con `combat_damage`, il log `turn_completed` mostra il modello usato

**Nel frontend** (dopo ogni `turn_complete`):
- [ ] **HP nel character sheet si aggiorna** — se ricevi danno, la barra rossa si accorcia
- [ ] I numeri `current/max` cambiano (es. da `22/22` a `17/22`)
- [ ] La barra si aggiorna proporzionalmente

---

## TEST 4 — CombatTracker appare e persiste

**Obiettivo**: verificare che il CombatTracker sia visibile durante il combattimento

**Azioni** (continuazione TEST 3):
1. Dopo l'azione aggressiva che avvia il combattimento

**Verifiche**:
- [ ] Il **CombatTracker appare** nel frontend (non era mai apparso prima)
- [ ] Mostra "COMBAT - Round N"
- [ ] Mostra la lista dei combattenti con HP (player + nemici)
- [ ] **Persiste tra i turni** — non scompare dopo il turno, rimane visibile
- [ ] Evidenzia il combattente corrente con bordo diverso

**Nei log backend**:
- [ ] `keys=["combat_start", ...]` nel primo turno di combattimento
- [ ] Nei turni successivi: `keys=["combat_damage", ...]` (NON ripete combat_start)

---

## TEST 5 — CombatTracker scompare dopo combat_end

**Obiettivo**: verificare che il CombatTracker sparisca correttamente

**Azioni**:
1. Continua il combattimento fino alla vittoria (o invia `"Uccido il goblin"`)
2. Aspetta che il DM narri la vittoria

**Nei log backend**:
- [ ] `keys=["combat_end", ...]` nell'ultimo turno di combattimento

**Nel frontend**:
- [ ] Il **CombatTracker scompare** dopo il turno con combat_end
- [ ] Il character sheet rimane visibile con HP aggiornato

---

## TEST 6 — HP nested format stabile

**Obiettivo**: verificare che HP rimanga leggibile dopo i damage update

**Azioni** (durante combattimento):
1. Guarda il character sheet dopo ogni turno con danno

**Verifiche**:
- [ ] HP **non mostra mai** `[object Object]` o `undefined/undefined`
- [ ] Sia prima del combattimento (flat o nested) che dopo i danni, il formato è sempre `N/N`
- [ ] La barra HP non è mai al 0% quando il personaggio ha ancora HP

---

## TEST 7 — fact_extraction non crasha più

**Obiettivo**: verificare che il background task fact_extractor non generi più errori

**Nei log backend** (dopo qualsiasi turno):
- [ ] **NON** appare `fact_extraction_failed` con `JSONDecodeError`
- [ ] **NON** appare `fact_extraction_failed` con `AttributeError: list has no .get`
- [ ] Se appare `fact_extraction_unparseable` — è un warning non bloccante, non un errore (accettabile)
- [ ] In alcuni turni appare `facts_extracted count=N` — conferma che funziona

---

## TEST 8 — world_state sincronizzato nel frontend

**Obiettivo**: verificare che il frontend riceva lo stato aggiornato dal backend

**Azioni**:
1. Esegui un'azione che modifica world_state (es. combattimento, scoperta di un luogo)
2. Apri DevTools del browser → Application → (oppure Console) e cerca lo store Zustand

**Nei log backend**:
- [ ] Il `turn_complete` WebSocket message include `world_state` e `character_data` (visibile nel Network tab del browser → WS frames)

**Nel frontend**:
- [ ] Dopo ogni turno, il character sheet mostra dati aggiornati senza ricaricare la pagina

---

## TEST 9 — Azione non-combat non mostra CombatTracker

**Obiettivo**: verificare che azioni pacifiche non attivino il combat tracker

**Azioni**:
1. Invia: `"Parlo con il barista"`
2. Invia: `"Esamino la stanza"`

**Verifiche**:
- [ ] CombatTracker **non appare**
- [ ] Nei log: `world_updates_applying keys=[...]` non contiene `combat_start`
- [ ] Il character sheet è visibile e stabile

---

## TEST 10 — Nuova campagna con classe diversa da Warrior

**Obiettivo**: verificare i preset per ogni classe

**Azioni**:
1. Crea una nuova campagna, al Step 3 seleziona "Mage"
2. Verifica il preview: INT 16 (+3), WIS 14 (+2), CON 8 (-1)
3. HP dovrebbe essere 19 (20 base - 1 per CON -1)
4. Crea la campagna e verifica nel character sheet

**Verifiche**:
- [ ] Abilities corrette per il Mage
- [ ] HP coerente con il CON modifier
- [ ] Background inserito visibile nel character sheet

---

## TEST 11 — WebSocket non crasha alla disconnessione

**Obiettivo**: verificare il fix del WS crash

**Azioni**:
1. Avvia un turno (invia un messaggio)
2. **Mentre il DM sta rispondendo** (streaming attivo), naviga via dalla pagina o chiudi il tab

**Nei log backend**:
- [ ] Appare `ws_disconnected` (info log normale)
- [ ] **NON** appare `RuntimeError: Cannot call "send" once a close message has been sent`
- [ ] **NON** appare la doppia traceback di WebSocketDisconnect

---

## Checklist Rapida (smoke test)

| Test | Passa? |
|------|--------|
| Form creazione personaggio in 3 step | |
| Character sheet visibile con dati corretti | |
| HP si aggiorna dopo danno | |
| HP non mostra [object Object] | |
| CombatTracker appare in combattimento | |
| CombatTracker persiste tra i turni | |
| CombatTracker scompare dopo combat_end | |
| fact_extractor non crasha | |
| WS disconnect non genera crash | |
| Azioni pacifiche non attivano combat | |
