# VERIFY_AGENTIC_MIGRATION.md

**Scope**: Phase D — Agentic DM migration (tool-calling architecture)
**Data**: 2026-04-03
**Test da fare prima di eliminare i file legacy** (`streaming.py`, `parser.py`, ecc.)

---

## Setup

```bash
make test-infra-up          # PostgreSQL + Redis
cd backend && uv run alembic upgrade head
cd backend && uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

Assicurati di avere una API key valida in `.env` (`GOOGLE_AI_API_KEY` o altra).

---

## 1. Turno base — narrazione streamma correttamente

**Procedura**: Crea una campagna, scrivi un'azione qualsiasi (es. "I look around the room"), premi Act.

**Atteso**:
- Il testo della narrazione appare token by token in tempo reale
- L'indicatore di processing (`DM considers...`) appare durante lo streaming
- Al termine, `turn_complete` arriva e la narrazione si consolida
- L'header mostra il turn counter aggiornato

**Log da verificare**:
```bash
grep "ai_request" logs/saga.log | tail -1
grep "ai_raw_response" logs/saga.log | tail -5
grep "agent_step" logs/saga.log | tail -5
```
Atteso: `ai_request` mostra provider/model/importance. `ai_raw_response` per ogni step con `raw_preview` e `tool_calls`. Almeno 1 step per turno.

---

## 2. Dice — click-to-reveal con loop in pausa

**Procedura**: Esegui un'azione che richiede un tiro (es. "I try to pick the lock", "I attempt to sneak past the guard", "I attack the goblin").

**Atteso**:
1. La narrazione streamma ("You attempt to...")
2. Il DM chiama `request_dice` — appare il dado in stato "Roll!" (non ancora rivelato)
3. Il server manda `await:dice_reveal` — il server è in pausa
4. L'utente **clicca** il dado: animazione 1.5s, poi mostra totale + DC + outcome
5. Al click, il frontend manda `{"type": "dice_revealed"}` al WebSocket
6. Il server riceve il risultato e continua: la narrazione del risultato streamma subito dopo
7. Il turno si completa normalmente

**Cosa verificare**:
- Il dado appare PRIMA che il DM finisca di narrare (appena `request_dice` viene chiamato)
- Finché non si clicca, il DM non continua (non arrivano nuovi chunk di narrazione)
- Dopo il click, la narrazione riprende in pochi secondi

**Log**:
```bash
grep "request_dice\|await_player" logs/saga.log | tail -5
```

---

## 3. Combattimento completo

**Procedura**: Avvia un combattimento (es. "I attack the bandit near the door"). Gioca 3+ turni di combat.

**Atteso**:

**Inizio combattimento**:
- Il DM chiama `start_combat` — il CombatTracker appare con l'ordine d'iniziativa
- Arriva anche l'evento `combat:start` (compatibilità frontend)
- `scene_mood` diventa `combat_fury` (bordo rosso sul narrative panel)

**Durante il combattimento**:
- Il DM chiama `apply_damage(target="Goblin", amount=8)` — HP del goblin scende nel CombatTracker
- Il DM chiama `apply_damage(target="PlayerName", amount=3)` — HP del player scende nella CharacterSheet
- Gli eventi `tool:executed` arrivano per ogni danno
- `current_turn_index` avanza nel CombatTracker (il turno passa al prossimo combattente)

**Fine combattimento**:
- Il DM chiama `end_combat` — CombatTracker sparisce
- Arriva evento `combat:end`

**Log**:
```bash
grep "start_combat\|end_combat\|apply_damage" logs/saga.log | tail -10
```

---

## 4. Movimento e location

**Procedura**: "I walk to the marketplace" o "I go through the door to the north".

**Atteso**:
- Il DM chiama `move_to(location="Marketplace")`
- L'header si aggiorna con la nuova location
- **Log**: `grep "location_updated\|move_to" logs/saga.log | tail -3`

---

## 5. NPC dialogue — DM riceve risposta e reagisce

**Procedura**: "I talk to the innkeeper" o "I ask the guard about the missing merchant".

**Atteso**:
1. Narrazione DM iniziale streamma
2. Il DM chiama `invoke_npc(name="Innkeeper")` — appare la dialogue bubble dell'NPC
3. La risposta dell'NPC (1-2 frasi in character) appare come `npc:dialogue` event
4. Il DM riceve il dialogo come tool result e può continuare a narrare tenendo conto di cosa ha detto l'NPC

**Log**:
```bash
grep "invoke_npc\|npc_dialogue" logs/saga.log | tail -5
```

---

## 6. Multi-step loop — più tool in un turno

**Procedura**: Fai un'azione complessa (es. "I search the room for traps, then take the key from the table").

**Atteso**:
- Un turno può avere più step LLM visibili nei log (`agent_step step=0`, `step=1`, ecc.)
- In un solo step il DM può emettere più tool calls (es. `add_item` + `log_event` + `set_scene_mood`)
- Il turno non supera 5 step (`saga_max_agent_steps=5`)
- Se il DM finisce prima, il loop si ferma (non sempre 5 step)

**Log**:
```bash
grep "agent_step" logs/saga.log | tail -10
# atteso: step=0 spesso è sufficiente, step=1 se c'erano tool calls
```

---

## 7. Item add/remove

**Procedura**: "I pick up the torch from the wall" e poi "I use my health potion".

**Atteso**:
- `add_item(name="Torch")` → l'inventario nella CharacterSheet si aggiorna dopo `turn_complete`
- `remove_item(name="Health Potion")` → l'oggetto sparisce dall'inventario
- Evento `tool:executed` arriva per entrambi

---

## 8. Scene mood

**Procedura**: Gioca in situazioni diverse (esplorazione, dialogo teso, combattimento).

**Atteso**:
- Il `narrative panel` cambia colore di bordo/sfondo in base al mood
- Il DM chiama `set_scene_mood` durante i turni
- La transizione CSS è smooth (1.5s)

---

## 9. Chat history dopo reload (da Sprint 2)

**Procedura**: Gioca 3 turni. Ricarica la pagina (F5).

**Atteso**:
- Tutti i turni riappaiono (narrazione, dadi storici)
- L'ordine è corretto (turno 1, 2, 3)
- Le dice rolls storiche sono visibili ma non più rivelabili (già revealed)
- Nessun messaggio "Your adventure awaits..." se ci sono turni

---

## 10. Messaggio utente nella chat (da Sprint 2)

**Procedura**: Scrivi un'azione e premi Act.

**Atteso**:
- La bolla dorata con il testo dell'azione appare istantaneamente a destra
- Si resetta a ogni nuovo turno
- Dopo `turn_complete`, l'azione è parte del turno storico

---

## 11. Auto-scroll (da Sprint 2)

**Procedura**: Riempi la schermata di turni, poi invia un'azione.

**Atteso**: La chat scrolla automaticamente verso il basso durante lo streaming.

---

## 12. Back button e navigazione (da Sprint 2)

**Procedura**: Dalla game view, clicca `←` nell'header.

**Atteso**: Naviga a `/` senza errori. WebSocket si chiude correttamente.

---

## 13. Error recovery (da Sprint 2)

**Procedura**: Metti una API key invalida, invia un'azione.

**Atteso**:
- L'indicatore di processing si resetta
- L'input box torna abilitata
- Nessun crash, nessun loop infinito

---

## 14. Death system (regressione)

**Procedura**: Fai scendere HP a 0 (combattimento aggressivo in modalità Cronista).

**Atteso**: Death overlay appare con il messaggio corretto. In Cronista: "Near Death". In Destino: "Fate Intervenes". In Ironman: "You Have Fallen" + campagna completata.

---

## 15. Logging — ai_request + ai_raw_response

**Verifica completa dei log**:
```bash
# Ogni turno deve avere esattamente 1 ai_request
grep '"event":"ai_request"' logs/saga.log | tail -5

