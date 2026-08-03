# TODO — SAGA

<!-- REGOLA DI POTATURA: questo file NON e' append-only (quello sono gli ADR).
     Si cancella tutto cio' che un lettore puo' recuperare da CHANGELOG.md, da un ADR,
     dal git log o da una GitHub issue. Si tiene solo cio' che andrebbe perso:
     lavoro aperto, avvertimenti operativi, e decisioni non scritte altrove.
     I BUG non stanno qui: vanno su GitHub issue (CLAUDE.md "Issue Convention"). -->

## NOW / prossimi
<!-- Lavoro attivo near-term: /catchup legge questa sezione, /wrap-up la aggiorna. -->
[~] **playtest su `v0.2.0-beta.1`**: primo giro fatto, i bug sono su GitHub. Resta da fare: rifare i turni su un modello competente (il primo giro era free-tier, vedi il commento su #52) e i cicli 0005/0008 qui sotto.
[~] **harness modelli (`backend/eval/`)**: fatto — 5 probe, scenari `empty`/`gold`/`bloat`/`contradiction`, colonna Δ, `--dry-run` per validare i prompt senza consumare quota. Il trascritto gold e' 25 turni ancorati al world reale, con lunghezza calibrata su produzione (1375 char/turno, misurati dal DB dev) e stato derivato replayando gli update negli handler veri. RESTA:
    [x] **passo `--derive`**: fatto, `eval/derive.py` — guida i sottosistemi VERI (compressore a batch, global summary iterativo, fact extractor) sui 25 turni. Nessun flag `--model`: passa dal router come la produzione, perche' un fixture riassunto da un modello migliore di quello che gira in gioco misura un mondo piu' facile del reale. `--dry-run` stampa modello risolto e budget chiamate; ogni chiamata e' checkpointata.
    [ ] **ri-derivare `gold`** (34 chiamate): la prima derivazione e' CONTAMINATA — girata prima del fix di #77, il `global_summary` e' il ragionamento del modello troncato a meta' parola. Il fixture committato ha `derived: true` e quindi il harness NON avvisa: rimettere `derived: false` finche' non si ri-deriva. Da rifare dopo #78, non prima: #77 toglie il troncamento ma il ragionamento puo' ancora finire dentro la risposta.
    [ ] **`derive.py` — persistere tutto e riemettere senza chiamate**: oggi cancella il checkpoint a fine run, quindi i riassunti dei batch che il lettore non raggiunge (vedi #79) sono persi. Salvare batch summary + corpus completo e poter riscrivere il fixture dallo stato salvato: quando ADR 0017 cambiera' le probe, il fixture si aggiorna a costo zero invece che a 34 chiamate.
    [ ] **probe canarino di memoria**: pianta un fatto nei `recalled_memories` che il modello non puo' inventare e verifica che lo usi. I tre canary sono gia' nel trascritto e il recall e' gia' autorato per probe; manca solo il check in `probes.py`. NB: il harness inietta il recall direttamente, quindi si puo' testare anche con #55 aperto.
    [ ] **probe due NPC presenti**: ADR 0017-A4 batcha le chiamate in una sola risposta del DM — il probe misura se il modello lo fa davvero invece di chiamarli in sequenza.
    [ ] varianti entropia in piu' (`rename`, `death`, `abandoned`, `language`): NON farle finche' `bloat`/`contradiction` non dicono qualcosa. `language` sarebbe la traduzione degli stessi 25 turni — l'unico modo controllato di mettere un numero su #51.
    NB: non aggiungere probe sulla disciplina combat, ADR 0003 rimuove `start_combat`.
    **IN PAUSA (2026-08-03) — perche'**: l'harness ha due strati con vite diverse. Lo scaffolding (trascritto, fixture, `derive.py`, replay negli handler veri) e' ancorato a mondo e storia, gli ADR non lo toccano: investimento stabile e sostanzialmente fatto. Le PROBE invece codificano obbligazioni sui tool, cioe' esattamente cio' che gli ADR in coda rimescolano — 0017 uccide `npc_followup` per costruzione (B2: il DM emette un marker vuoto, non riscrive la battuta, quindi #53 diventa impossibile) e cambia la forma del contratto di `invoke_npc` (B1: lista di 1..N battute, non `dialogue` singolo); 0003 rimuove `start_combat`. Ma la ragione decisiva non e' la churn: e' che il numero non sarebbe **azionabile**. Il prompt tuning e' gated su 0004, le violazioni sui tool su 0017/0003 — misureremmo una superficie che stiamo per rifare, senza poter toccare niente in risposta. Si riprende quando la superficie dei tool si ferma.
[ ] **quota OpenRouter**: il free tier e' ~50 richieste/giorno e si esaurisce in un giro di harness. Con 10 crediti una tantum passa a 1000/giorno sui modelli free (messaggio dell'API, 2026-07-27). Serve per misurare i modelli che gli utenti gireranno davvero. NB: non tarare mai i prompt su un modello che gli utenti non avranno.
[ ] **granularita' dei knob di memoria**: gli hardcode di `max_tokens` sono andati con #77, ma resta che compressione, estrazione fatti e global summary condividono un solo `memory_compression` pur avendo output di taglia molto diversa. Splittare quando ci sara' una ragione misurata, non prima — oggi il tetto e' generoso per tutti e tre e `finish_reason` intercetta chi lo sfonda.
[ ] **estrazione fatti a batch invece che per turno** (feature, non ADR — e' una manopola, non uno sprint): oggi ogni turno viene *spremuto* anche quando non e' successo niente, da cui fatti-rumore tipo "Lyra stops pretending to watch the tree line". Una chiamata ogni N turni sui turni grezzi lascia al modello lo spazio di scegliere cosa merita, e costa 3 chiamate invece di 25. N configurabile, cap dei fatti idem (std 14). NB: cambia *quando* gira l'estrazione in produzione (oggi e' fire-and-forget dopo ogni turno), e i fatti perdono l'attribuzione precisa al turno. Imparentata con "summarization per scena" piu' sotto.
[ ] **ADR 0017 — implementazione**: intervista fatta (2026-08-02), tutte le forche strutturali chiuse, ADR Proposed. I TODO aperti (valori numerici, token esatto del marker, forma dello split di `NarrationSegmentSchema`, finestra 500 char del beat 2) stanno nell'indice §4 dell'ADR, non qui. Tocca `dm.yaml` 31/42 → coordinare con 0004.
[ ] **ADR 0003 — implementazione S1-S4**: piano e contratti nell'ADR §7. Primo implementabile della coda dopo 0002.
[ ] **ADR 0005 — playtest veloce**: validare a mano la qualita' dei delta dal modello budget (rischio #1 dell'ADR, nessun test automatico possibile) — Lyra guardinga (trust −20 authored), minaccia a sconosciuto (×3 visibile in scena), favore+bugia (assi giusti si muovono), editor con asse custom. Se i delta sono scarsi il fix e' il wording del prompt, non lo schema.
[ ] **ADR 0008 — validazione manuale**: playtest a mano del ciclo (creazione campagna da world, move_to/viaggio/encounter, mappa, editor: crea/modifica/salva/export/import) in una chat a contesto pulito. NB operativo: le campagne del DB dev vecchie non hanno baseline (J2: wipe accettato, pre-1.0); `npm ci` locale richiede `--legacy-peer-deps` (conflitto peer eslint@10 pre-esistente nel lockfile, da sanare con le dependency updates).
[ ] **normalizzazione `character_data.abilities`** (residuo di 80fe1ec, owner: `0010-F1`): restano **tre convenzioni divergenti** sulle stesse chiavi — il FE salva nomi pieni lowercase (`{strength, dexterity, …}`, `class-presets.ts`), `combat_graph.py:35` legge `"DEX"` con fallback `"dexterity"`, `prompts/dm.py` legge flat `char_data["dex"]` che **non e' mai popolato** (il blocco `<abilities>` non compare mai nel prompt reale). Il dado e' stato allineato; il resto no. Normalizzare a un punto unico quando 0010-F1 ritipizza `character_data` con Pydantic.
[ ] **UI redesign — polish pass**: fix visivi minori rimasti su play screen e altrove, segnalati dall'owner ma non bloccanti. Da fare al prossimo giro sul frontend.
[ ] installer: validare il ramo "auto-installa git/node/uv se mancanti" su VM/PC Windows VERGINE (NON testabile da Linux: il bundle PG sono exe win64, pwsh-su-Linux solo parsa; serve VM Windows o Windows Sandbox)
[ ] passare in rassegna le funzioni marcate #TODO nel codice (capire se servono)
[ ] code quality: barrel export puliti — `index.ts` per feature/modulo FE che ri-esportano l'API pubblica. Per il BE valutare `__init__.py` con re-export MA attenzione ai cicli d'import (Python preferisce path espliciti — barrel meno idiomatico che in TS; farlo solo dove riduce davvero il rumore).

