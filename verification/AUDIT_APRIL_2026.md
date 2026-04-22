# Audit SAGA — Aprile 2026

**Data**: 2026-04-22  
**Branch**: `refactor`  
**Scope**: Backend (`app/`), Frontend (`frontend/src/`), Test suite, Lint, SOTA research  
**Auditato da**: saga-audit team (backend-auditor, frontend-auditor, test-runner, web-scout, doc-writer)

---

## Sommario esecutivo

| Area | HIGH | MED | LOW | Stato |
|------|------|-----|-----|-------|
| Backend | 9 | 12 | 9 | open |
| Frontend | 3 | 7 | 10 | open |
| Test & Lint | — | 2 | 1 | parziale |
| Arch. decisions | — | 4 | — | pending |
| **Totale** | **12** | **25** | **20** | |

---

## Backend — Finding

### HIGH (9)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-H1 | `app/ai/tools/dm_tools.py` (636 righe) | God file: tool registry + 14 implementazioni tool + dispatcher tutto nello stesso file. Viola regola 12. | `[ ]` |
| B-H2 | `app/core/agent.py` (493 righe) | God class: streaming + dice + NPC + tool dispatch + death check. Viola regola 12. | `[ ]` |
| B-H3 | `app/core/streaming.py` (294 righe) | Dead code post-migrazione LangGraph. Nessun caller vivo. Da eliminare. | `[ ]` |
| B-H4 | `app/core/dm/dm_tools_executor.py:114` | Apre una nuova DB session per ogni NPC call dentro il turn → N sessioni extra per turn. **Fix architetturale**: ricevere il campaign object già fetchato via LangGraph state invece di riaprire sessione. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 3. | `[ ]` |
| B-H5 | `app/core/dm/dm_nodes.py:42` | Due sessioni concorrenti sullo stesso Campaign row → race condition su `turn_number`. **Fix architetturale**: `context_node` carica e chiude; solo `post_process_node` scrive. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 3. | `[ ]` |
| B-H6 | `app/api/websocket.py:47,251` | DB session tenuta aperta per tutta la durata di una turn (secondi/minuti). Esaurisce il connection pool. | `[ ]` |
| B-H7 | `app/services/campaign_service.py:28` vs `app/memory/updater.py:35` | Chiave disposition diverge: `"disposition"` vs `"disposition_toward_player"` dal turn 1. Corruzione silenziosa dello world_state. | `[ ]` |
| B-H8 | `app/config.py:8,12` | `jwt_secret` e `api_key_encryption_key` hanno default letterale `"change-me-to-a-random-256-bit-key"` senza startup validation. JWT forgery in produzione se l'operatore dimentica di impostare l'env var. **Fix**: `@model_validator(mode="after")` in `AppConfig` che lancia `ValueError` se il campo inizia con `"change-me"`. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 1. | `[ ]` |
| B-H9 | `app/api/websocket.py:27-32` | JWT token passato come query parameter. Esposto nei log del server, nella browser history, e nei referrer header. **Fix**: migrare a handshake via messaggio iniziale WS o token one-time dal backend. Richiede coordinazione frontend/backend. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 2. | `[ ]` |

---

