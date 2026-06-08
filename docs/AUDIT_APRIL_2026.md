# Audit SAGA — Aprile 2026

**Data**: 2026-04-22  
**Branch**: `refactor`  
**Scope**: Backend (`app/`), Frontend (`frontend/src/`), Test suite, Lint, SOTA research  
**Auditato da**: saga-audit team (backend-auditor, frontend-auditor, test-runner, web-scout, doc-writer)

---

## Sommario esecutivo

| Area | HIGH | MED | LOW | Stato |
|------|------|-----|-----|-------|
| Backend | 7 | 11 | 9 | parziale |
| Frontend | 3 | 7 | 10 | parziale |
| Test & Lint | — | 2 | 1 | parziale |
| Arch. decisions | — | 3 | — | pending |
| **Totale** | **10** | **23** | **20** | |

> ~~B-H6, B-H9, A-2~~ rimossi: `websocket.py` era dead code (eliminato 2026-04-22). ~~B-H3~~ eliminato: `streaming.py` rimosso. ~~B-H7, B-M12, F-M3~~ fixati in sessione.
>
> **Update 2026-06-08**: ~~B-H1~~ `dm_tools.py` (640 righe) splittato in `tools_base` + `tools_combat` + `tools_inventory` + `tools_world` + `tools_special` + facade `dm_tools.py` (tutti < 300). ~~B-H2~~ `agent.py` (489 righe) era dead code post-LangGraph (nessun importer) → eliminato. ~~A-4~~ `MEANINGFUL_TOOLS`/`VISIBLE_TOOLS` ora unica source of truth in `tools_base`. 521 unit test verdi, ruff pulito. **Rimane aperto A-3 / B-H4 / B-H5** (DB session lifecycle in `turns.py` — richiede infra + integration test di concorrenza).

---

## Backend — Finding

### HIGH (9)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-H1 | `app/ai/tools/dm_tools.py` (636 righe) | God file: tool registry + 14 implementazioni tool + dispatcher tutto nello stesso file. Viola regola 12. | `[x]` ✅ splittato 2026-06-08 |
| B-H2 | `app/core/agent.py` (493 righe) | God class: streaming + dice + NPC + tool dispatch + death check. Viola regola 12. | `[x]` ✅ era dead code, eliminato 2026-06-08 |
| B-H3 | `app/core/streaming.py` (294 righe) | Dead code post-migrazione LangGraph. Nessun caller vivo. Da eliminare. | `[x]` ✅ eliminato |
| B-H4 | `app/core/dm/dm_tools_executor.py:114` | Apre una nuova DB session per ogni NPC call dentro il turn → N sessioni extra per turn. **Fix architetturale**: ricevere il campaign object già fetchato via LangGraph state invece di riaprire sessione. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 3. | `[ ]` |
| B-H5 | `app/core/dm/dm_nodes.py:42` | Due sessioni concorrenti sullo stesso Campaign row → race condition su `turn_number`. **Fix architetturale**: `context_node` carica e chiude; solo `post_process_node` scrive. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 3. | `[ ]` |
| ~~B-H6~~ | ~~`app/api/websocket.py:47,251`~~ | ~~DB session tenuta aperta per tutta la durata di una turn.~~ | N/A — `websocket.py` era dead code, eliminato |
| B-H7 | `app/services/campaign_service.py:28` vs `app/memory/updater.py:35` | Chiave disposition diverge: `"disposition"` vs `"disposition_toward_player"` dal turn 1. Corruzione silenziosa dello world_state. | `[x]` ✅ fixato in `prompts/dm.py:191` |
| B-H8 | `app/config.py:8,12` | `jwt_secret` e `api_key_encryption_key` hanno default letterale `"change-me-to-a-random-256-bit-key"` senza startup validation. JWT forgery in produzione se l'operatore dimentica di impostare l'env var. **Fix**: `@model_validator(mode="after")` in `AppConfig` che lancia `ValueError` se il campo inizia con `"change-me"`. Vedi AGENTIC_ARCHITECTURE.md §"Security Hardening — Planned" punto 1. | `[x]` ✅ fixato (commit 1f95ac5, B-H8 + A-1) |
| ~~B-H9~~ | ~~`app/api/websocket.py:27-32`~~ | ~~JWT token passato come query parameter.~~ | N/A — `websocket.py` era dead code, eliminato |