## avvertimenti operativi
<!-- Cose che non stanno in nessun ADR e che ci si dimentica. -->
[!] **vulture**: e' euristico. Se un falso positivo blocca una PR (route FastAPI, fixture pytest, `relationship` SQLAlchemy, attributi dinamici) **NON abbassare la soglia** — aggiungere un file whitelist (equivalente di `knip.json`). NB: a `--min-confidence 80` NON ha intercettato `decrypt_api_key`, funzione pubblica mai chiamata (vedi #65) — la soglia lascia passare proprio il caso che sarebbe servito.

## infra / distribuzione
[ ] debug con docker
[ ] nginx: serve davvero?
[ ] installer macOS: job `macos-smoke` in `installer-smoke.yml` DA VALIDARE al primo dispatch. Sospetto principale se rosso: `brew install pgvector` builda l'estensione contro il postgres di default di brew invece di `postgresql@16` (mismatch di linking). Non testabile in locale — solo via runner CI.
[ ] icona custom `saga.ico` per la shortcut desktop (polish; la shortcut funziona anche senza)
[ ] dependency updates (Dependabot, 1 PR raggruppata per ecosystem): VALIDARE prima del merge. Major che rompono = NON auto-merge, sono migrazioni: (a) **frontend** React 19 + `react-i18next` v17 — i18next 15→17 rompe tutte e 32 le suite di test (PR #17/18/19 chiuse per questo) → migrazione FE dedicata; (b) **backend** `google-genai` 1.68→2.9 — la CI mocka le chiamate LLM, quindi verde NON garantisce il runtime → smoke test contro l'API reale prima di fidarsi. Postura: patch/minor+security subito, major schedulati.
[ ] CD: `release.yml` tag-triggered — DA FARE INSIEME a Docker→GHCR, non prima. `release.sh` pubblica gia' la Release e allega gli installer; un'Action solo per quello sarebbe over-engineering — si ripaga quando la CI deve BUILDARE artefatti che non vuoi sul laptop. PREREQUISITO: i Dockerfile attuali sono DEV-image (frontend = vite dev server; backend single-stage + bind-mount + `--reload`) → NON pubblicabili. Servono prima Dockerfile di PRODUZIONE e decidere se **una sola** immagine (FastAPI serve la SPA, ADR 0000) o due. Modello scelto: tag-triggered, cosi' la CI non scrive mai su `main`. Quando si fa → ADR "CD artefatti".

## world-building / template
[ ] template + world-building fatti bene (tanti yaml indentati per profondita'/dettaglio del mondo). attenzione a non saturare il contesto → analisi dettagliata

# ============================================================
# da analisi multi-repo (giu 2026): NEQ, ai_rpg, dnd-llm-game,
# aidm, llm-rpg, open-tabletop-gm, Friends&Fables.
# keeper indipendenti dai fork.
# ============================================================

## memoria
[ ] summarization per "scena" (cambio location/combat) invece che a finestra fissa di turni; conservare i quotes[] dei dialoghi chiave [ai_rpg]
[ ] idempotency guard sui background task (turns.py): campo chronicled_at su Turn per non rieseguire fact-extraction/compression [aidm]
[ ] continuity_checklist: flag booleani machine-readable per NPC/location ("vivo: true", "sa_di_X: false") accanto alla prosa, per coerenza multi-sessione [aidm]

## combat
[ ] timeout esplicito per singola tool-call LLM in combat (oltre al recursion cap), con fallback "il turno prosegue" [llm-rpg] — NB ridimensionato da ADR 0003 B1: il combat non fa piu' chiamate LLM per le azioni nemiche; resta il timeout generico per tool-call

## prosa / output
[ ] **prompt tuning pass dedicato**: rivedere e calibrare i prompt DM/NPC. Ora ha una base empirica — `model_smoke.py` misura la compliance, e le issue #51/#52/#53 hanno i numeri. Include la qualita' di `axis_changes` (ADR 0005). Da fare col factoring di ADR 0004, non prima.
[ ] LangSmith: verificare su tracce reali cosa entra davvero nel contesto per ogni nodo del grafo (prompt effettivi, non presunti)
[ ] slop-buster: lista parole/n-gram in saga.config.yaml + check post-prosa nel DM (qualita' prosa = pillar) [ai_rpg]
[ ] popolare suggested_actions (oggi None) con blocklist di placeholder per filtrare scelte malformate [dnd-llm-game]

## world / player agency
[ ] override strutturati player→DM: NPC_PROTECTION / CONTENT_CONSTRAINT / TONE / NARRATIVE_DEMAND con scope (campaign/session/arc), persistiti e iniettati nel prompt ogni turno [aidm]
[ ] WorldBuilder accept-not-reject: il DM accetta le asserzioni del player come canon salvo ambiguita' fisica (player co-autore), niente REJECT [aidm]
[ ] meta-channel: intent /meta che NON consuma un turno di gioco (feedback al DM fuori dalla narrativa) [aidm]
[ ] "player input come ispirazione" (parcheggiato da ADR 0013, e' gameplay non UI) → merita un ADR suo

## homebrew / custom
[ ] upload PDF lore homebrew → chunking + embedding su pgvector, associato a campagna, recuperato nel recall (riusa pgvector, non LanceDB) [dnd-llm-game]
[ ] formalizzare lo schema "pacchetto campagna" export/import (aree/NPC/mostri/plot): estende export.py + pillar data-sovereignty [NEQ moduli drop-in]

## concorrenza (minore)
[ ] advisory lock per campagna sul turn handler: turn_number e' gia' atomico ma world_state ha una race last-writer-wins su turni concorrenti (stretta: e' single-user REST) [aidm]

# ============================================================
# SECONDARI / deferred — bassa priorita', alcuni legati a versioni future.
# ============================================================

## secondari — combat / gioco
[ ] toggle prompt combat full/compresso, CONFIGURABILE in saga.config.yaml [NEQ]
[ ] op_dominant: reframe narrativo su tier-gap forte (combattente molto superiore) [aidm]
[ ] focus-budget: limite caratteri dell'azione come stat di gioco [llm-rpg]
[ ] enemy come agente LLM autonomo / pipeline simmetrica hero-enemy [llm-rpg]

## secondari — memoria / world
[ ] lorebook "constant entries" sempre iniettate (regole mondo/magia) [ai_rpg]
[ ] tool di ricerca keyword/fulltext sul log di campagna [otgm]

## secondari — world-gen / template (alimentano "template fatti bene" sopra)
[ ] Three Truths per elemento: Obvious / Discoverable / Secret [otgm]
[ ] Threat-Arc table a 5 stadi (Now → No Return) con trigger e reversal [otgm]
[ ] faction inbound-relationships generator (come le fazioni esistenti vedono la nuova) [ai_rpg]
[ ] word-steering per nemici tematici (liste parole) [llm-rpg]
[ ] GM-player-calibration notes (stile del player, persistente, letto a inizio sessione) [otgm]
# nota: calendario fantasy (mesi/stagioni/festivita') = gia' coperto da "template fatti bene"

## secondari — infra / dev
[ ] narrative-probe v2 per calibrare quali modelli nei tier del router [otgm] — primo mattone posato: `model_smoke.py` misura la compliance ai tool. Manca il pezzo "qualita' narrativa" e il collegamento ai tier di ADR 0016.
[ ] LLM-fixture-file per test end-to-end deterministici [ai_rpg]
[ ] subprocess isolation per generazione modulo AI lunga [NEQ]
[ ] cached_property per il config loader [llm-rpg]
[ ] mod-system con scope isolato + route namespaced — SCOPE DEFERRED, molto in fondo (ADR quando si progetta l'estensibilita') [ai_rpg]

## secondari — v3
[ ] TLS self-signed + distribuzione cert per LAN [otgm]
[ ] Hero globali riusabili tra campagne (Hero vs Character) [dnd-llm-game]

# ============================================================
# ADR: follow-up aperti. Il contenuto di ogni decisione sta nell'ADR,
# qui solo cio' che resta da fare e non e' scritto la'.
# ============================================================

## ADR 0007 (Proposed) — direzioni adottate dalla Voyage
[ ] massima configurabilita' della memoria + modelli per-sottosistema [§2 — direzione; primi frutti: whitelist 0004, famiglia recall.* in 0002 S1]

## ADR 0010 (Proposed — design pass 2 fatto 2026-07-12) — customizzazione PG
[ ] implementazione S1-S5 (rulebook / runtime / progressione / item / FE): piano nell'ADR §7. Gate di 0012, 0014 e 0015.

## ADR 0011 (Accepted) — E2E frontend mockato
[ ] variante E2E con backend reale + Docker (make test-infra-up + DB seedato + action→dado); oggi le /api sono mockate in-browser