### MED (12)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-M1 | `app/core/dm/dm_nodes.py` | `context_node` legge Campaign e costruisce il prompt nella stessa sessione DB che poi resta aperta fino al termine del nodo. Refactoring pattern apri→leggi→chiudi→LLM. | `[ ]` |
| B-M2 | `app/ai/router.py` | Score di importanza basato su keyword heuristics hardcoded. Nessun test di regressione sul routing. Aggiungere test unitari sul router. | `[ ]` |
| B-M3 | `app/memory/fact_extractor.py` | Estrazione fatti non limita le dimensioni della risposta LLM; se il modello produce output anomalo la serializzazione fallisce silenziosamente (`summarization_failed=True` non viene settato per i fact). | `[ ]` |
| B-M4 | `app/memory/compressor.py` | Retry con backoff `[1s, 5s, 30s]` — il backoff da 30s può tenere in attesa un background task più a lungo del ciclo successivo. Verificare se il dedup `batch_id` copre il caso di retry concorrenti. | `[ ]` |
| B-M5 | `app/core/dm/dm_helpers.py` | Funzione `build_context()` supera 150 righe di logica concatenata senza suddivisione. Candidato a splitting in builder dedicati per segmento (history, recalled_memories, scene). | `[ ]` |
| B-M6 | `app/ai/prompts/dm.py` | `BASE_DM_PROMPT` e `DEATH_MODE_PROMPT` sono stringhe letterali nel modulo. Con l'aggiunta di nuove regole diventano difficili da versionare/testare. Valutare migrazione a template YAML. | `[ ]` |
| B-M7 | `app/core/dm/dm_nodes.py` | `post_process_node` esegue clock advance, death check e segment split in sequenza sincrona. Se uno step fallisce il turn viene persisted in stato inconsistente. Aggiungere transazione esplicita. | `[ ]` |
| B-M8 | `app/services/campaign_service.py` | `create_campaign` non valida che `template.world_state` contenga i campi obbligatori prima di copiarlo in `Campaign.world_state`. Un template malformato produce errori runtime al primo turn. | `[ ]` |
| B-M9 | `app/api/` (generale) | Nessun rate limiting sugli endpoint `/turns`. Un client può inondare il backend con LLM calls. Aggiungere rate limit per `user_id` (es. 10 req/min). | `[ ]` |
| B-M10 | `app/security/encryption.py` | AES-256 key derivata da `api_key_encryption_key` senza salt per-user. Se la chiave viene compromessa, tutti i record sono decifrabili in bulk. | `[ ]` |
| B-M11 | `app/core/dm/dm_nodes.py` | `route_after_tools` non ha test di integrazione end-to-end sul percorso `consecutive_empty_steps ≥ 2 → exit`. Solo test unitari sul routing. | `[ ]` |
| B-M12 | `app/core/agent.py` vs `app/core/dm/dm_graph.py` | `_meaningful_tools` duplicata in entrambi i file con valori divergenti. Fix: definire una volta sola in `app/ai/tools/dm_tools.py` e importare da entrambi i caller. Vedi AGENTIC_ARCHITECTURE.md §"Refactor Candidates — `_meaningful_tools` Planned Consolidation". | `[ ]` |

---

### LOW (9)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-L1 | `app/models/` | Mancano indici su `turns.campaign_id` e `memory_facts.campaign_id`. Su campagne lunghe (500+ turn) le query di compressione diventano lente. | `[ ]` |
| B-L2 | `app/core/dm/dm_tools_executor.py` | Tool sort (request_dice → others → invoke_npc) implementato con chiave numerica hardcoded `{0,1,2}`. Fragile se si aggiungono nuovi tool con priorità. Usare enum. | `[ ]` |
| B-L3 | `app/ai/npc_director.py` | `last_interactions` troncato agli ultimi 3. Non configurabile. Aggiungere a `saga.config.yaml`. | `[ ]` |
| B-L4 | `app/api/campaigns.py` | Export JSON non include `memory_facts`. Un import su altra istanza perde tutta la memoria semantica. | `[ ]` |
| B-L5 | `app/core/combat.py` | Initiative order non gestisce i pareggi (stesso valore d20 per due combatants). Comportamento non deterministico. | `[ ]` |
| B-L6 | `app/ai/prompts/presets.py` | Preset `horror` e `grimdark` producono testi molto simili in playtest. Differenziare le linee guida stilistiche. | `[ ]` |
| B-L7 | `templates/` | Schema JSON (`templates/schema.json`) non ha versioning. Un template creato con v1 schema sarà silently incompatible dopo modifiche. | `[ ]` |
| B-L8 | `app/config.py` | `AppConfig` non espone la versione dell'app. Difficile fare diagnostica su deployment con versioni diverse. | `[ ]` |
| B-L9 | `app/memory/updater.py` | `update_global_summary()` non ha limite di token sul global_summary in ingresso. Su campagne molto lunghe il prompt di summarization può eccedere il context window. | `[ ]` |

---

## Frontend — Finding

### HIGH (3)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-H1 | `shared/stores/auth-store.ts` | `accessToken` + `refreshToken` salvati in localStorage in chiaro. XSS su qualsiasi dipendenza compromessa svuota i token. Migrare a httpOnly cookies o memory-only store. | `[ ]` |
| F-H2 | `features/game/components/game-view.tsx:39` | Race condition: `submitScrollRef.current` mutato nel body del componente, può diventare `null` tra `onMutate` e la callback di `requestAnimationFrame`. | `[ ]` |
| F-H3 | `features/character/components/character-sheet.tsx:181` | `archetype` non è in `CharacterData` interface. Utilizzato con cast `as unknown as Record<string, unknown>`. Type safety violata. | `[ ]` |

---