---

### MED (12)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-M1 | `app/core/dm/dm_nodes.py` | `context_node` legge Campaign e costruisce il prompt nella stessa sessione DB che poi resta aperta fino al termine del nodo. Refactoring pattern apri→leggi→chiudi→LLM. | `[ ]` |
| B-M2 | `app/ai/router.py` | Score di importanza basato su keyword heuristics hardcoded. Nessun test di regressione sul routing. Aggiungere test unitari sul router. | `[x]` ✅ `tests/unit/test_router.py` presente |
| B-M3 | `app/memory/fact_extractor.py` | Estrazione fatti non limita le dimensioni della risposta LLM; se il modello produce output anomalo la serializzazione fallisce silenziosamente (`summarization_failed=True` non viene settato per i fact). | `[x]` ✅ fixato (commit 2884606) |
| B-M4 | `app/memory/compressor.py` | Retry con backoff `[1s, 5s, 30s]` — il backoff da 30s può tenere in attesa un background task più a lungo del ciclo successivo. Verificare se il dedup `batch_id` copre il caso di retry concorrenti. | `[x]` ✅ backoff max 30s→10s (commit 0791cdd) |
| B-M5 | `app/core/dm/dm_helpers.py` | Funzione `build_context()` supera 150 righe di logica concatenata senza suddivisione. Candidato a splitting in builder dedicati per segmento (history, recalled_memories, scene). | `[ ]` |
| B-M6 | `app/ai/prompts/dm.py` | `BASE_DM_PROMPT` e `DEATH_MODE_PROMPT` sono stringhe letterali nel modulo. Con l'aggiunta di nuove regole diventano difficili da versionare/testare. Valutare migrazione a template YAML. | `[ ]` |
| B-M7 | `app/core/dm/dm_nodes.py` | `post_process_node` esegue clock advance, death check e segment split in sequenza sincrona. Se uno step fallisce il turn viene persisted in stato inconsistente. Aggiungere transazione esplicita. | `[ ]` |
| B-M8 | `app/services/campaign_service.py` | `create_campaign` non valida che `template.world_state` contenga i campi obbligatori prima di copiarlo in `Campaign.world_state`. Un template malformato produce errori runtime al primo turn. | `[ ]` |
| B-M9 | `app/api/` (generale) | Nessun rate limiting sugli endpoint `/turns`. Un client può inondare il backend con LLM calls. Aggiungere rate limit per `user_id` (es. 10 req/min). | `[x]` ✅ `@limiter.limit` su `/turns` + `api/rate_limit.py` (commit 112b375) |
| B-M10 | `app/security/encryption.py` | AES-256 key derivata da `api_key_encryption_key` senza salt per-user. Se la chiave viene compromessa, tutti i record sono decifrabili in bulk. | `[ ]` |
| B-M11 | `app/core/dm/dm_nodes.py` | `route_after_tools` non ha test di integrazione end-to-end sul percorso `consecutive_empty_steps ≥ 2 → exit`. Solo test unitari sul routing. | `[ ]` |
| B-M12 | `app/core/agent.py` vs `app/core/dm/dm_graph.py` | `_meaningful_tools` duplicata in entrambi i file con valori divergenti. Fix: definire una volta sola in `app/ai/tools/dm_tools.py` e importare da entrambi i caller. Vedi AGENTIC_ARCHITECTURE.md §"Refactor Candidates — `_meaningful_tools` Planned Consolidation". | `[x]` ✅ fixato |

---

