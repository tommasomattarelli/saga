# Sprint 2 — Playability + Polish + Engine Refactor

**Data**: 2026-03-31
**Status**: Completato
**Obiettivo**: Fix di tutti i bug rimasti dal playtest (Sprint 2+3 del piano originale merged), refactor engine.py per Rule 12.

---

## Bug risolti

### 1. Chat history persa al reload (C4) — CRITICO

**Causa**: `turnHistory` nello store Zustand veniva popolato solo da eventi WebSocket `turn_complete`. Al reload della pagina, lo store si resettava e la chat appariva vuota.

**Fix**:
- `frontend/src/stores/game-store.ts` — Aggiunto metodo `setTurnHistory(turns)` che sovrascrive l'intera lista.
- `frontend/src/components/game-view.tsx` — Dopo `setCampaign(r.data)`, chiama `setTurnHistory(r.data.turns)` per idratare la storia dai dati backend (caricati via `lazy="selectin"` sull'ORM).

### 2. Messaggi utente non visibili nella chat (A3) — ALTO

**Causa**: L'azione del player veniva inviata via WebSocket ma non mostrata localmente. Solo la narrazione DM appariva.

**Fix**:
- `frontend/src/stores/game-store.ts` — Aggiunto campo `pendingAction: string | null` allo streaming state + metodo `setPendingAction()`.
- `frontend/src/components/input/action-input.tsx` — Prima di `wsRef.current.send()`, chiama `setPendingAction(text)`.
- `frontend/src/components/narrative/narrative-stream.tsx` — Aggiunto componente `PlayerBubble` (bolla dorata allineata a destra). Renderizzato sia come `pendingAction` live che come `turn.player_action` nei turni storici.
- `backend/app/api/websocket.py` — Aggiunto `player_action: action` al payload `turn_complete` per rendere l'azione disponibile nei turni idratati.
- `frontend/src/types/index.ts` — Aggiunto campo opzionale `player_action?: string` a `TurnResponse`.

### 3. No auto-scroll durante streaming (A5) — ALTO

**Causa**: Nessuna logica di scroll automatico. L'utente doveva scrollare manualmente per vedere la narrazione in arrivo.

**Fix**:
- `frontend/src/components/narrative/narrative-stream.tsx` — Aggiunto `bottomRef` alla fine del container narrativo + `useEffect` che chiama `scrollIntoView({ behavior: "smooth" })` su ogni aggiornamento di `streaming.currentNarration` o `turnHistory.length`.

### 4. Dadi sopra la narrazione invece che sotto (A2) — ALTO

**Causa**: `DiceRoller` era renderizzato prima del blocco testo sia nei turni completati che nello streaming live.

**Fix**:
- `frontend/src/components/narrative/narrative-stream.tsx` — Spostato `<DiceRoller />` dopo il `<div>` della narrazione in entrambi i contesti (TurnBlock e live streaming).

### 5. WebSocket race condition (A6) — ALTO

**Causa**: Se il componente GameView veniva smontato durante la connessione WS (navigazione rapida), gli handler continuavano a fare state updates su componente unmounted.

**Fix**:
- `frontend/src/components/game-view.tsx` — Aggiunto `isMountedRef` con pattern guard: tutti gli handler WS sono wrappati in una funzione `guard()` che controlla `isMountedRef.current` prima di aggiornare lo stato. Il cleanup setta `isMountedRef.current = false`.

### 6. Stagione non mostrata nell'header (M2) — MEDIO

**Causa**: L'header mostrava solo Day e time_of_day dal clock, ignorando `meta.current_season`.

**Fix**:
- `frontend/src/components/game-view.tsx` — Aggiunto rendering condizionale di `campaign.world_state.meta.current_season` nell'header dopo il clock.

### 7. Nessun back button alla lista campagne (M4) — MEDIO

**Causa**: Non implementato. L'utente non aveva modo di tornare alla lista campagne dal game view.

**Fix**:
- `frontend/src/components/game-view.tsx` — Aggiunto `useNavigate()` + bottone `←` nell'header che naviga a `/`.

### 8. Nessun errore visibile dopo fallimento AI (M9) — MEDIO

**Causa**: Il frontend non aveva un handler per l'evento WS `error`. Se l'AI falliva, il frontend restava bloccato su "The DM considers your action..." indefinitamente.

**Fix**:
- `frontend/src/components/game-view.tsx` — Aggiunto handler `ws.on("error", ...)` che resetta `isProcessing` e `isStreaming`, sbloccando l'input.

### 9. Nessun handler `location` in updater.py — MEDIO

**Causa**: Le location updates del DM cadevano nel fallback generico merge, senza logging e senza validazione.

**Fix**:
- `backend/app/memory/updater.py` — Aggiunto handler `_handle_location()` registrato con `@_register_handler("location")`. Setta `state["location"]` e logga `location_updated`.

### 10. `current_turn_index` sempre 0 nel CombatTracker — BASSO

**Causa**: Nessuna logica avanzava l'indice del turno tra i combattenti. Il CombatTracker mostrava sempre il primo combattente come attivo.

**Fix**:
- `backend/app/memory/updater.py` — In `_handle_combat_damage()`, dopo aver applicato il danno, avanza `current_turn_index` con modulo sulla lunghezza della lista combattenti.

---

## Refactor

### 11. engine.py split (Rule 12: no file > 300 righe)

**Causa**: `engine.py` era 513 righe con due funzioni principali (non-streaming e streaming) + dataclass + costanti.

**Fix**: Split in 3 file:
- `backend/app/core/engine.py` (50 righe) — Dataclass `ProcessedTurn`, `StreamEvent`, costanti condivise.
- `backend/app/core/turn.py` (177 righe) — `process_game_turn()` (pipeline non-streaming).
- `backend/app/core/streaming.py` (294 righe) — `process_game_turn_streaming()` (pipeline streaming).

Import aggiornati in:
- `backend/app/api/websocket.py` — `from app.core.streaming import process_game_turn_streaming`
- `backend/app/services/turn_service.py` — `from app.core.turn import process_game_turn`
- `backend/tests/unit/test_turn_pipeline_a1.py` — Patch target aggiornati a `app.core.turn.*`

---

## Bug ancora aperti

| Bug | Stato | Note |
|-----|-------|------|
| DM a volte non emette combat_damage spontaneamente | MONITORARE | Prompt esplicito, verificare con log |
| DM chiede tiri di dado troppo spesso (M6) | PARZIALE | Prompt aggiornato in Sprint 1, ma potrebbe servire tuning |
| Prompt injection hardening (M7) | GIA' PRESENTE | Backend ha `detect_injection()` + DM prompt ha regola "You are ONLY a DM" |

---

## Risultato

- 239 test passano
- Ruff lint + format clean
- ESLint clean
- Tutti i file sotto 300 righe (Rule 12)
