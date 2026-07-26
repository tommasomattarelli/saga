# TODO — SAGA

## NOW / prossimi
<!-- Lavoro attivo near-term: /catchup legge questa sezione, /wrap-up la aggiorna. Il resto del file e' backlog curato. -->
[x] **ADR 0009 npc enrichment → IMPLEMENTATO** (S1-S3 mergiati su `adr/0009-npc-enrichment`, 2026-07-11): identità UUID + rung v7, modello engine tipizzato + `npc_fields` world-defined + resolver F2, tools `update_npc`/`kill_npc`/`remove_npc`/`restore_npc` + writer morte HP≤0, surfaces (scene/npc prompt) + editor npc_fields + prune-on-removal G5 (incl. fix bug assi 0005) + FE. Suite verde: 627 unit BE + 132 FE, ruff ok. ADR flippato ad **Accepted** al merge su main (2026-07-26).
[x] **ADR 0009 — PR su main**: PR #49 mergiata il 2026-07-26. Con lei sono arrivate su main anche 0005, 0008 e 0013 (branch concatenati) — `worlds/` c'è, `templates/` non c'è più.
[x] **release `v0.2.0-beta.1`**: tagliata il 2026-07-26 con `scripts/release.sh` (pre-release, asset installer allegati). Pre-release apposta: il playtest gira CONTRO questo tag, così ogni issue ha una versione di riferimento; `0.2.0` finale quando le issue del playtest sono chiuse.
[~] **playtest su `v0.2.0-beta.1` → GitHub issue**: ogni bug trovato diventa una issue (titolo `type(scope): subject` come i commit, label `type:`/`prio:`/`area:`, form YAML in `.github/ISSUE_TEMPLATE/`), NON un fix silenzioso sul branch. Il commit di fix cita la issue, `release.sh` la tagga `(#NN)` nelle note. Primo giro fatto → **#50** (P0, `choices[0]` su payload d'errore OpenRouter), **#51** (dialogo NPC ignora la lingua), **#52** (DM scrive i dialoghi invece di chiamare `invoke_npc`), **#53** (DM parafrasa l'output di `invoke_npc`), **#54** (typewriter troppo lento e non configurabile). ATTENZIONE metodologica: quel giro girava su un modello free-tier — #52/#53 vanno riverificate su un modello competente PRIMA di riscrivere i prompt.
[ ] **ADR 0017 (dialoghi NPC: tool a metà turno vs pre-pass parallelo) — WIP, da sviluppare**: stub scritto (`docs/adr/0017-npc-dialogue-turn-architecture.md`), nessuna fork chiusa, nessuna intervista fatta. Nato dal playtest (#52/#53): il tool a metà turno serializza DM e NPC (3 battute ≈ 7 round-trip in serie), la DM lo salta o ne parafrasa l'output, e il taglio spezza il ritmo della scena. Opzione B (pre-pass parallelo a inizio turno, `invoke_npcs_parallel` esiste già) porta la stessa scena a 2 round-trip. Da difendere: le DECISIONI dell'NPC restano sue, non della DM — l'opzione "NPC dà le intenzioni, la DM scrive le parole" va respinta. Sei fork aperte in §4, incl. il rapporto con la acting call di 0014 (stessa forma) e come si rende esigibile "riporta le battute alla lettera" meglio della regola 42 di oggi. **Prossimo passo: intervista di design con l'owner.**
[ ] **ADR 0003 — implementazione S1-S4** (design pass 2026-07-12: ADR espanso a "risoluzione unificata", tutte le fork chiuse dall'owner): S1 resolver 6 livelli + bande fisse + clamp / S2 combat senza modalità (tool `attack` simmetrico, statblock sui record 0009, barre vita di scena) / S3 difficoltà campagna (via `DeathMode`) / S4 surfaces FE+editor. Partire DOPO la PR 0009 su main. Piano e contratti in ADR §7.
[ ] **ADR 0005 — playtest veloce** (PR su main: fatta, arrivata col merge #49): validare a mano la qualità dei delta dal modello budget (rischio #1 dell'ADR, nessun test automatico possibile) — Lyra guardinga (trust −20 authored), minaccia a sconosciuto (×3 visibile in scena), favore+bugia (assi giusti si muovono), editor con asse custom. Se delta scarsi → fix = prompt wording (vedi riga prompt-tuning in backlog).
[ ] **ADR 0008 — validazione manuale** (PR su main: fatta, arrivata col merge #49): playtest a mano del ciclo (creazione campagna da world, move_to/viaggio/encounter, mappa, editor: crea/modifica/salva/export/import) in una chat a contesto pulito; i bug emersi diventano GitHub issue. NB: le campagne del DB dev vecchie non hanno baseline (J2: wipe accettato, pre-1.0). Nota tecnica: `npm ci` locale richiede `--legacy-peer-deps` (conflitto peer eslint@10 pre-esistente nel lockfile) — da sanare con le dependency updates.
[x] **UI redesign → ADR 0013** (Accepted, `docs/adr/0013-ui-visual-redesign.md`): dark moderno pulito, Voyage-informed identità nostra, re-skin su architettura tokenizzata. Sprint 1 (play screen, pattern-setter): font Newsreader+Instrument Sans, accento verdigris `#8fb8ac`, atmosfera stripped, dado tier-arc. Sprint 2 (propagazione): auth card, campaign grid, wizard flat, character modal a rail, journal/settings/combat re-skinnati, ornamenti morti rimossi. Branch `redesign/ui-dark-a` (merge di sprint-1 + sprint-2), owner sign-off dato, su main col merge #49. PARCHEGGIATO (ADR suoi): "player input come ispirazione" (gameplay), bug `getTurns` empty-render.
[ ] **UI redesign — polish pass** (post ADR 0013 Sprint 1+2, minor): fix visivi minori rimasti sulla play screen e altrove, segnalati dall'owner ma non bloccanti ("ora è giocabile, prima no"). Da fare insieme al prossimo giro sul frontend, dopo il lavoro backend/test in corso.
[x] **fix(dice) — ability scores INERTI in ogni check (mis-keying, bug LIVE nel playtest).** FATTO (commit 80fe1ec): `_STAT_FULL_NAMES` abbrev→nome pieno in `_handle_dice` + test sul formato chiavi reale FE, 394 unit verdi. Prompt-block e normalizzazione unica restano a `0010-F1`. Decoupled da ADR 0010 (vedi `0010-H1`). PROBLEMA: il FE salva `character_data.abilities` con **nomi pieni lowercase** (`{strength:16, dexterity:12, …}`, `frontend/src/features/campaign/data/class-presets.ts`); ma il risolutore del dado `core/dm/dm_tools_executor.py:217` legge `abilities.get(stat, abilities.get(stat.lower(), 10))` con `stat` = `"DEX"`/`"STR"`/… → cerca `"DEX"` poi `"dex"`, **non matcha `"dexterity"`** → fallback a 10 → `modifier = (10-10)//2 = 0` **SEMPRE**. Quindi **ogni `request_dice` ignora gli ability score** (tira a +0). Per contrasto: `core/combat/combat_graph.py:35` legge `abilities.get("DEX", abilities.get("dexterity", 10))` → matcha (iniziativa combat ok); `ai/prompts/dm.py:71` legge flat `char_data["dex"]` → mai popolato → il blocco `<abilities>` non compare nel prompt. **Tre convenzioni divergenti.** FIX MINIMO: allineare il lettore del dado (e il blocco prompt) alle chiavi reali del FE (nomi pieni lowercase) o normalizzare a un punto unico. NB: throwaway quando `0010-F1` ritipizza `character_data` (Pydantic), ma è ~1 riga e sana un bug che falsa OGNI tiro. Aggiungere un test: `request_dice` su DEX alta → `modifier > 0`.
[x] installer: validato il ramo auto-install su **Linux vergine** (podman Ubuntu 24.04, utente non-root, `SAGA_FROM_LOCAL=1`): uv + node portable + pg16/pgvector + initdb + .env + uv sync + vite build → OK end-to-end (exit 0). Trovato e FIXATO un bug: eseguito come root moriva su `initdb: cannot be run as root` DOPO aver già apt-installato Postgres → aggiunto guard no-root (commit ba5b23d). PROBLEMA PORTABILITÀ emerso: vedi sezione follow-up sotto (Debian/Fedora rotti).
[ ] installer: validare il ramo "auto-installa git/node/uv se mancanti" su VM/PC Windows VERGINE (NON testabile da Linux: il bundle PG sono exe win64, pwsh-su-Linux solo parsa; serve VM Windows o Windows Sandbox)
[x] companion → **ADR 0014 (npc-promotion), design pass 2026-07-12**: scope generalizzato a "promozione NPC" (companion + elite/boss — stessa scheda, stesso cervello dedicato, segno opposto; boss autorati, o promossi dal Director 0006). Tutte le fork chiuse: party list + record 0009 per la vita, sheet snella senza XP, lealtà = assi 0005, pipeline promozione det+refine background, call autonoma sempre-se-presenti (spazio azione pieno incl. tradimento), equip-layer che fixa 0010-I8, transfer_item + auto-equip strictly-better, rung v9. Implementazione GATED dietro 0010 S1-S4 + 0012 S1 — piano S1-S4 e TODO nell'ADR §7/§3, NON in ## NOW.
[ ] passare in rassegna le funzioni marcate #TODO nel codice (capire se servono)
[ ] code quality: barrel export puliti — `index.ts` per feature/modulo FE che ri-esportano l'API pubblica (import più puliti tra moduli). Per il BE valutare `__init__.py` con re-export MA attenzione ai cicli d'import (Python preferisce path espliciti — barrel meno idiomatico che in TS; farlo solo dove riduce davvero il rumore).
[ ] verificare/riprodurre i bug Gemini trovati testando (vedi sezione "provider AI — bug" sotto): `thought_signature` multi-turno (400 INVALID_ARGUMENT) + embedding hardcoded su OpenAI. Riprodurre e fixare.
[x] mypy backend: `[tool.mypy]` + verde (82 file) + gateato su pre-push E in CI (branch `fix/mypy`, PR aperta) — plugin pydantic, override import `pgvector`, stub types; boundary SDK e `computed_field` con `# type: ignore[code]` mirati; forward-ref ORM via `TYPE_CHECKING` (giu 2026)
[x] vulture in CI (gate dead-code BE, speculare a knip FE): FATTO (commit a94f84e, `ci.yml:28` — `uv run vulture app --min-confidence 80`, verde, 0 findings). È euristico → se in futuro un falso positivo blocca una PR (route FastAPI, fixture pytest, `relationship` SQLAlchemy, attributi dinamici) NON abbassare la soglia: aggiungere un file whitelist vulture (equivalente di `knip.json`). Validare alla prima PR che tocca codice nuovo.

## roadmap / release
[x] pipeline GitHub (CI) — fatto (`.github/workflows/ci.yml`: lint, unit, integration+playtest con service container pgvector, frontend, docker build-smoke, parse-check installer; nessuna API key, tutto mockato). CD/release ancora da fare (sarà `release.yml`)

## frontend
[x] refactor + analisi del frontend (come fatto per il backend) — fatto giu 2026 (branch refactor/frontend): god-file split, dead code 0, coverage ~95%, E2E mockato, guida in scratch/frontend/

## infra / distribuzione
[ ] debug con docker
[ ] nginx: serve davvero?
[~] installer casual NATIVO (no-Docker) — fatto (vedi ADR 0000, dir `install/`). Scelta rivista vs la riga originale: NON wrappa docker-compose (l'utente tecnico fa `docker compose up --build`); il casual provisiona un bundle Postgres+pgvector portatile (Release asset), uv user-scope + Node portatile, NO admin, secret auto-generati nel `.env` (std 16). Niente dialog API-key: le key si mettono dalla UI (BYOAK). Usa `.env.example` (non `.env.template`). Windows .bat+.ps1 + launcher accoppiato; controparti Linux/Mac .sh (PG da package manager). Backend invariato (FastAPI serve la SPA, mount guardato). FATTO: bundle pubblicato come Release (`bundle-pg16-v1`, PG 16.14 + pgvector 0.8.2) + URL reale cablato in `install/windows/install_saga.ps1` e `installer-smoke.yml`. [spunto: NEQ installer .bat, dnd-llm-game launcher]

# ---- installer/CI: follow-up rimasti (giu 2026) ----
[x] smoke E2E installer VERDE su Windows + Linux (`installer-smoke.yml`): bundle scaricato (gh), PG+pgvector provisionati, DB creato, backend su, SPA servita. Trigger TEMP gia' rimossi.
[~] installer PORTABILITÀ pacchetti Postgres (VALIDATO via podman, giu 2026). Debian/Ubuntu **FIXATO** (commit c29168f): `install_saga.sh` aggiunge il repo **PGDG** (`apt.postgresql.org`, keyring `signed-by`, codename da `/etc/os-release`) → pg16 16.14 + pgvector 0.8.4 uniformi su tutte le release. Validato e2e su Debian 13 trixie (default pg17) + probe bookworm/noble. La CI `installer-smoke.yml` ora esercita questa logica (rimosso il PGDG manuale). RESTA: **Fedora** non supportato (nessun ramo dnf; l'installer conosce solo apt/brew) — eppure pg16 + pgvector 0.6.2 sono in dnf → aggiungere un ramo dnf o documentare unsupported.
[ ] installer macOS: aggiunto job `macos-smoke` a `installer-smoke.yml` (runner `macos-latest`, path brew `postgresql@16` + `pgvector`). DA VALIDARE al primo dispatch/schedule: sospetto principale se rosso = `brew install pgvector` che builda l'estensione contro il postgres di default di brew invece di `postgresql@16` (mismatch di linking). Non testabile in locale (niente Mac / no VM macOS) → solo via runner CI.
[ ] icona custom `saga.ico` per la shortcut desktop (polish; la shortcut funziona anche senza)
[ ] (terziario) installer: porta PG dinamica. Oggi `54320` e' hardcoded in `start_saga.ps1`/`install_saga.ps1` senza check ne' fallback; se un processo TERZO la occupa, `pg_ctl start` fallisce il bind ma e' un exe nativo -> non fa scattare `$ErrorActionPreference=Stop` -> lo script prosegue su uvicorn che poi non trova il DB (fallimento muto). FIX: sondare una porta libera all'avvio, scriverla nel `.env`, passarla a pg_ctl; messaggio chiaro se il bind fallisce. Loopback-only (no esposizione di rete) gia' ok. Raro (un orfano stessa-datadir si auto-cura via postmaster.pid) -> farlo alla prima issue utente o quando ci sono 5 min per testare.
[ ] dependency updates (Dependabot, ora 1 PR raggruppata per ecosystem): VALIDARE le PR prima del merge — la CI sulla PR e' la guardia, ma alcuni controlli mockano (vedi sotto). Major che rompono = NON auto-merge, sono migrazioni: (a) **frontend** React 19 + `react-i18next` v17 (le PR #17/18/19 chiuse 2026-06-23: i18next 15→17 rompe tutte e 32 le suite di test) → migrazione FE dedicata; (b) **backend** `google-genai` 1.68→2.9 (major SDK AI) → la CI mocka le chiamate LLM, verde NON garantisce il runtime → smoke test contro l'API Gemini reale prima di fidarsi. Postura: patch/minor+security subito, major schedulati; se troppo rumore aggiungere `ignore` major-version nel dependabot.yml.
[ ] AL GO-PUBLIC (security): (1) abilitare secret scanning + push protection — `gh api --method PATCH repos/<owner>/saga -f security_and_analysis...` (oggi 422 "not available", e' private); (2) CodeQL + dependency-review si auto-attivano (gia' in `.github/workflows/`, guardati su `github.event.repository.visibility == 'public'`); (3) valutare se aggiungere i loro check al ruleset `protect-main` come required (dopo il primo run verde). Dependabot e' gia' attivo (funziona anche da private).
[ ] CD: `release.yml` tag-triggered (`on: push: tags v*`) — DA FARE INSIEME a Docker→GHCR, non prima. Oggi `release.sh` pubblica gia' la Release + allega i due installer come asset (giu 2026); un'Action solo per quello sarebbe over-engineering. L'Action si ripaga quando la CI deve BUILDARE artefatti che non vuoi sul laptop. PREREQUISITO Docker: i Dockerfile attuali sono DEV-image (frontend = `npm run dev`/vite dev server; backend single-stage + bind-mount+`--reload` nel compose) → NON pubblicabili. Servono prima Dockerfile di PRODUZIONE (multi-stage, frontend buildato statico, backend senza reload) e decidere se **una sola** immagine (FastAPI serve la SPA, vedi ADR 0000) o due → push su GHCR `ghcr.io/.../saga-*:vX.Y.Z`+`:latest` (pubblico = storage gratis/illimitato). Modello scelto: tag-triggered (la CI non scrive mai su `main`, niente bypass/segreti). Quando si fa → ADR "CD artefatti".

[ ] verificare che i push al frontend in dm_tools_executor siano fail-silent (un FE down non deve bloccare il loop DM) [spunto: open-tabletop-gm]

## world-building / template
[ ] template + world-building fatti bene (tanti yaml indentati per profondita'/dettaglio del mondo). attenzione a non saturare il contesto -> analisi dettagliata

# ============================================================
# da analisi multi-repo (giu 2026): NEQ, ai_rpg, dnd-llm-game,
# aidm, llm-rpg, open-tabletop-gm, Friends&Fables.
# keeper indipendenti dai fork.
# ============================================================

## router / costi
[x] score_importance → **ADR 0016 (importance-scoring), design pass 2026-07-13**: studio fatto, tutte le fork chiuse — scoperto che oggi il routing è di fatto inerte per il gioco in italiano (keyword English-only → sempre 5 → sempre medium) e il bump combat legge una chiave che nessuno scrive (dead code). Design: score a 3 layer ZERO chiamate nuove — segnali stato engine (combat window 0014, boss presenti, hp, tensione 0006) + ancore embedding (batch nella chiamata recall esistente, cattura perifrasi cross-lingua, ±2) + stakes-rating dal summarizer post-turno (lag 1 turno) — pesi/soglie config, breakdown loggato per turno per il tuning empirico. Pre-classifier LLM respinto (latenza+costo BYOAK). Sprint unico, nessun gate (ADR §7).

## provider AI — bug trovati testando OpenRouter/Gemini Flash (lug 2026)
[ ] **embedding hardcoded su OpenAI, ignora il provider configurato.** `app/ai/embeddings.py:18` chiama sempre `api.openai.com/v1/embeddings` con `settings.openai_api_key`, a prescindere da `SAGA_GLOBAL_PROVIDER`. Se il provider globale è Google/OpenRouter/altro e non è settata anche `OPENAI_API_KEY`, ogni embedding fallisce con 401 (silenzioso: la funzione ritorna `None`, non rompe il turno ma il recall semantico pgvector non funziona mai). Serve wiring dell'embedding sul provider configurato (Google ha endpoint embedding proprio; OpenRouter no — serve capire fallback).
[ ] **Gemini 2.5/3.x: `thought_signature` mancante rompe il tool-calling multi-turno (400 INVALID_ARGUMENT).** Riprodotto con `gemini-3.5-flash` su un secondo tool-call nello stesso turno (`set_scene_mood` dopo `invoke_npc`). Root cause in `app/ai/providers/google.py`: `generate_with_tools` (righe 175-218) estrae da `part.function_call` solo `name`+`args` nel `ToolCall`, scartando l'eventuale `thought_signature` che Gemini richiede echeggiato nel turno successivo; `_to_contents` (righe 39-103) ricostruisce lo storico assistant/tool_calls senza mai riscriverlo nel `function_call` part. Fix: propagare `thought_signature` da `ToolCall`/schema fino alla ricostruzione dei messages. Vedi https://ai.google.dev/gemini-api/docs/thought-signatures.

## memoria
[x] recall pgvector query composta → ASSORBITA in ADR 0002 (design pass 2026-07-13): query = azione + entità di scena + K summary, un solo embedding, cap lunghezza (R2)
[ ] summarization per "scena" (cambio location/combat) invece che a finestra fissa di turni; conservare i quotes[] dei dialoghi chiave [spunto: ai_rpg]
[ ] idempotency guard sui background task (turns.py): campo chronicled_at su Turn per non rieseguire fact-extraction/compression [spunto: aidm]
[ ] continuity_checklist: flag booleani machine-readable per NPC/location ("vivo: true", "sa_di_X: false") accanto alla prosa, per coerenza multi-sessione [spunto: aidm]

## combat
[ ] timeout esplicito per singola tool-call LLM in combat (oltre al recursion cap), con fallback "il turno prosegue" [spunto: llm-rpg] — NB ridimensionato da ADR 0003 B1: il combat non fa più chiamate LLM per le azioni nemiche; resta il timeout generico per tool-call
[x] formalizzare il circumstance modifier nel roll tool → SUPERSEDED da ADR 0003 A5 (advantage/disadvantage binario con reason; il ±N numerico è respinto esplicitamente)
[x] effetti temporizzati: tick per round → SPOSTATO a ADR 0012 (ADR 0003 C2: niente più round; sistema durate unico status+cooldown quando si fa 0012)

## prosa / output
[ ] **prompt tuning pass dedicato (DOPO ADR 0009)**: sessione/ADR per rivedere e calibrare i prompt DM/NPC su playtest reali — include la qualità di `axis_changes` (ADR 0005) e i prompt che 0009 aggiungerà
[x] prompt-as-yaml → ASSORBITA in ADR 0004 (design pass 2026-07-13): veicolo dello sprint S2 (npc.py → yaml, cartella unica, obblighi tool generati)
[ ] LangSmith: verificare su tracce reali cosa entra davvero nel contesto per ogni nodo del grafo (prompt effettivi, non presunti) — base empirica per il tuning pass
[ ] slop-buster: lista parole/n-gram in saga.config.yaml + check post-prosa nel DM (qualita' prosa = pillar) [spunto: ai_rpg]
[ ] popolare suggested_actions (oggi None) con blocklist di placeholder per filtrare scelte malformate [spunto: dnd-llm-game]

## world / player agency
[x] commercio → **ADR 0015 (commerce), design pass 2026-07-13**: tutte le fork chiuse — value authored|range|derivato dalle classi con draw per-transazione cachato/giorno, invariante hard anti-arbitraggio, tutti commerciano + shop_classes world-defined (pattern npc_classes: stock/restock lazy/portafoglio finito/haggle_difficulty), valuta 1-3 tagli schema-capped (senza valuta = niente commercio, baratto TODO), transazione deterministica all'accettazione player (rail + offerte NPC prezzate engine, DM mai sui soldi), trade disposition 0-100 da pesi world-defined + soglie config, haggle = check 0003 via pointer rulebook (mai nome hardcoded) 1×/giorno con fail critico che irrita, servizi come item virtuali (enum chiuso rest/heal/passaggi). Implementazione GATED dietro 0010 S4 — piano S1-S3 nell'ADR §7, NON in ## NOW.
[ ] override strutturati player->DM: NPC_PROTECTION / CONTENT_CONSTRAINT / TONE / NARRATIVE_DEMAND con scope (campaign/session/arc), persistiti e iniettati nel prompt ogni turno [spunto: aidm]
[x] DM hidden notes / "mystery box" → ASSORBITA in ADR 0006 (design pass 2026-07-12): `narrative.dm_notes` Director-owned, resa al DM nel blocco advisory (D1)
[x] narrative arc: blocco narrative_arc → ASSORBITA in ADR 0006 (design pass 2026-07-12): `narrative.arc` advisory, mai plot vincolante (A3 #12, D1)
[ ] WorldBuilder accept-not-reject: il DM accetta le asserzioni del player come canon salvo ambiguita' fisica (player co-autore), niente REJECT [spunto: aidm]
[x] faction_moves: log esplicito → ASSORBITA in ADR 0006 (design pass 2026-07-12): `factions.{}.moves` scritto dal Director (A3 #7); verificato: il living-world oggi NON lo fa (factions mai scritte)
[x] living world: trigger su transizione oraria → ASSORBITA in ADR 0006 (design pass 2026-07-12): trigger ibrido N turni OR M minuti di clock (B1)
[ ] meta-channel: intent /meta che NON consuma un turno di gioco (feedback al DM fuori dalla narrativa) [spunto: aidm]

## homebrew / custom
[ ] upload PDF lore homebrew -> chunking + embedding su pgvector, associato a campagna, recuperato nel recall (riusa pgvector, non LanceDB) [spunto: dnd-llm-game]
[ ] formalizzare lo schema "pacchetto campagna" export/import (aree/NPC/mostri/plot): estende export.py + pillar data-sovereignty [spunto: NEQ moduli drop-in]

## concorrenza (minore)
[ ] advisory lock per campagna sul turn handler: turn_number e' gia' atomico ma world_state ha una race last-writer-wins su turni concorrenti (stretta: e' single-user REST) [spunto: aidm]

# ============================================================
# FORK DECISI (giu 2026) -> vedi docs/adr/. follow-up implementativi.
# ============================================================

## fork A -> ADR 0002 (relationship graph + recall enrichment)
[x] design pass 2026-07-13: entrambe le righe decise e superate dall'ADR espanso — score composito SQL (decay+boost, campi nuovi, seam reranker spento), query composta, grafo edge tipizzati in `world_state.relations` (fazione→player unifica disposition/reputation/tiers morti, factions rekeyed by slug, 4 writer incl. estensione guardata del fact extractor — la verb-table originale è respinta). Piano S1-S3 nell'ADR §7 — NESSUN gate esterno: primo implementabile della coda ADR.

## fork B -> ADR 0003 (risoluzione a soglie fisse + danno server-side)
[x] design pass 2026-07-12: le tre righe originali (bande fisse, tier->danno server-side, config-first) sono decise e superate dall'ADR espanso (risoluzione unificata per TUTTI i check, non solo combat); piano S1-S4 nell'ADR §7, tracking implementazione in ## NOW

## fork C -> ADR 0004 (dm_core / game_system + tono per campagna)
[x] design pass 2026-07-13: le tre righe decise e superate dall'ADR espanso — il "game_system caricabile" è superseded nella sostanza (sistema = engine 0003 + rulebook 0010, dati); 0004 = factoring prompt (dm_core yaml + obblighi GENERATI dai tool group + flavor), tono = personas esistenti + writing_style_notes (knob numerici RESPINTI: lethality→0003, magic→world, darkness→persona; system_prompt_addendum ridondante con persona_xml), config_override JSONB WHITELISTATO (precedenza campaign > yaml > default, merge puro, re-validazione all'import). Piano: S1 tono+override SENZA gate / S2 factoring DOPO l'implementazione 0003 (ADR §7).

## fork D -> ADR 0005 (psicologia NPC multi-asse)
[x] ridisegnare npc_psychology JSONB come multi-asse → design fissato in ADR 0005 (S0 2026-07-07); ciclo implementativo in `## NOW`
[x] fazioni: `disposition` fazione→player → RISOLTA da ADR 0002 (design pass 2026-07-13, G1/G6): edge fazione→player nel graph (stance -100..100, bande dai reputation_tiers authored); i tre frammenti morti (overlay disposition / char_data.reputation / tiers) unificati e ritirati. Implementazione con 0002 S2.

# ============================================================
# SECONDARI / deferred (giu 2026) — promossi dal long-tail multi-repo.
# bassa priorita'; alcuni legati a versioni future.
# ============================================================

## secondari — combat / gioco
[ ] toggle prompt combat full/compresso, CONFIGURABILE in saga.config.yaml [NEQ]
[ ] op_dominant: reframe narrativo su tier-gap forte (combattente molto superiore) [aidm]
[ ] focus-budget: limite caratteri dell'azione come stat di gioco [llm-rpg]
[ ] enemy come agente LLM autonomo / pipeline simmetrica hero-enemy [llm-rpg]

## secondari — memoria / world
[ ] lorebook "constant entries" sempre iniettate (regole mondo/magia) [ai_rpg]
[x] foreshadowing-seeds con lifecycle → ASSORBITA in ADR 0006 (design pass 2026-07-12): `narrative.seeds` planted→advanced→resolved/expired + payoff meccanico via scheduled events (A3 #9-10)
[ ] tool di ricerca keyword/fulltext sul log di campagna [otgm]

## secondari — world-gen / template (alimentano la riga "template fatti bene" sopra)
[ ] Three Truths per elemento: Obvious / Discoverable / Secret [otgm]
[ ] Threat-Arc table a 5 stadi (Now -> No Return) con trigger e reversal [otgm]
[ ] faction inbound-relationships generator (come le fazioni esistenti vedono la nuova) [ai_rpg]
[ ] word-steering per nemici tematici (liste parole) [llm-rpg]
[ ] GM-player-calibration notes (stile del player, persistente, letto a inizio sessione) [otgm]
# nota: calendario fantasy (mesi/stagioni/festivita') = gia' coperto dalla riga "template fatti bene"

## secondari — infra / dev
[ ] narrative-probe v2 per calibrare quali modelli nei tier del router [otgm]
[ ] LLM-fixture-file per test end-to-end deterministici [ai_rpg]
[ ] subprocess isolation per generazione modulo AI lunga [NEQ]
[ ] cached_property per il config loader [llm-rpg]
[ ] mod-system con scope isolato + route namespaced -- SCOPE DEFERRED, molto in fondo (ADR quando si progetta l'estensibilita') [ai_rpg]

## secondari — v3
[ ] TLS self-signed + distribuzione cert per LAN [otgm]
[ ] Hero globali riusabili tra campagne (Hero vs Character) [dnd-llm-game]

## v2.5 — AI Director (vedi ADR 0006)
[x] design pass 2026-07-12: le quattro righe originali sono decise e superate dall'ADR espanso (taxonomy 14 capacità con bool per capacità, guard node-scoped all'apply, tabella `director_changes` + apply exactly-once, trigger ibrido turni/clock, rumors grounded + `tell_rumor`, creazione NPC/fazioni con guardrail, rung v8). Piano S1-S4 e Decided/Open index nell'ADR §7/§3 — implementazione v2.5, NON in `## NOW` finché l'owner non la schedula.

# ============================================================
# ADR 0007-0011 (giu 2026) -> follow-up. 0007-0010 = analisi Voyage; 0011 = refactor FE.
# vedi docs/adr/. 0007-0010 NON ancora Accepted (Proposed/WIP).
# vanno prima accettati.
# ============================================================

## ADR 0007 (Proposed) — direzioni adottate dalla Voyage
[x] state-audit pass → PROGETTATO (design pass 2026-07-13, ADR §1): perimetro inventario/quest/location + npc remove|restore reversibili + tempo cappato (MAI kill/engine-authoritative), apply via queue 0006 generalizzata (colonna source, guard per-source), guard anti-allucinazione (solo-aggiunta, precondizioni drop+log, location = set posizione MAI travel engine), audited_at transazionale, AICallType.STATE_AUDIT on-by-default. Sprint unico, gate soft = tabella queue condivisa (ADR §S1).
[ ] massima configurabilita' della memoria + modelli per-sottosistema [ADR 0007 §2 — direzione; primi frutti: whitelist 0004, famiglia recall.* in 0002 S1]

## ADR 0008 (Proposed — design fissato, TODO aperti prima di Accepted) — world model multi-layer YAML + grafo spaziale deterministico
[ ] chiudere i TODO di design: enum `kind` (A-i), transform/scale globale per livello (A-ii), sistema unita'/coordinate (B-i), vocabolario `terrain` + range `elevation_m` (B-ii), schema blocco `scenario` + seed della campagna (C-i)
[ ] poi: split in sprint di implementazione

## ADR 0009 (Proposed — S0 design pass 2026-07-07) — NPC enrichment (identità UUID, lifecycle/condition, traits world-defined, update_npc)
[x] analisi dedicata → S0 completato 2026-07-07/08: fork chiusi da interview + advisor Opus (identità UUID mirror 0008, record ibrido typed+traits da taxonomy `npc_fields`, writer morte engine HP≤0 + kill/remove/restore engine-checked, update_npc con partizione esaustiva + fuzzy guard); ciclo implementativo S1-S3 in `## NOW`

## ADR 0010 (WIP, nulla deciso) — customizzazione PG (skill progression + abilities configurabili)
[ ] analisi dedicata: decidere le meccaniche PRIMA di implementare (oggi e' solo direzione)

## ADR 0011 (Accepted) — E2E frontend mockato
[ ] variante E2E con backend reale + Docker (make test-infra-up + DB seedato + action->dado); oggi le /api sono mockate in-browser