### LOW (9)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| B-L1 | `app/models/` | Mancano indici su `turns.campaign_id` e `memory_facts.campaign_id`. Su campagne lunghe (500+ turn) le query di compressione diventano lente. | `[x]` ✅ `index=True` su entrambi + indici compositi su `memory_facts` |
| B-L2 | `app/core/dm/dm_tools_executor.py` | Tool sort (request_dice → others → invoke_npc) implementato con chiave numerica hardcoded `{0,1,2}`. Fragile se si aggiungono nuovi tool con priorità. Usare enum. | `[ ]` |
| B-L3 | `app/ai/npc_director.py` | `last_interactions` troncato agli ultimi 3. Non configurabile. Aggiungere a `saga.config.yaml`. | `[ ]` |
| B-L4 | `app/api/campaigns.py` | Export JSON non include `memory_facts`. Un import su altra istanza perde tutta la memoria semantica. | `[x]` ✅ fixato (commit 4e042be) |
| B-L5 | `app/core/combat.py` | Initiative order non gestisce i pareggi (stesso valore d20 per due combatants). Comportamento non deterministico. | `[x]` ✅ tiebreak DEX→nome (commit 05f8949) |
| B-L6 | `app/ai/prompts/presets.py` | Preset `horror` e `grimdark` producono testi molto simili in playtest. Differenziare le linee guida stilistiche. | `[x]` ✅ differenziati (commit 145b954) |
| B-L7 | `templates/` | Schema JSON (`templates/schema.json`) non ha versioning. Un template creato con v1 schema sarà silently incompatible dopo modifiche. | `[x]` ✅ `schema_version` aggiunto (commit f68f9a0) |
| B-L8 | `app/config.py` | `AppConfig` non espone la versione dell'app. Difficile fare diagnostica su deployment con versioni diverse. | `[ ]` |
| B-L9 | `app/memory/updater.py` | `update_global_summary()` non ha limite di token sul global_summary in ingresso. Su campagne molto lunghe il prompt di summarization può eccedere il context window. | `[ ]` |

---

## Frontend — Finding

### HIGH (3)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-H1 | `shared/stores/auth-store.ts` | `accessToken` + `refreshToken` salvati in localStorage in chiaro. XSS su qualsiasi dipendenza compromessa svuota i token. Migrare a httpOnly cookies o memory-only store. | `[x]` ✅ memory-only + sessionStorage (commit 743f707) |
| F-H2 | `features/game/components/game-view.tsx:39` | Race condition: `submitScrollRef.current` mutato nel body del componente, può diventare `null` tra `onMutate` e la callback di `requestAnimationFrame`. | `[x]` ✅ scrollRef in `useSubmitAction` (commit 51748ef) |
| F-H3 | `features/character/components/character-sheet.tsx:181` | `archetype` non è in `CharacterData` interface. Utilizzato con cast `as unknown as Record<string, unknown>`. Type safety violata. | `[x]` ✅ `archetype` in `CharacterData` (commit 0fbaa08) |

---

### MED (7)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-M1 | `shared/stores/game-store.ts` | Store Zustand non ha reset esplicito al logout. Dati di campagna precedente possono persistere in memoria dopo il cambio utente. | `[x]` ✅ reset al logout in `auth-store` (commit d667176) |
| F-M2 | `features/narrative/components/narrative-stream.tsx` | SSE event listener non viene rimosso su unmount del componente. Memoria leak su navigazione veloce. | `[ ]` |
| F-M3 | `features/narrative/components/dice-roller.tsx` | `revealedCount` usato ma non dichiarato correttamente — causa errore ESLint residuo. | `[x]` ✅ fixato |
| F-M4 | `features/game/components/action-input.tsx` | Input non sanitizzato lato client prima dell'invio. Il backend sanitizza (`sanitize_player_input`) ma il frontend non dà feedback immediato su input troppo lunghi o caratteri non validi. | `[ ]` |
| F-M5 | `features/character/` | Nessun loading skeleton su `CharacterSheet` durante il fetch iniziale. Flash di contenuto vuoto visibile su connessioni lente. | `[ ]` |
| F-M6 | `shared/services/` | Client API non gestisce il caso di token scaduto durante una SSE stream in corso. L'utente vede uno stream interrotto senza messaggio di errore. | `[ ]` |
| F-M7 | `features/narrative/` | Nessun test unitario sui componenti narrativi (NarrativeStream, DiceRoller). Regressioni di rendering non rilevabili con il solo ESLint. | `[ ]` |

---

### LOW (10)

