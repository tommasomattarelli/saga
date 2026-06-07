# VERIFY_V1.md — Sprint v1 Playtest & Regression Guide

**Scope**: Sprint v1 (template world init, tool groups, NPC pre-hook, location post-hook, XML prompt, saga.config.yaml)
**Data**: 2026-04-07
**Come avviare**:
```bash
# Terminal 1
make test-infra-up
cd backend && uv run uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

---

## Setup pre-playtest

1. Crea una campagna con template `tutorial` (The Awakening)
2. Nome personaggio qualsiasi, death mode `destino`
3. **Nuovo**: al momento della creazione il world_state viene seedato dal template — verifica dal log:

```bash
grep "world_state_migrating" logs/saga.log | tail -3
# atteso: migrazione da v0 a v4 (prima campagna)
```

---

## A. TEMPLATE WORLD INITIALIZATION (Nuovo — v1)

### A1. World state seedato alla creazione

**Procedura**: Crea una campagna, poi controlla il DB o la risposta API.

**Atteso**:
- `world_state.npcs.Marta` esiste con `personality`, `motivation`, `secret`, `disposition: 0`
- `world_state.locations["Shrine of First Light"]` esiste con `description` e `connections`
- `world_state.companions.Lyra` esiste con `stats.loyalty: 6`
- `world_state.factions["The Hollow"]` esiste
- `world_state.meta.current_location == "Shrine of First Light"`
- `world_state.time_of_day == "morning"`, `weather == "clear"`
- `campaign.quests.active[0].name == "Who Am I?"`

**Come verificare**:
```bash
# API
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/campaigns/$ID | python -m json.tool | grep -A5 '"npcs"'
```

RISPOSTA CURL: curl -s -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxZjQ3MmZlOS0yNzgwLTRkMGYtOGRkOS0yZjI4NTE2MGVhZjgiLCJleHAiOjE3NzU1ODQ2NTksInR5cGUiOiJhY2Nlc3MifQ.oLQSN-WUjoW6Op4TaxMJwaqpV9p_ekFtSwFGj8SEIVI" http://localhost:8000/api/campaigns/dcd87f35-8e24-4a3f-8d88-28c26b5cadf6 | python -m json.tool | grep -A5 '"npcs"'

---

### A2. Template sconosciuto → 404

**Procedura**: Crea campagna con `template_id: "template_che_non_esiste"`.

**Atteso**: API ritorna `404 Not Found` con `detail: "Template '...' not found"`.


VERIFICATO



---

## B. TOOL GROUPS DINAMICI (Nuovo — v1)

### B1. Tool count fuori dal combattimento

**Procedura**: Primo turno di una campagna appena creata (nessun combattimento attivo).

**Atteso nei log**:
```bash
grep "tool_groups_resolved" logs/saga.log | tail -1
# atteso: tool_count=9 (core: 5 + inventory: 2 + social: 2 perché ci sono NPC)
# apply_damage, end_combat, start_combat, request_dice NON nel set
```

**Tools attivi attesi (no combat)**:
- Core: `move_to`, `advance_time`, `set_scene_mood`, `log_event`, `update_quest`
- Inventory: `add_item`, `remove_item`
- Social (NPCs in world_state): `invoke_npc`, `change_npc_disposition`


tommasomattarelli@LAPTOP-41P6SR3J:/mnt/c/users/asus/desktop/saga$ grep "tool_groups_resolved" backend/logs/saga.log | ta
il -1
{"campaign_id": "dcd87f35-8e24-4a3f-8d88-28c26b5cadf6", "tool_count": 9, "tools": ["add_item", "advance_time", "change_npc_disposition", "invoke_npc", "log_event", "move_to", "remove_item", "set_scene_mood", "update_quest"], "event": "tool_groups_resolved", "level": "info", "logger": "app.core.agent", "timestamp": "2026-04-07T19:00:53.367921Z"}

PERFETTO.




### B2. Tool count durante combattimento

**Procedura**: Invia "I attack the guard" e verifica che il DM chiami `start_combat`. Poi controlla il turno successivo.

**Atteso**: Al turno successivo (combat_state.active = true):
```bash
grep "tool_groups_resolved" logs/saga.log | tail -1
# atteso: tool_count=14 (core+inventory+social+combat)
# apply_damage, end_combat, update_hp, request_dice presenti
```








---

## C. NPC PRE-HOOK (Nuovo — v1)

### C1. NPC con profilo completo dal template

**Procedura**: "I talk to Marta" (NPC presente nel template tutorial).

**Atteso**:
1. Il DM chiama `invoke_npc(name="Marta")`
2. Il NPC director riceve il profilo completo di Marta: `personality: "Warm but shrewd..."`, `motivation: "Protect her village..."`, `secret: "She found a strange artifact..."`
3. Marta risponde in character (non genericamente)

**Log**:
```bash
grep "npcs_invoked" logs/saga.log | tail -1
# atteso: count=1, names=["Marta"]
```

**Regressione**: Marta non deve rispondere "..." (failure silenzioso) né rispondere con un personaggio generico privo di motivazioni.

### C2. NPC non nel template → errore graceful

**Procedura**: Forza il DM a chiamare un NPC non esistente (es. suggerisci "ask Marco the blacksmith" — Marco non è nel tutorial template).

**Atteso**:
- Il DM riceve come tool result: `"NPC 'Marco' is not defined in this world. Do not invoke them."`
- Il DM NON crasha, adatta la narrazione (es. "no blacksmith is known here")
- Nessun errore nel log

### C3. last_interactions ring buffer

**Procedura**: Parla con Marta in 3 turni diversi, poi controlla world_state.

**Atteso**: `world_state.npcs.Marta.last_interactions` ha le ultime 3 interazioni. Al quarto turno il più vecchio è rimosso (max 3).

---

## D. LOCATION POST-HOOK (Nuovo — v1)

### D1. move_to arricchisce il tool result

**Procedura**: "I walk to Thornhaven" o "I go to the Forest Path".

**Atteso nel log**:
```bash
grep "execute_tool\|move_to\|location" logs/saga.log | grep -i "moved" | tail -3
```

Il DM deve ricevere come tool result:
```
Player moved to: Thornhaven
Description: A small village of timber-and-stone buildings. A tavern, a smithy, and a market square.
Connected to: Shrine of First Light, Forest Path, North Road.
```

**Atteso nel gameplay**: Il DM **deve** descrivere l'arrivo a Thornhaven usando i dettagli reali (taverna, fabbro) — non inventarsi una location generica.

### D2. world_state.meta.current_location aggiornato

**Atteso**: Dopo `move_to`, `world_state.meta.current_location` si aggiorna. L'header del frontend mostra la nuova location.

**Regressione**: Il prompt del turno successivo deve mostrare `<location name="Thornhaven">` (non "Shrine of First Light").

---

## E. XML SYSTEM PROMPT (Nuovo — v1)

### E1. Struttura XML nel log

**Procedura**: Controlla `system_prompt_preview` nel log `ai_request`.

```bash
grep "ai_request" logs/saga.log | python -c "import sys,json; [print(json.loads(l).get('system_prompt_preview','')) for l in sys.stdin]" | head -5
```

**Atteso**: Il preview inizia con `<instructions>` — NON con `## Player Character` o ```` ```json ````.

