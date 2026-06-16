# Sprint 1 — Combat Fixes & AI Logging

**Data**: 2026-03-30
**Status**: Completato
**Obiettivo**: Risolvere il bug root-cause che impediva al CombatTracker, agli aggiornamenti HP e alla death logic di funzionare.

---

## Root Cause

Il DM emetteva `world_updates` come oggetto singolo (`{}`) invece che come array (`[{}]`). Questo faceva sì che ogni update finisse nel path "legacy merge" invece dei typed handler (`combat_start`, `combat_damage`, `combat_end`), rompendo l'intera pipeline di combattimento.

---

## Cambiamenti

### `ai/prompts/dm.py`
- **BASE_DM_PROMPT**: riformulato per insegnare il formato array tipizzato per `world_updates`; aggiunta regola anti-code-fence (niente ` ```json ``` `); aggiunta regola anti-player-speaking; aggiunta difesa da prompt injection.
- **COMBAT_PROMPT**: riscritto con esempi JSON concreti (combat_start, mid-combat, end); regole esplicite su nesting vietato, `combat_start` emesso una sola volta, `change` sempre intero non-zero.

### `ai/schemas/dm_response.py`
- `world_updates` da `dict | None` a `list[dict] | dict | None` — accetta entrambi i formati durante la validazione Pydantic.

### `ai/parser.py`
- Aggiunta funzione `_normalize_world_updates()`: converte dict con campo `key` in lista, estrae automaticamente i nested typed dicts (es. `player_damage: {key: "combat_damage", ...}` dentro un `combat_start`).
- Logging structlog su ogni parse: `raw_preview`, esito, tipo e count di `world_updates`.

### `core/engine.py`
- Invertito ordine dei branch: `list` è ora il path primario, `dict` il fallback legacy.
- Aggiunto logging `ai_raw_response` (prima del parse) in entrambe le funzioni streaming e non-streaming.

### `tests/unit/test_parser_normalize.py` *(nuovo)*
- 9 test che coprono tutti i casi di normalizzazione: None, lista passthrough, dict singolo wrappato, nested dicts estratti, legacy dict senza `key`.

---

## Risultato

- 239 test passano (era 230 prima dello sprint)
- Ruff lint clean
- Il path tipizzato (`apply_typed_updates`) ora viene raggiunto correttamente in tutti i turni di combattimento
