# Sprint 2 — Verification Plan

**Data**: 2026-03-31
**Scope**: All remaining playtest bugs (Sprint 2+3 merged) + engine refactor

---

## Test nuovi — Sprint 2

### 1. Chat history persistente al reload (C4)

**Come testare**: Avvia una campagna, gioca 2-3 turni. Poi ricarica la pagina (F5).

**Evento atteso**: Tutti i turni precedenti riappaiono nella chat, incluse narrazione, dadi, azioni suggerite. Non serve riscrivere nulla.

**Cosa verificare**:
- I turni appaiono nell'ordine corretto (turno 1, 2, 3)
- Le dice rolls dei turni passati sono visibili e cliccabili
- Le suggested actions dei turni passati NON sono cliccabili (solo l'ultimo turno le mostra)
- Il messaggio "Your adventure awaits..." NON appare se ci sono turni

---

### 2. Messaggio utente visibile nella chat (A3)

**Come testare**: Scrivi un'azione nella input box (es. "I attack the goblin") e premi Act.

**Evento atteso**: Immediatamente dopo il click, il testo dell'azione appare come una bolla dorata allineata a destra, PRIMA che il DM inizi a rispondere.

**Cosa verificare**:
- La bolla appare istantaneamente (non aspetta la risposta DM)
- La bolla scompare quando arriva `turn_start` (il DM inizia a pensare)
- Dopo `turn_complete`, il turno storico mostra la `player_action` come bolla sopra la narrazione DM
- Anche dopo un reload, i turni storici mostrano la player_action come bolla
- Il bottone "Continue" (che manda "wait") mostra anch'esso la bolla

---

### 3. Auto-scroll durante lo streaming (A5)

**Come testare**: Gioca abbastanza turni da riempire lo schermo. Poi invia un'altra azione.

**Evento atteso**: Durante lo streaming della narrazione DM, la chat scrolla automaticamente verso il basso. L'utente non deve scrollare manualmente.

**Cosa verificare**:
- Lo scroll avviene con animazione smooth (non jump brusco)
- Lo scroll si attiva sia durante la narrazione che quando arriva un nuovo turno
- Se l'utente scrolla manualmente verso l'alto, il prossimo chunk di narrazione lo riporta in basso

---

### 4. Dadi sotto la narrazione (A2)

**Come testare**: Fai un'azione che richiede un tiro di dado (es. "I try to pick the lock").

**Evento atteso**: Il DiceRoller (animazione dado, DC, risultato) appare SOTTO il testo della narrazione, non sopra.

**Cosa verificare**:
- Nei turni storici: il dado appare dopo il testo narrativo
- Durante lo streaming live: il dado appare dopo il testo che sta arrivando
- Il click-to-reveal del dado funziona ancora normalmente

---

### 5. WebSocket race condition (A6)

**Come testare**: Naviga rapidamente tra la lista campagne e una campagna attiva (avanti/indietro veloce).

**Evento atteso**: Nessun crash, nessun errore in console. La connessione WebSocket si chiude e riapre correttamente.

**Cosa verificare**:
- No errori `WebSocket is closed before the connection is established` in console
- No state updates su componenti unmounted (warning React)
- Tornando alla campagna, il WebSocket si riconnette e funziona

---

### 6. Stagione nell'header (M2)

**Come testare**: Avvia una campagna e gioca almeno 1 turno.

**Evento atteso**: L'header mostra la stagione corrente dopo il day/time. Es: "Turn 3 — Forest Clearing — Day 1, Morning — Spring"

**Cosa verificare**:
- La stagione appare se `world_state.meta.current_season` esiste
- Se il campo non esiste, non appare nulla (no "undefined", no crash)
- La stagione si aggiorna se il DM emette un cambio di stagione

---

### 7. Back button alla lista campagne (M4)

**Come testare**: Dalla game view, clicca la freccia `←` nell'header (a sinistra del nome campagna).

**Evento atteso**: L'app naviga alla lista campagne (`/`).

**Cosa verificare**:
- Il bottone è visibile e ha un hover state
- Cliccando, si torna alla home/lista campagne
- Lo stato della campagna non viene perso (rientrando si vedono i turni)

---

### 8. Errore visibile dopo fallimento AI (M9)

**Come testare**: Difficile da testare manualmente senza simulare un errore AI. Per testing:
- Metti una API key invalida nel `.env`
- Oppure disconnetti internet dopo il login

**Evento atteso**: Dopo che l'AI fallisce, il messaggio "DM considers your action..." scompare e l'utente può riprovare. Il frontend non rimane bloccato in stato "processing".

**Cosa verificare**:
- L'indicatore di processing si resetta
- L'input box torna abilitata
- L'utente può inviare una nuova azione

---

### 9. Location handler (Backend)

**Come testare**: Gioca un turno in cui il DM sposta il personaggio (es. "I walk to the marketplace"). Controlla i log backend.

**Evento atteso**: Nel log appare `location_updated location=Marketplace` (o simile). Il campo `world_state.location` nell'header si aggiorna.

**Cosa verificare**:
- `cat logs/saga.log | grep location_updated` mostra la nuova location
- L'header mostra la nuova location dopo il turno
- Il fallback generico non viene più usato per le location (no `typed_update_generic_fallback` per location)

---

### 10. Combat turn index avanza (Backend/Frontend)

**Come testare**: Inizia un combattimento e fai almeno 2 turni di attacco.

**Evento atteso**: Nel CombatTracker, l'indicatore del turno corrente avanza dopo ogni `combat_damage` event.

**Cosa verificare**:
- `current_turn_index` nel `combat_state` non è sempre 0
- L'indice wrappa correttamente (torna a 0 dopo l'ultimo combattente)
- Il CombatTracker evidenzia il combattente corrente