### E2. Token ridotti

**Confronto token prima/dopo**: Il prompt v1 non include il full JSON dump di `world_state`. Si stima una riduzione del 40-60% nelle prime campagne con world_state popolato.

### E3. NPC filtrati per location nel prompt

**Procedura**: Crea campagna, parti allo "Shrine of First Light". Verifica che Marta (location: Thornhaven) NON appaia in `<npcs_present>`.

**Atteso**: `<npcs_present>` è vuoto allo shrine. Dopo `move_to Thornhaven`, `<npcs_present>` mostra Marta e Aldric.

---

## F. DELETE /campaigns/{id} (Nuovo — v1)

### F1. Delete rimuove campagna + cascade

**Procedura**:
```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/campaigns/$ID
# atteso: 204 No Content
```

**Verifica DB**: La campagna, i suoi turni e i memory_facts sono stati eliminati.

### F2. Delete campagna di un altro utente → 403

**Atteso**: `403 Forbidden`.

### F3. Delete campagna inesistente → 404

**Atteso**: `404 Not Found`.

---

## G. saga.config.yaml (Nuovo — v1)

### G1. Cambio modello da config

**Procedura**: Modifica `saga.config.yaml` a root, cambia `dm_narration.low.model` in qualcosa di diverso. Riavvia backend.

**Atteso**: Il log `ai_request` mostra il nuovo modello.

**NON atteso**: Modificare `backend/app/ai/model_config.yaml` (file eliminato — deve dare errore se cercato).

---

## H. REGRESSIONI — Features precedenti

### H1. Narrazione base streamma

**Procedura**: Invia "I look around the shrine".

**Atteso**:
- Testo streamma token by token nel frontend
- Nessun markdown nel testo (`**bold**`, `# header`) — solo prosa
- Nessuna `Tool Call:` o `Mood:` nel testo

### H2. Dice click-to-reveal

**Procedura**: "I try to pick the lock" oppure "I attack the goblin".

**Atteso (sequenza)**:
1. Narrazione DM streamma
2. Dado appare con "Roll!" button — server in pausa
3. Click → animazione 1.5s → mostra totale/DC/outcome
4. Frontend manda `{"type": "dice_revealed"}` (verifica console browser)
5. Narrazione riprende

