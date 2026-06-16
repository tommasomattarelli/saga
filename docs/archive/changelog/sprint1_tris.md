# Sprint 1-tris — Hotfix Combat Damage + Logging + WS

**Data**: 2026-03-31
**Status**: Completato
**Obiettivo**: Fix 3 bug emersi dal playtest di Sprint 1-bis.

---

## Fix applicati

### 1. combat_damage non applicava danno al player

**Causa**: il COMBAT_PROMPT usava `"target": "PlayerName"` come placeholder letterale. Il DM inviava `"PlayerName"` invece del nome reale (es. "Aldric"). Il handler matchava per nome esatto → nessun match → HP invariato.

**Fix**:
- `backend/app/ai/prompts/dm.py` — COMBAT_PROMPT riscritto: istruisce esplicitamente il DM a usare il nome reale del personaggio dalla sezione "Player Character". Aggiunta regola "ALWAYS emit combat_damage for EVERY hit that lands".
- `backend/app/memory/updater.py` — `_handle_combat_damage()`: aggiunto fallback — se target è `"player"` o `"playername"` (generici), matcha automaticamente il combattente di tipo `"player"`. Aggiunto warning log se nessun match.

### 2. WebSocket crash su turn_complete

**Causa**: il `send_json` del `turn_complete` non era protetto. Se il client disconnetteva durante il processing (dopo DB commit ma prima dell'invio), crashava con `RuntimeError: Cannot call "send" once a close message has been sent`.

**Fix**: `backend/app/api/websocket.py` — wrappato `send_json` di `turn_complete` in try/except con warning log.

### 3. Log troncati / nessun file di log

**Causa**: structlog usava il default (console stdout senza configurazione), i log venivano troncati da Docker.

**Fix**:
- `backend/app/logging_setup.py` — Nuovo file: configura structlog con doppio output (console key=value + file JSON lines). File di log rotante: `logs/saga.log`, 10 MB x 3 backup.
- `backend/app/main.py` — Chiama `setup_logging()` all'import.
- Log completi leggibili con: `cat backend/logs/saga.log`

---

## Bug ancora aperti (da Sprint 1-bis)

| Bug | Stato | Note |
|-----|-------|------|
| current_turn_index nel CombatTracker sempre 0 | APERTO | Non c'è logica che avanza il turno tra player/nemici. Cosmetico, non bloccante |
| DM a volte non emette combat_damage spontaneamente | MONITORARE | Il prompt ora è più esplicito, verificare con il file di log completo |

---

## Risultato

- 239 test passano
- Ruff lint + format clean
- ESLint clean