---

### 11. Engine split (Backend — solo regressione)

**Come testare**: `cd backend && uv run pytest tests/unit tests/integration -v`

**Evento atteso**: 239 test passano. Nessuna regressione.

**Cosa verificare**:
- I 3 file (`engine.py`, `turn.py`, `streaming.py`) sono tutti sotto 300 righe
- `ruff check .` e `ruff format --check .` passano
- L'import `from app.core.engine import process_game_turn_streaming` nei test vecchi è aggiornato

---

## Regressioni da Sprint 1 / 1-bis / 1-tris

| Cosa fare | Evento atteso |
|-----------|---------------|
| Invia un'azione durante il combattimento | `combat_damage` applica danno all'HP del player (non a "PlayerName" letterale) |
| Gioca un turno qualsiasi | `world_updates` nel log è formato `list` con `keys=[...]` |
| Crea nuova campagna (step 3: form personaggio) | Il form mostra 6 classi, stats, background. Submit crea il personaggio |
| Gioca turno dopo creazione | Character sheet mostra nome, HP bar, abilità, oro |
| Gioca turno con combattimento | CombatTracker appare e persiste tra i turni |
| Gioca turno dopo combat_end | CombatTracker scompare |
| HP scende a 0 | Death overlay appare (cronista/destino/ironman) |
| Controlla `logs/saga.log` | File esiste, JSON lines, log completi non troncati |
| Controlla log per `ai_request` | Log mostra provider, model, temperature, system_prompt_preview |
| Controlla log per `ai_raw_response` | Log mostra raw_length e raw_preview della risposta AI |
| DM non wrappa JSON in code fences | Narrazione pulita, nessun ```json visibile |
| DM non parla per il player | Il DM narra solo la reazione del mondo, non le parole/decisioni del player |
| `combat_start` emesso una sola volta | Il DM non ri-emette combat_start nei turni successivi |
| Bottone "Continue" visibile | Appare quando `requires_player_action` è false |
| Location nell'header | Mostra la location corrente, non "Unknown location" (dopo primo turno) |
| Turn counter | Si aggiorna dopo ogni turn_complete |
| Suggested actions solo ultimo turno | Solo l'ultimo turno mostra i bottoni azione suggerita |
| `fact_extractor` non crasha | Nessun `fact_extraction_failed` nel log (verificare con `grep fact_extraction logs/saga.log`) |