# Ogni step del loop ha un ai_raw_response
grep '"event":"ai_raw_response"' logs/saga.log | tail -10

# agent_step mostra quanti round ha fatto il loop
grep '"event":"agent_step"' logs/saga.log | tail -10

# Nessun errore di formato JSON (erano comuni prima)
grep '"event":"parse_error"\|json_decode_error' logs/saga.log | tail -5
# atteso: 0 risultati — il formato è garantito dall'SDK
```

---

## Regressioni possibili

| Problema | Causa | Come verificare |
|----------|-------|----------------|
| Il DM non chiama i tool (solo narra) | System prompt non descrive bene i tool o modello non supporta function calling | Controllare `ai_raw_response` — `tool_calls` dovrebbe essere non-vuoto quando appropriato |
| Loop si ferma al primo step senza tool calls | Il DM termina subito (corretto se non servono tool) | Normale. Verificare solo in combat che chiami `apply_damage` |
| `apply_damage` con target sbagliato | Il DM usa nome diverso da quello in initiative_order | Controllare log `combat_damage_target_not_found` |
| Dadi non si sbloccano dopo il click | Il WS `dice_revealed` non arriva al server | Console browser: verificare `{"type":"dice_revealed"}` inviato |
| Il DM non chiama `start_combat` | Ha descritto il combattimento senza avviarlo | Nessun CombatTracker visibile. Verificare nei log manca `start_combat` |
| `invoke_npc` con NPC non nel world_state | NPC creato al volo — fallback graceful in `npc_director` | NPC risponde comunque, ma senza profilo memorizzato |
| `suggested_actions` non appaiono | Rimosso da DMResponse, nessun tool equivalente | **Regressione nota** — aggiungere `suggest_actions` tool in sprint successivo |
| `advance_time` non aggiorna l'header | Il DM non chiama il tool o `time_of_day` non mappa su meta | Verificare `world_state.meta.clock` dopo turno |
| Multipl step in parallelo per Google | Gemini tool streaming accumula tutto — nessun chunk intermedio | Atteso: narrazione arriva tutta alla fine del primo step. Funzionale ma meno live |

---

## TODO — lavoro rimasto aperto dopo questa sessione

### Immediato (prima del merge/deploy)

1. **Test di integrazione con DB reale** — lanciare `make test-infra-up` e `uv run pytest tests/integration` per verificare che il turn pipeline completo funzioni end-to-end con agent.py.

2. **Test con Google Gemini (provider default)** — verificare tool calling effettivo con `gemini-3-flash-preview`. I test unit mockano il provider, serve un test con API reale.

3. **Eliminare file legacy** dopo integrazione test verde:
   - `backend/app/core/streaming.py` → sostituito da `agent.py`
   - `backend/app/core/turn.py` → non più usato nel pipeline principale
   - `backend/app/ai/parser.py` → JSON healing non più necessario
   - `backend/app/ai/stream_extractor.py` → NarrationExtractor non più usato
   - `backend/app/ai/schemas/dm_response.py` → sostituito dai tool schemas (verificare che nessun test importi da qui)

4. **`suggested_actions` mancanti** — il vecchio DMResponse aveva un campo `suggested_actions` mostrato come pulsanti. Ora non viene più prodotto. Opzioni: (a) aggiungere un tool `suggest_actions(actions: list[str])`, (b) generare post-loop, (c) rimuovere feature per ora.

### Sprint successivo (polish)

5. **Frontend tool events inline** — `add_item`/`remove_item` → toast notification visiva. `update_hp`/`apply_damage` → flash momentaneo sulla HP bar. Attualmente i pannelli si aggiornano solo a `turn_complete`.

6. **Playtest bugs Phase B** (5 bug in memoria) — validare e fixare in sprint dedicato.

7. **Contextual loading** — `build_context()` non usa ancora l'output del Semantic Resolver per caricare selettivamente NPC/location. Rinviato a Phase E.

8. **Hybrid search** — pgvector + tsvector query in `memory/semantic.py`. Infrastruttura pronta (tabella + indici), query non implementata. Phase E.

9. **`advance_time` tool e GameClock** — verificare che `advance_game_clock()` aggiorni correttamente `meta.clock.current_season` e `time_of_day` e che l'header li mostri.

10. **OpenRouter / Local provider test** — aggiungere `local_model_url` e `openrouter_api_key` al `.env.example`. Testare con Ollama o LM Studio in locale.

11. **`agent_step` log per monitoring** — considerare di aggiungere il log `agent_step` anche al pannello di sviluppo nel frontend (solo in dev mode).