### MED (7)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-M1 | `shared/stores/game-store.ts` | Store Zustand non ha reset esplicito al logout. Dati di campagna precedente possono persistere in memoria dopo il cambio utente. | `[ ]` |
| F-M2 | `features/narrative/components/narrative-stream.tsx` | SSE event listener non viene rimosso su unmount del componente. Memoria leak su navigazione veloce. | `[ ]` |
| F-M3 | `features/narrative/components/dice-roller.tsx` | `revealedCount` usato ma non dichiarato correttamente — causa errore ESLint residuo. | `[ ]` |
| F-M4 | `features/game/components/action-input.tsx` | Input non sanitizzato lato client prima dell'invio. Il backend sanitizza (`sanitize_player_input`) ma il frontend non dà feedback immediato su input troppo lunghi o caratteri non validi. | `[ ]` |
| F-M5 | `features/character/` | Nessun loading skeleton su `CharacterSheet` durante il fetch iniziale. Flash di contenuto vuoto visibile su connessioni lente. | `[ ]` |
| F-M6 | `shared/services/` | Client API non gestisce il caso di token scaduto durante una SSE stream in corso. L'utente vede uno stream interrotto senza messaggio di errore. | `[ ]` |
| F-M7 | `features/narrative/` | Nessun test unitario sui componenti narrativi (NarrativeStream, DiceRoller). Regressioni di rendering non rilevabili con il solo ESLint. | `[ ]` |

---

### LOW (10)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-L1 | `features/game/components/game-view.tsx` | Mood CSS transitions non hanno `prefers-reduced-motion` media query. Accessibilità. | `[ ]` |
| F-L2 | `shared/stores/` | Nessun middleware di logging su Zustand in development mode. Difficile debuggare sequenze di azione. | `[ ]` |
| F-L3 | `features/character/components/character-sheet.tsx` | Valori ability score (STR, DEX, ...) hardcoded nel componente invece di essere derivati dall'interface `CharacterData`. | `[ ]` |
| F-L4 | `features/narrative/components/dice-roller.tsx` | Animazione click-to-reveal non disabilitabile da `saga.config.yaml`. Nessun modo per l'utente di disattivarla. | `[ ]` |
| F-L5 | `src/i18n/` | Stringhe di errore dell'API non sono localizzate — vengono mostrate in inglese anche in locale non-EN. | `[ ]` |
| F-L6 | `shared/` | Nessun global error boundary React. Un'eccezione non gestita in un componente smonta l'intera app. | `[ ]` |
| F-L7 | `features/` | Bundle size non monitorato. Nessun budget configurato in Vite. | `[ ]` |
| F-L8 | `features/narrative/` | NPC dialogue bubble non ha attributo `aria-label`. Screen reader non distingue narratore da NPC. | `[ ]` |
| F-L9 | `src/` | Nessun test E2E (Playwright/Cypress). Il golden path (crea campagna → azione → dado) non è coperto da automazione. | `[ ]` |
| F-L10 | `features/game/` | CombatTracker overlay non gestisce il caso di 0 combatants (combat_state.active=true ma initiative_order=[]). Possibile crash di rendering. | `[ ]` |

---

## Test & Lint

### Risultati

| Suite | Risultato | Note |
|-------|-----------|------|
| Backend unit tests (516) | PASS | `pytest tests/unit --noconftest -q` |
| Backend integration tests | PASS | Richiedono infra Docker |
| Frontend tests | PASS | |
| Backend ruff | 14 errori residui | `[ ]` SIM117 nested `with` — fix in corso |
| Frontend ESLint | 1 errore residuo | `[ ]` `revealedCount` non dichiarato in `dice-roller.tsx` — fix in corso |

### Copertura gap

- `[ ]` Nessun test su `route_after_tools` con path `consecutive_empty_steps ≥ 2`
- `[ ]` Nessun test E2E sul golden path frontend
- `[ ]` Nessun test di regressione sul routing modello in `ai/router.py`

---

## SOTA Research — Azioni Raccomandate

### Gap 1 — Dual-Memory Architecture (priorità: ALTA | effort: M)

**Gap**: L'architettura attuale usa rolling summary + pgvector RAG separati ma non li compone in modo ottimale. Research 2025/2026 mostra che dual-memory (compact rolling summary aggiornato continuamente + episodic vector RAG) aumenta il recall su query topic-specifiche dal 41% all'87%.