**Soft lock check**: Se il dado appare ma la narrazione non riprende dopo il click → bug deadlock.

```bash
grep "request_dice\|dice_reveal" logs/saga.log | tail -5
```

### H3. Turn counter si aggiorna

**Atteso**: L'header mostra "Turn N" e si aggiorna dopo ogni `turn_complete` senza F5.

### H4. Chat history dopo reload

**Procedura**: Gioca 3 turni, poi F5.

**Atteso**: Tutti e 3 i turni riappaiono (narrazione + azioni player + dadi storici).

**Log**: `GET /api/journal/{id}` deve tornare i turni.

### H5. User message bubble

**Procedura**: Scrivi "I examine the altar" e premi Act.

**Atteso**: La bolla dorata appare immediatamente a destra PRIMA della risposta DM. Non scompare durante lo streaming.

### H6. Auto-scroll

**Procedura**: Riempi di turni la schermata, invia una nuova azione.

**Atteso**: La chat scrolla automaticamente verso il basso durante lo streaming.

### H7. Combat completo

**Procedura**: "I attack the guard at the gate" o "I draw my sword and charge".

**Atteso**:
1. DM chiama `start_combat` → CombatTracker appare
2. DM chiama `request_dice` per l'attacco
3. DM chiama `apply_damage(target=..., amount=...)` → HP scende
4. `end_combat` → CombatTracker sparisce

**Regressione nota**: Il DM potrebbe descrivere il combattimento senza chiamare `start_combat`. Verifica:
```bash
grep "start_combat" logs/saga.log | tail -3
```

### H8. NPC dialogue bubble

**Procedura**: "I talk to Marta" (dopo `move_to Thornhaven`).

**Atteso**:
- Bubble NPC appare nel frontend con il dialogo in character
- Il DM continua la narrazione tenendo conto di ciò che Marta ha detto

### H9. Multi-step loop

**Procedura**: "I search the room for clues, pick up the key, and note the time".

**Atteso**: Log mostra `agent_step step=0` con tool calls (add_item, log_event, advance_time), poi step=1 solo narrazione.

```bash
grep "agent_step" logs/saga.log | tail -10
```

### H10. Death system

**Procedura**: Usa Cronista, fai scendere HP a 0.

**Atteso**: Death overlay "Near Death", HP resettati a 1, campagna continua.

### H11. Scene mood

**Atteso**: Il pannello narrazione cambia colore (bordo/sfondo) in base al mood. `set_scene_mood("combat_fury")` → bordo rosso.

### H12. Back button + WebSocket cleanup

**Procedura**: Dalla game view, clicca `←` header.

**Atteso**: Naviga a `/` senza errori JS. Nessun `WebSocket is closed` o memory leak.

### H13. Error recovery

**Procedura**: Disabilita internet o metti API key invalida. Invia un'azione.

**Atteso**: L'indicatore `DM considers...` si resetta, l'input box torna abilitata.

---

## I. ANTI-REGRESSIONI da verificare con i test

```bash
cd backend
# Unit + integration completi (309 test, nessuna regressione)
.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q
# atteso: 309 passed

# Solo i nuovi test v1
.venv/Scripts/python.exe -m pytest tests/integration/test_campaign_creation.py tests/integration/test_campaign_delete.py tests/unit/test_tool_groups.py tests/unit/test_dm_prompt_xml.py -v
```

---

## J. LOG CHECKLIST — ogni turno deve avere

```bash
# 1 ai_request per turno (provider, model, importance)
grep "ai_request" logs/saga.log | tail -3

# tool_groups_resolved mostra tool attivi
grep "tool_groups_resolved" logs/saga.log | tail -3

# agent_step mostra n step del loop
grep "agent_step" logs/saga.log | tail -5

# ai_raw_response per ogni step (text_len, tool_calls)
grep "ai_raw_response" logs/saga.log | tail -5

# Nessun json_decode_error
grep "json_decode_error\|parse_error" logs/saga.log | tail -3
# atteso: 0 risultati
```

---

## K. PROBLEMI NOTI / OUT OF SCOPE v1

| Problema | Status | Note |
|----------|--------|------|
| `suggest_actions` non appaiono come pulsanti | Deferred v1 | Rimosso da DMResponse, tool `suggest_actions` non ancora aggiunto |
| NPC non si sposta tra locations autonomamente | Deferred v1.5 | `location` è statico, world_sim non attivo |
| Global story summary assente | Deferred v1.5 | Config `features.global_summary.enabled: false` |
| HTTP `/turn` endpoint usa old pipeline | Tech debt | Frontend usa WS, endpoint ancora attivo ma stale |
| `streaming.py`, `turn.py` ancora presenti | Tech debt | Da eliminare dopo spike test |
| `agent.py` 452 linee | Tech debt | Refactor in v1.5 |