| # | File:Linea | Descrizione | Stato |
|---|-----------|-------------|-------|
| F-L1 | `features/game/components/game-view.tsx` | Mood CSS transitions non hanno `prefers-reduced-motion` media query. Accessibilità. | `[x]` ✅ `prefers-reduced-motion` in `App.tsx` + toggle in `settings-drawer` |
| F-L2 | `shared/stores/` | Nessun middleware di logging su Zustand in development mode. Difficile debuggare sequenze di azione. | `[ ]` |
| F-L3 | `features/character/components/character-sheet.tsx` | Valori ability score (STR, DEX, ...) hardcoded nel componente invece di essere derivati dall'interface `CharacterData`. | `[ ]` |
| F-L4 | `features/narrative/components/dice-roller.tsx` | Animazione click-to-reveal non disabilitabile da `saga.config.yaml`. Nessun modo per l'utente di disattivarla. | `[x]` ✅ toggle `diceAnimationEnabled` (commit d30a844) |
| F-L5 | `src/i18n/` | Stringhe di errore dell'API non sono localizzate — vengono mostrate in inglese anche in locale non-EN. | `[x]` ✅ chiavi i18n + locale IT (commit be2da5b, 4526701) |
| F-L6 | `shared/` | Nessun global error boundary React. Un'eccezione non gestita in un componente smonta l'intera app. | `[x]` ✅ ErrorBoundary in `App.tsx` (commit 6209252) |
| F-L7 | `features/` | Bundle size non monitorato. Nessun budget configurato in Vite. | `[x]` ✅ warning limit 500 kB in `vite.config.ts` (commit 484f4ab) |
| F-L8 | `features/narrative/` | NPC dialogue bubble non ha attributo `aria-label`. Screen reader non distingue narratore da NPC. | `[x]` ✅ `aria-label` presente in `narrative-stream.tsx` |
| F-L9 | `src/` | Nessun test E2E (Playwright/Cypress). Il golden path (crea campagna → azione → dado) non è coperto da automazione. | `[ ]` |
| F-L10 | `features/game/` | CombatTracker overlay non gestisce il caso di 0 combatants (combat_state.active=true ma initiative_order=[]). Possibile crash di rendering. | `[x]` ✅ edge case gestito (commit 1e0072e) |

---

## Test & Lint

### Risultati

| Suite | Risultato | Note |
|-------|-----------|------|
| Backend unit tests (516) | PASS | `pytest tests/unit --noconftest -q` |
| Backend integration tests | PASS | Richiedono infra Docker |
| Frontend tests | PASS | |
| Backend ruff | **0 errori** | `[x]` ✅ SIM117 nested `with` fixati |
| Frontend ESLint | **0 errori** | `[x]` ✅ `revealedCount` rimosso da `dice-roller.tsx` |

### Copertura gap

- `[ ]` Nessun test su `route_after_tools` con path `consecutive_empty_steps ≥ 2`
- `[ ]` Nessun test E2E sul golden path frontend
- `[x]` ✅ Test di regressione sul routing modello → `tests/unit/test_router.py`

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
- `[x]` ✅ auth-store migrato a memory-only + sessionStorage (commit 743f707)
- `[x]` ✅ N/A — JWT in query param riguardava `websocket.py` (dead code, eliminato); il path REST usa `Authorization: Bearer`
- `[x]` ✅ startup validation su `jwt_secret` in `config.py` (commit 1f95ac5)

**Effort stimato**: ~~1-2 giorni~~ → **completato**

---

### Gap 3 — DB session lifecycle (priorità: ALTA | effort: M)

**Gap**: Con LLM latency di 5-30s per turn, una sessione DB tenuta aperta attraverso le LLM call esaurisce il connection pool già con 5-10 utenti concorrenti e causa race condition su `turn_number`. Non è un problema oggi (self-hosted single user) ma blocca qualsiasi scaling futuro.

> **Diagnosi affinata 2026-06-08**: i nodi del grafo (`context_node`, `tools_node`) **già** aprono→leggono→chiudono la sessione *prima* della LLM call. Il locus reale rimasto è **`app/api/turns.py`**: la sessione di richiesta (`Depends(get_db)`) resta aperta attraverso tutto `dm_graph.ainvoke()` e `campaign.turn_number += 1` viene committato solo a fine turno (riga ~151), dopo tutte le LLM call → finestra di race su `turn_number` (B-H5).

