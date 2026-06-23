# TODO — SAGA

## NOW / prossimi
<!-- Lavoro attivo near-term: /catchup legge questa sezione, /wrap-up la aggiorna. Il resto del file e' backlog curato. -->
[x] **fix(dice) — ability scores INERTI in ogni check (mis-keying, bug LIVE nel playtest).** FATTO (commit 80fe1ec): `_STAT_FULL_NAMES` abbrev→nome pieno in `_handle_dice` + test sul formato chiavi reale FE, 394 unit verdi. Prompt-block e normalizzazione unica restano a `0010-F1`. Decoupled da ADR 0010 (vedi `0010-H1`). PROBLEMA: il FE salva `character_data.abilities` con **nomi pieni lowercase** (`{strength:16, dexterity:12, …}`, `frontend/src/features/campaign/data/class-presets.ts`); ma il risolutore del dado `core/dm/dm_tools_executor.py:217` legge `abilities.get(stat, abilities.get(stat.lower(), 10))` con `stat` = `"DEX"`/`"STR"`/… → cerca `"DEX"` poi `"dex"`, **non matcha `"dexterity"`** → fallback a 10 → `modifier = (10-10)//2 = 0` **SEMPRE**. Quindi **ogni `request_dice` ignora gli ability score** (tira a +0). Per contrasto: `core/combat/combat_graph.py:35` legge `abilities.get("DEX", abilities.get("dexterity", 10))` → matcha (iniziativa combat ok); `ai/prompts/dm.py:71` legge flat `char_data["dex"]` → mai popolato → il blocco `<abilities>` non compare nel prompt. **Tre convenzioni divergenti.** FIX MINIMO: allineare il lettore del dado (e il blocco prompt) alle chiavi reali del FE (nomi pieni lowercase) o normalizzare a un punto unico. NB: throwaway quando `0010-F1` ritipizza `character_data` (Pydantic), ma è ~1 riga e sana un bug che falsa OGNI tiro. Aggiungere un test: `request_dice` su DEX alta → `modifier > 0`.
[x] installer: merge del branch su `main` (squash) — sblocca il bottone "Run" dello smoke (`workflow_dispatch`)
[ ] installer: validare il ramo "auto-installa git/node/uv se mancanti" su VM/PC Windows VERGINE
[ ] companion: implementarli
[x] versioning: prima release **v0.1.0-beta.1** (manifest gia' a 0.1.0, nessun bump; SemVer + tag `v` + bump 0.x in CLAUDE.md). Tag dopo il merge di install-from-tag.
[ ] passare in rassegna le funzioni marcate #TODO nel codice (capire se servono)
[x] mypy backend: `[tool.mypy]` + verde (82 file) + gateato su pre-push E in CI (branch `fix/mypy`, PR aperta) — plugin pydantic, override import `pgvector`, stub types; boundary SDK e `computed_field` con `# type: ignore[code]` mirati; forward-ref ORM via `TYPE_CHECKING` (giu 2026)
[ ] vulture in CI (gate dead-code BE, speculare a knip FE): oggi 0 findings a `--min-confidence 80`. È euristico → se in futuro un falso positivo blocca una PR (route FastAPI, fixture pytest, `relationship` SQLAlchemy, attributi dinamici) NON abbassare la soglia: aggiungere un file whitelist vulture (equivalente di `knip.json`). Validare alla prima PR che tocca codice nuovo.
[x] installare `gh` CLI — fatto (giu 2026)
[x] validare la CI del branch `feat/claude-skills` via PR (il nuovo `prettier --check` in CI non ha ancora girato — scatta solo su PR o push a `main`)

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
[ ] icona custom `saga.ico` per la shortcut desktop (polish; la shortcut funziona anche senza)
[ ] (terziario) installer: porta PG dinamica. Oggi `54320` e' hardcoded in `start_saga.ps1`/`install_saga.ps1` senza check ne' fallback; se un processo TERZO la occupa, `pg_ctl start` fallisce il bind ma e' un exe nativo -> non fa scattare `$ErrorActionPreference=Stop` -> lo script prosegue su uvicorn che poi non trova il DB (fallimento muto). FIX: sondare una porta libera all'avvio, scriverla nel `.env`, passarla a pg_ctl; messaggio chiaro se il bind fallisce. Loopback-only (no esposizione di rete) gia' ok. Raro (un orfano stessa-datadir si auto-cura via postmaster.pid) -> farlo alla prima issue utente o quando ci sono 5 min per testare.
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
[ ] ATTIVARE il tiering del router: oggi importance_score e' hardcoded =5 (turns.py:91), quindi tutto il routing low/med/high di router.py e' inerte e paghi sempre il tier di default. aggiungere un pre-classificatore (mini-LLM o euristica) che deriva importance_score dall'azione del player. [spunto: NEQ action_predictor]

## memoria
[ ] recall pgvector: usare come query "azione + ultimi N turni" invece della sola query nuda (semantic.py) [spunto: dnd-llm-game]
[ ] summarization per "scena" (cambio location/combat) invece che a finestra fissa di turni; conservare i quotes[] dei dialoghi chiave [spunto: ai_rpg]
[ ] idempotency guard sui background task (turns.py): campo chronicled_at su Turn per non rieseguire fact-extraction/compression [spunto: aidm]
[ ] continuity_checklist: flag booleani machine-readable per NPC/location ("vivo: true", "sa_di_X: false") accanto alla prosa, per coerenza multi-sessione [spunto: aidm]

## combat
[ ] timeout esplicito per singola tool-call LLM in combat (oltre al recursion cap), con fallback "il turno prosegue" [spunto: llm-rpg]
[ ] formalizzare il circumstance modifier nel roll tool: {amount: -10..+10, reason: str}, mostrato al player [spunto: ai_rpg]
[ ] effetti temporizzati: tick per round su combat_state con auto-expire + annuncio (verificare se gia' in dm_tools_executor) [spunto: open-tabletop-gm]

## prosa / output
[ ] slop-buster: lista parole/n-gram in saga.config.yaml + check post-prosa nel DM (qualita' prosa = pillar) [spunto: ai_rpg]
[ ] popolare suggested_actions (oggi None) con blocklist di placeholder per filtrare scelte malformate [spunto: dnd-llm-game]

## world / player agency
[ ] override strutturati player->DM: NPC_PROTECTION / CONTENT_CONSTRAINT / TONE / NARRATIVE_DEMAND con scope (campaign/session/arc), persistiti e iniettati nel prompt ogni turno [spunto: aidm]
[ ] DM hidden notes / "mystery box": campo JSONB dm_notes (pensieri NPC nascosti, misteri decisi in anticipo, tensioni) aggiornato ogni N turni, per coerenza narrativa [spunto: ai_rpg]
[ ] narrative arc: blocco narrative_arc nel JSONB (beat "what_changes" + world_pressure) che il coordinator consulta per calibrare la pressione (NON plot rigido) [spunto: open-tabletop-gm, aidm]
[ ] WorldBuilder accept-not-reject: il DM accetta le asserzioni del player come canon salvo ambiguita' fisica (player co-autore), niente REJECT [spunto: aidm]
[ ] faction_moves: log esplicito delle azioni fazioni off-screen tra sessioni (verificare se il living-world gia' lo fa) [spunto: open-tabletop-gm]
[ ] living world: trigger su transizione oraria (dawn/dusk via GameClock gia' presente) oltre al counter turni [spunto: ai_rpg]
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
[ ] recall pgvector: aggiungere recency-weighting/decay + boost-on-access (oltre al top-K cosine puro) [spunto: aidm heat decay]
[ ] relationship graph: grafo relazioni NPC/fazioni/luoghi (tabella Postgres o JSONB) con query scene_context(place, present_npcs) BFS 2-hop; popolamento semi-auto dal session log via estrazione deterministica (verb-table); complementare al pgvector (tema vs scena) [spunto: open-tabletop-gm]

## fork B -> ADR 0003 (risoluzione a soglie fisse + danno server-side)
[ ] sostituire il DC deciso dall'LLM con soglie fisse stile PbtA: d20 + mod vs bande fisse (niente DC arbitrario), mantenendo i 6 outcome tier di dice.py
[ ] mappare outcome_tier -> danno lato server (FULL=pieno, PARTIAL=meta'+conseguenza, ...); l'LLM non tocca piu' gli HP
[ ] bande di risoluzione e mappature tier->danno in saga.config.yaml (std 14)

## fork C -> ADR 0004 (dm_core / game_system + tono per campagna)
[ ] separare dm_core (principi GM universali, immutabili) da game_system (regole D&D) caricabile -> predispone multi-TTRPG (Pathfinder/VtM) [spunto: open-tabletop-gm]
[ ] parametri di tono per campagna (darkness/pacing/lethality/magic) iniettati nel prompt DM [spunto: aidm DNA, ai_rpg]
[ ] system_prompt_addendum + writing_style_notes per campagna; config_override (JSONB) per-campagna mergiato con saga.config.yaml [spunto: NEQ, ai_rpg]

## fork D -> ADR 0005 (psicologia NPC multi-asse)
[ ] ridisegnare npc_psychology JSONB come multi-asse (trust / respect / affection / fear / ... 5-6 assi) con soglie nominate + first_impression_multiplier x3; sostituisce disposition_change scalare [spunto: ai_rpg dispositions, NEQ emotional vectors]

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
[ ] foreshadowing-seeds con lifecycle (PLANTED->RESOLVED) + ratifica -> di competenza dell'AI Director (vedi ADR 0006) [aidm]
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
[ ] AI Director: background ogni N turni, autorita' SOLO off-screen (fazioni/NPC assenti/clock/arc/semi), DM owns on-screen
[ ] coda pending_world_changes applicata dal turn path al turno successivo (single writer, niente race) + validazione consistenza all'apply (scarta/riconcilia se la precondizione non regge)
[ ] output = world data (fatti=hard ground-truth, pressione narrativa=soft advisory che il DM interpreta)
[ ] nuovo AICallType.DIRECTOR (thinking tier) + max_iterations cap (std 19) + disciplina sessioni rule-15

# ============================================================
# ADR 0007-0011 (giu 2026) -> follow-up. 0007-0010 = analisi Voyage; 0011 = refactor FE.
# vedi docs/adr/. 0007-0010 NON ancora Accepted (Proposed/WIP).
# vanno prima accettati.
# ============================================================

## ADR 0007 (Proposed) — direzioni adottate dalla Voyage
[ ] state-audit pass: secondo passaggio CHEAP, async e fuori dal critical path, che estrae/riconcilia lo stato implicato dalla narrazione vs i tool realmente eseguiti e patcha il drift (estrazione, NON decisione; niente two-pass pieno) [ADR 0007 §1]
[ ] massima configurabilita' della memoria + modelli per-sottosistema [ADR 0007 §2-3]

## ADR 0008 (Proposed — design fissato, TODO aperti prima di Accepted) — world model multi-layer YAML + grafo spaziale deterministico
[ ] chiudere i TODO di design: enum `kind` (A-i), transform/scale globale per livello (A-ii), sistema unita'/coordinate (B-i), vocabolario `terrain` + range `elevation_m` (B-ii), schema blocco `scenario` + seed della campagna (C-i)
[ ] poi: split in sprint di implementazione

## ADR 0009 (WIP, nulla deciso) — NPC enrichment (status, update_npc, archivio NPC rimossi)
[ ] analisi dedicata: decidere le meccaniche PRIMA di implementare (oggi e' solo direzione)

## ADR 0010 (WIP, nulla deciso) — customizzazione PG (skill progression + abilities configurabili)
[ ] analisi dedicata: decidere le meccaniche PRIMA di implementare (oggi e' solo direzione)

## ADR 0011 (Accepted) — E2E frontend mockato
[ ] variante E2E con backend reale + Docker (make test-infra-up + DB seedato + action->dado); oggi le /api sono mockate in-browser