**Azione**:
- `[ ]` Migrare `memory_facts` da `vector` (float32) a `halfvec` (float16) per ridurre footprint del 50%
- `[ ]` Abilitare BM25 hybrid search (`gameplay.pgvector_hybrid`) per keyword anchoring su nomi propri
- `[ ]` Documentare come `global_summary` + `search_similar_facts` soddisfano già il dual-memory pattern

**Effort stimato**: 3-5 giorni (migrazione Alembic + test di recall)

---

### Gap 2 — Auth token security (priorità: ALTA | effort: S)

**Gap**: Token in localStorage (F-H1) + JWT in query param (B-H9) sono vulnerabilità documentate OWASP Top 10 (A02:2021, A07:2021). In un'app self-hosted con BYOAK, un XSS su qualsiasi dipendenza npm compromette credenziali API key.

**Azione**:
- `[ ]` Migrare auth-store da localStorage a memory-only store (sessionStorage come fallback, non localStorage)
- `[ ]` Passare JWT via header `Authorization: Bearer` o handshake iniziale invece di query param
- `[ ]` Aggiungere startup validation su `jwt_secret` in `config.py` (Pydantic `@field_validator`)

**Effort stimato**: 1-2 giorni

---

### Gap 3 — DB session lifecycle (priorità: ALTA | effort: M)

**Gap**: Tre punti critici (B-H4, B-H5, B-H6) tengono sessioni DB aperte attraverso LLM calls. Con LLM latency di 5-30s per turn, il connection pool si esaurisce già con 5-10 utenti concorrenti. Non è un problema oggi (self-hosted single user) ma blocca qualsiasi scaling futuro e causa race condition su `turn_number`.

**Azione**:
- `[ ]` Refactoring `dm_nodes.py`: pattern apri→leggi→chiudi→LLM→apri→scrivi
- `[ ]` Eliminare session extra in `dm_tools_executor.py:114` — passare dati necessari come argomenti invece di riaprire sessione
- `[ ]` Aggiungere integration test che verifica la race condition su `turn_number` (due turn concorrenti sulla stessa campagna)

**Effort stimato**: 2-3 giorni

---

## Decisioni architetturali pendenti

Queste decisioni sono state concordate dall'audit team e documentate in `AGENTIC_ARCHITECTURE.md`. Richiedono implementazione nei prossimi sprint.

| # | Decisione | File coinvolti | Stato |
|---|-----------|---------------|-------|
| A-1 | **Config secrets startup validation**: `@model_validator` in `AppConfig` che fallisce a startup se `jwt_secret` o `api_key_encryption_key` iniziano con `"change-me"`. | `app/config.py` | `[ ]` |
| A-2 | **JWT WS handshake**: spostare JWT da query param a messaggio iniziale WS (opzione A) o token one-time da `/auth/ws-token` (opzione B). Richiede coordinazione frontend/backend. | `app/api/websocket.py`, `frontend/src/shared/services/` | `[ ]` |
| A-3 | **DB session lifecycle via LangGraph state**: `context_node` carica Campaign e chiude sessione; downstream nodes leggono da `GameState`; solo `post_process_node` apre sessione di scrittura. | `app/core/dm/dm_nodes.py`, `app/core/dm/dm_tools_executor.py` | `[ ]` |
| A-4 | **`_meaningful_tools` unica source of truth**: spostare il set in `app/ai/tools/dm_tools.py` e importare da `agent.py` e `dm_graph.py`. | `app/ai/tools/dm_tools.py`, `app/core/agent.py`, `app/core/dm/dm_graph.py` | `[ ]` |

---

## File da eliminare / refactorare

| File | Motivo | Priorità |
|------|--------|----------|
| `app/core/streaming.py` | Dead code post-LangGraph migration, nessun caller vivo | ALTA — eliminare |
| `app/ai/tools/dm_tools.py` | 636 righe, god file. Split pianificato: `tool_registry.py` + `tools_core.py` + `tools_combat.py` + `tools_social.py` + `tools_inventory.py` + `tool_dispatcher.py` | ALTA — refactorare |
| `app/core/agent.py` | 493 righe, god class. Responsabilità da distribuire tra i nodi LangGraph esistenti | MEDIA — refactorare |
| `app/core/dm/dm_helpers.py` | `build_context()` supera 150 righe. Split in builder per segmento | MEDIA — refactorare |
| `app/ai/prompts/dm.py` | Prompt come stringhe letterali. Candidato a migrazione YAML per versionabilità | BASSA — valutare |