**Azione**:
- `[ ]` `turns.py`: pattern apri→leggi→incrementa+commit `turn_number`→chiudi→LLM→riapri→scrivi risultati. Oppure increment atomico DB-level (`UPDATE ... SET turn_number = turn_number + 1 RETURNING`).
- `[ ]` Eliminare session extra in `dm_tools_executor.py:114` — passare il campaign object via state invece di riaprire sessione (B-H4)
- `[ ]` Aggiungere integration test che verifica la race condition su `turn_number` (due turn concorrenti) — **richiede `make test-infra-up`** (regole 1 e 11). Gli unit test `--noconftest` NON la coprono.

**Effort stimato**: 2-3 giorni

---

## Decisioni architetturali pendenti

Queste decisioni sono state concordate dall'audit team e documentate in `AGENTIC_ARCHITECTURE.md`. Richiedono implementazione nei prossimi sprint.

| # | Decisione | File coinvolti | Stato |
|---|-----------|---------------|-------|
| A-1 | **Config secrets startup validation**: `@model_validator` in `AppConfig` che fallisce a startup se `jwt_secret` o `api_key_encryption_key` iniziano con `"change-me"`. | `app/config.py` | `[x]` ✅ fixato (commit 1f95ac5) |
| ~~A-2~~ | ~~**JWT WS handshake**~~ | ~~`app/api/websocket.py`~~ | N/A — `websocket.py` era dead code, eliminato |
| A-3 | **DB session lifecycle**: due sessioni brevi in `submit_action` (claim atomico `UPDATE ... RETURNING turn_number` → close → graph senza sessione → re-fetch + write). Nessuna sessione attraverso le LLM call, niente race su `turn_number`. | `app/api/turns.py` | `[x]` ✅ fixato 2026-06-08 (ADR 0001), integration test concorrenza |
| A-4 | **`_meaningful_tools` unica source of truth**: spostare il set in `app/ai/tools/dm_tools.py` e importare da `agent.py` e `dm_graph.py`. | `app/ai/tools/dm_tools.py`, `app/core/agent.py`, `app/core/dm/dm_graph.py` | `[x]` ✅ `MEANINGFUL_TOOLS` in `tools_base`, `agent.py` eliminato |

---

## File da eliminare / refactorare

| File | Motivo | Priorità |
|------|--------|----------|
| ~~`app/core/streaming.py`~~ | Dead code post-LangGraph migration | ✅ eliminato 2026-04-22 |
| ~~`app/api/websocket.py`~~ | Dead code post-migrazione REST+SSE | ✅ eliminato 2026-04-22 |
| ~~`app/ai/tools/dm_tools.py`~~ | 636 righe, god file. Splittato in `tools_base` + `tools_combat` + `tools_inventory` + `tools_world` + `tools_special` + facade | ✅ fatto 2026-06-08 |
| ~~`app/core/agent.py`~~ | 493 righe, god class — in realtà dead code post-LangGraph (nessun importer) | ✅ eliminato 2026-06-08 |
| `app/ai/context.py` | `build_context()` (ex `dm_helpers.py`, ora 179 righe in `context.py`). Split in builder per segmento (history, recalled_memories, scene) — B-M5 | MEDIA — refactorare |
| ~~`turn_service.py` + `core/turn.py` + `stream_extractor.py`~~ | Pipeline di turno legacy pre-LangGraph (dead code). | ✅ eliminata 2026-06-08 (commit 58f70a9) |
| ~~`app/ai/parser.py`~~ | `parse_dm_response` eliminato con la pipeline legacy; `_strip_fences` spostato in `app/ai/sanitizer.py` come `strip_code_fences`. | ✅ rimosso 2026-06-08 |
| `app/ai/prompts/dm.py` | Prompt come stringhe letterali. Candidato a migrazione YAML per versionabilità | BASSA — valutare |

---

## Cosa manca da fare (snapshot 2026-06-08)

Stato dopo la sessione del 2026-06-08. **Tutto il backlog backend (HIGH/MEDIA/LOW) è chiuso o consapevolmente deferito.** Resta solo il frontend + research opzionale. Ordinato per priorità.

> **Chiuse il 2026-06-08**: A-3 (ADR 0001), B-M1, B-M5, B-M6, B-M7 (risolto da A-3), B-M8, B-M11, B-L2, B-L3, B-L8, B-L9, rimozione pipeline di turno legacy (`turn_service` + `core/turn.py` + `stream_extractor` + `parser.py`). **Deferito con motivazione**: B-M10 (premessa errata + feature non cablata).

### 🟢 Backend — priorità MEDIA (tutte chiuse o deferite)
- ~~**B-M5**~~ — ✅ fatto 2026-06-08: `build_context()` splittato in `_load_history`, `_load_batch_summaries`, `_recall_memories`; l'orchestratore ora è ~40 righe, file 199 righe.
- ~~**B-M6**~~ — ✅ fatto 2026-06-08: `BASE_DM_PROMPT` + `DEATH_MODE_PROMPTS` esternalizzati in `app/ai/prompts/dm.yaml`, caricati all'import. `dm.py` resta solo logica di assemblaggio XML. Output del prompt verificato byte-identico al precedente.
- ~~**B-M7**~~ — ✅ risolto da A-3 (2026-06-08): la diagnosi era pre-A-3. Oggi `post_process_node` è una funzione **pura** (nessun DB) che calcola world_state/death_event/segments in memoria; la persistenza è un singolo `commit()` atomico nella Session 2 di `turns.py`. Se un passo fallisce il graph fallisce e non viene scritto nulla (solo un gap di `turn_number`). Nessuna scrittura parziale possibile → niente da aggiungere.
- **B-M10** — ⏸️ **DEFERRED (premessa corretta 2026-06-08).** La diagnosi originale ("AES-256 senza salt per-user → compromissione chiave = decrypt in bulk") è **criptograficamente errata**: il salt HKDF è non-segreto per design (RFC 5869); la sicurezza dipende solo dall'IKM (la master key). Un salt per-utente NON protegge dal furto della master key — l'attaccante deriva comunque ogni chiave. Il salt dà solo *domain separation*, non la protezione dichiarata. L'unico fix reale per quella minaccia è **envelope encryption / KMS** (decisione di design a livello progetto). Inoltre la feature BYOAK è **non cablata**: `decrypt_api_key` non è chiamato da nessuna parte (le chiavi si scrivono cifrate ma non si rileggono mai). Qualunque modifica crypto ora sarebbe lavoro speculativo su un path non testabile end-to-end. **Da rivedere quando BYOAK viene effettivamente cablato**, valutando envelope/KMS. `encrypt/decrypt_api_key` restano come scaffolding.
- ~~**B-M11**~~ — ✅ fatto 2026-06-08: test su `route_after_tools` per il cap `consecutive_empty_steps` (unit deterministico in `test_dm_routing.py`; il path è una funzione pura, un integration test richiederebbe di forzare loop a vuoto con LLM mockato — coperto meglio a livello unit).
- ~~**B-M1**~~ — ✅ fatto 2026-06-08: l'embedding di recall è precalcolato in `context_node` PRIMA di aprire la sessione e passato a `build_context → search_similar_facts` (param `query_embedding`). Nessuna chiamata embedding API in-sessione.

### 🟡 Frontend — priorità MEDIA
- **F-M2** — SSE event listener non rimosso su unmount di `narrative-stream.tsx` (verificato: nessun cleanup) → memory leak.
- **F-M4** — input non sanitizzato lato client (nessun feedback immediato su input troppo lunghi).
- **F-M5** — nessun loading skeleton su `CharacterSheet`.
- **F-M6** — token scaduto durante SSE stream non gestito.
- **F-M7** — nessun test unitario sui componenti narrativi (`NarrativeStream`, `DiceRoller`).

### 🟢 Frontend — priorità BASSA
- **F-L2** — nessun middleware di logging Zustand in dev.
- **F-L3** — ability score hardcoded nel componente invece che derivati da `CharacterData`.
- **F-L9** — nessun test E2E (Playwright/Cypress) sul golden path.

### 🔬 SOTA Research (opzionale, da valutare)
- Migrazione `memory_facts` da `vector` (float32) a `halfvec` (float16).
- BM25 hybrid search (`gameplay.pgvector_hybrid`) per anchoring su nomi propri.
- Documentare come `global_summary` + `search_similar_facts` realizzano già il dual-memory pattern.

> **Prossimo consigliato**: B-M5 (split `build_context`) + B-M1 insieme, oppure B-M11 (integration test del routing) come task a basso rischio. B-M10 (salt per-user) merita una sessione dedicata di security.
