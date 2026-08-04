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
    [ ] **ri-derivare `gold`** (34 chiamate, `uv run python eval/derive.py gold`): la prima derivazione e' CONTAMINATA — girata prima del fix di #77, il `global_summary` e' il ragionamento del modello troncato a meta' parola, e il fixture e' stato rimesso a `derived: false` finche' non si rifa'. Da rifare dopo **#78**, non prima: #77 toglie il troncamento ma il ragionamento puo' ancora finire dentro la risposta.
    [ ] **`derive.py` — persistere tutto e riemettere senza chiamate**: oggi cancella il checkpoint a fine run, quindi i riassunti dei batch che il lettore non raggiunge (vedi #79) sono persi. Salvare batch summary + corpus completo e poter riscrivere il fixture dallo stato salvato: quando ADR 0017 cambiera' le probe, il fixture si aggiorna a costo zero invece che a 34 chiamate.
    [ ] **probe canarino di memoria**: pianta un fatto nei `recalled_memories` che il modello non puo' inventare e verifica che lo usi. I tre canary sono gia' nel trascritto e il recall e' gia' autorato per probe; manca solo il check in `probes.py`. NB: il harness inietta il recall direttamente, quindi si puo' testare anche con #55 aperto.
    [ ] **probe due NPC presenti**: ADR 0017-A4 batcha le chiamate in una sola risposta del DM — il probe misura se il modello lo fa davvero invece di chiamarli in sequenza.
    [ ] varianti entropia in piu' (`rename`, `death`, `abandoned`, `language`): NON farle finche' `bloat`/`contradiction` non dicono qualcosa. `language` sarebbe la traduzione degli stessi 25 turni — l'unico modo controllato di mettere un numero su #51.
    NB: non aggiungere probe sulla disciplina combat, ADR 0003 ha rimosso `start_combat`.
    **IN PAUSA (2026-08-03) — perche'**: l'harness ha due strati con vite diverse. Lo scaffolding (trascritto, fixture, `derive.py`, replay negli handler veri) e' ancorato a mondo e storia, gli ADR non lo toccano: investimento stabile e sostanzialmente fatto. Le PROBE invece codificano obbligazioni sui tool, cioe' esattamente cio' che gli ADR in coda rimescolano — 0017 uccide `npc_followup` per costruzione (B2: il DM emette un marker vuoto, non riscrive la battuta, quindi #53 diventa impossibile) e cambia la forma del contratto di `invoke_npc` (B1: lista di 1..N battute, non `dialogue` singolo); 0003 ha gia' rimosso `start_combat`. Ma la ragione decisiva non e' la churn: e' che il numero non sarebbe **azionabile**. Il prompt tuning e' gated su 0004, le violazioni sui tool su 0017/0003 — misureremmo una superficie che stiamo per rifare, senza poter toccare niente in risposta. Si riprende quando la superficie dei tool si ferma.
[ ] **quota OpenRouter**: il free tier e' ~50 richieste/giorno e si esaurisce in un giro di harness. Con 10 crediti una tantum passa a 1000/giorno sui modelli free (messaggio dell'API, 2026-07-27). Serve per misurare i modelli che gli utenti gireranno davvero. NB: non tarare mai i prompt su un modello che gli utenti non avranno.
[ ] **granularita' dei knob di memoria**: gli hardcode di `max_tokens` sono andati con #77, ma resta che compressione, estrazione fatti e global summary condividono un solo `memory_compression` pur avendo output di taglia molto diversa. Splittare quando ci sara' una ragione misurata, non prima — oggi il tetto e' generoso per tutti e tre e `finish_reason` intercetta chi lo sfonda.
[ ] **estrazione fatti a batch invece che per turno** (feature, non ADR — e' una manopola, non uno sprint): oggi ogni turno viene *spremuto* anche quando non e' successo niente, da cui fatti-rumore tipo "Lyra stops pretending to watch the tree line". Una chiamata ogni N turni sui turni grezzi lascia al modello lo spazio di scegliere cosa merita, e costa 3 chiamate invece di 25. N configurabile, cap dei fatti idem (std 14). NB: cambia *quando* gira l'estrazione in produzione (oggi e' fire-and-forget dopo ogni turno), e i fatti perdono l'attribuzione precisa al turno. Imparentata con "summarization per scena" piu' sotto.
[ ] **ADR 0017 — implementazione**: intervista fatta (2026-08-02), tutte le forche strutturali chiuse, ADR Proposed. I TODO aperti (valori numerici, token esatto del marker, forma dello split di `NarrationSegmentSchema`, finestra 500 char del beat 2) stanno nell'indice §4 dell'ADR, non qui. Tocca `dm.yaml` 31/42 → coordinare con 0004.
[ ] **ADR 0005 — playtest veloce**: validare a mano la qualita' dei delta dal modello budget (rischio #1 dell'ADR, nessun test automatico possibile) — Lyra guardinga (trust −20 authored), minaccia a sconosciuto (×3 visibile in scena), favore+bugia (assi giusti si muovono), editor con asse custom. Se i delta sono scarsi il fix e' il wording del prompt, non lo schema.
[ ] **ADR 0008 — validazione manuale**: playtest a mano del ciclo (creazione campagna da world, move_to/viaggio/encounter, mappa, editor: crea/modifica/salva/export/import) in una chat a contesto pulito. NB operativo: le campagne del DB dev vecchie non hanno baseline (J2: wipe accettato, pre-1.0).
[ ] **normalizzazione `character_data.abilities`** (residuo di 80fe1ec, owner: `0010-F1`): restano **tre convenzioni divergenti** sulle stesse chiavi — il FE salva nomi pieni lowercase (`{strength, dexterity, …}`, `class-presets.ts`), `core/attack.py:50` e `core/dm/dm_tools_executor.py:191` mappano `"DEX"` → `"dexterity"`, `prompts/dm.py:57` legge flat `char_data["dex"]` che **non e' mai popolato** (il blocco `<abilities>` non compare mai nel prompt reale). Il dado e' stato allineato; il resto no. Normalizzare a un punto unico quando 0010-F1 ritipizza `character_data` con Pydantic.
[ ] **lo stato di runtime non e' tipizzato da nessuna parte, e ogni chiave morta sta li'** (audit 2026-08-04). La linea esiste gia' nel repo: il **contenuto autorato** e' Pydantic (`world.py`, `npc.py`, `npc_class.py`, `npc_fields.py`, `psychology.py`) e non ha una sola chiave morta; lo **stato di runtime** (`character_data`, `world_state`, `quests`) e' dict libero e le ha tutte. Candidati, in ordine: (1) **`character_data`** — lo schema esiste gia' ma scritto in TypeScript (`types/index.ts:25`) e non applicato in Python, cioe' un contratto che una sola sponda rispetta; owner `0010-F1`. (2) **`world_state` al confine, non nella scala** — le rung lavorano per definizione su forme vecchie, quindi si tipizza l'ingresso/uscita sostituendo `ALLOWED_WORLD_STATE_KEYS` (oggi controlla i nomi e non i tipi, e infatti non ha fermato niente). (3) `quests`, minuscolo, viene gratis col fix di #86. **NON** tipizzare `traits` e gli assi `psychology`: sono aperti per progetto (tassonomia autorata dal mondo, 0005/0009).
[ ] **le fixture scritte a mano certificano bachi** (audit 2026-08-04, deciso: si fa DOPO la scelta sulla tipizzazione qui sopra, cosi' il registro si progetta una volta sola). Il pattern: il test si costruisce lo stato di input E asserisce sulla resa in output, quindi la fixture e' una **seconda definizione dello schema** che nessuno confronta col produttore; quando divergono il test pinna la forma sbagliata. `test_dm_prompt_xml.py` scriveva `{"hp": 12, "max_hp": 20}` e asseriva `hp="12/20"`: verde, mentre la produzione (`{current, max}`) rendeva un repr di dict. Il rimedio scelto e' un **conformance check fixture↔seed**, non fixture derivate: derivarle toglie la possibilita' di *vedere* lo stato sotto test in ~30 file, per un difetto che ne colpisce pochi. NB decisivo per scriverlo: e' un check di **forma, non di uguaglianza** — una fixture deve poter avere valori diversi (eroe ferito, NPC morto, e' il suo scopo), non percorsi di chiave e tipi diversi. Entrambi i bachi erano violazioni di forma. Buco noto: copre solo le fixture registrate, e chi scrive un test puo' non registrarla — la tipizzazione quel buco non ce l'ha, quindi i due rimedi sono complementari e non alternativi. Stessa malattia dell'alembic qui sotto: il test fabbrica l'artefatto invece di esercitare il produttore. Gli standard 1 e 5 lo dicevano gia'.
[ ] **il frontend ha la stessa malattia, senza nemmeno il cancello** (audit 2026-08-04): `api.get<Campaign>()` (`client.ts:56`) e' un'**asserzione di tipo, non un controllo** — zero validazione runtime, nessuno zod, quindi il JSON che arriva non viene mai confrontato con l'interfaccia. `WorldState` (`types/index.ts:82`) ha per giunta `[key: string]: unknown`, quindi non puo' intercettare una chiave sconosciuta: aperto travestito da chiuso. Resta la deriva sulle chiavi: mancano `player_position`, `node_status`, `edge_overrides`, `consumed_encounters`, `pending_travel`, `narrative`, `dm_heals`. Da affrontare insieme alla tipizzazione backend: sono lo stesso schema copiato a mano due volte, e finche' la copia resta a mano ridivergera'. `CharacterData.hp` e `CompanionData` invece combaciano con la produzione.
[ ] **chiavi orfane rimaste, tutte scritture** (audit 2026-08-04, non bloccanti): `world_state["factions"]` seedata e mai letta; `narrative.event_log` cresce a ogni evento e nessuno la consuma; `char_data["notes"]` seedata dal FE e mai letta. Droppare il payload richiede un rung v8→v9 + verifica del round-trip export/import, quindi non e' pulizia — si fa quando c'e' un'altra ragione per toccare lo schema. NB: `dm_heals` (`health.py:65`) vive in `world_state` ma **non e' in `ALLOWED_WORLD_STATE_KEYS`** — innocua oggi perche' il `ToolResult` scrive diretto, trappola se un domani passasse dal merge generico di `updater.py:186`.
[ ] **`companions` e' un fossile che spegne un gruppo di tool** (audit 2026-08-04, owner: ADR 0014): nessuno **aggiunge** mai un compagno — `updater.py:120` muta solo se il target c'e' gia'. Quindi il gate `companion_active` (`tool_groups.py:20`) e' sempre False e quel gruppo di tool non si e' mai attivato. Da chiudere con 0014, che gia' prevede di ritirare il fossile.
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

## prompt tuning — bersagli gia' noti (fare col pass di ADR 0004)
[ ] **la convenzione di scambio e' l'unico punto di ADR 0003 non chiuso per costruzione** (deciso 2026-08-04, vedi nota su C1c). Senza round, se il DM si dimentica di chiamare `attack` per i nemici il giocatore mena gratis — fallisce in silenzio e a suo favore. Il backstop deterministico e' stato progettato e rifiutato dall'owner: era fattibile (gli eventi `attack` esistono da S2b, nessun LLM coinvolto), ma la regola di disingaggio sotto non ha una risposta difendibile senza dati di playtest. Da misurare col playtest e poi con la probe nell'harness: **quante volte per scontro gli ostili in scena non rispondono**. Se il numero e' basso resta com'e'.
[ ] **`recent_events` e' calcolato e mai letto** (`ai/context.py:178` — gli ultimi 3 turni riassunti, `build_dm_system_prompt` non li tocca). Renderizzarli nel prompt e' un candidato del tuning pass: dare al DM il filo di cosa e' appena successo abbassa la probabilita' che si dimentichi lo scambio. NB: abbassa le probabilita', non chiude il buco. Quarta chiave morta trovata in questa sessione (con `in_combat`, `char_data["death_mode"]` e il tier `low`/`medium` identico) — vale la pena un giro sistematico a caccia di lettori senza scrittori e scrittori senza lettori.

## infra — migrazioni mai eseguite dai test
[ ] **nessuna migrazione alembic e' coperta dalla suite, e questo ha gia' morso** (2026-08-04, ADR 0003 S3/S4). `tests/conftest.py` costruisce lo schema con `Base.metadata.create_all`; la catena alembic non e' comunque eseguibile da zero (`001_add_memory_facts` presuppone che le tabelle esistano). Quindi una migrazione rotta passa la CI **verde**. **Prova**: la `005_campaign_difficulty` e' stata spedita con un baco che avrebbe messo a NULL la colonna di ogni campagna — SQLAlchemy persiste uno `StrEnum` col **nome** del membro (`CRONISTA`), la migrazione confrontava i **valori** (`cronista`). Verifica a mano su un DB costruito a mano NON l'ha preso, perche' avevo creato il tipo con le label che assumevo io: la fixture riproduce l'assunzione, non il database. L'ha preso il docker dev al primo avvio. Ora la 005 e' corretta, ha un guard che solleva sui valori non mappabili, ed e' verificata upgrade/downgrade/upgrade su una **copia del DB dev** con dati reali — ma il buco strutturale resta.
    NB operativo: il DB dev non aveva `alembic_version` (creato da `create_all`, alembic non ci ha mai girato). E' stato stampato a `004` e migrato. Un DB utente nella stessa condizione ha bisogno dello stesso trattamento.
    Da sanare: o una migrazione `000` che crea lo schema base, oppure una fixture che fa `alembic upgrade head` invece di `create_all` — la seconda copre davvero ma richiede la prima. Terza opzione piu' economica: un singolo test di integrazione che, su un DB usa-e-getta seedato da `create_all` + `alembic stamp <penultima>`, gira l'ultima migrazione avanti e indietro.

## ADR 0016 (Proposed) — da RIDIRIGERE: ritirare, non sistemare
[ ] **l'importance scoring non instrada niente, e 0016 non lo sa** (trovato 2026-08-04 con ADR 0003 S0). Tre cose insieme: le keyword sono inglesi, quindi in italiano il punteggio e' 5 fisso; il bonus combat leggeva `world_state["in_combat"]` che **nessuno scriveva** tranne il test che lo asseriva — riga e chiave cancellate da 0003 C1b, resta la sola formula a keyword; e i tier `low`/`medium` della config di default hanno **lo stesso modello**. Quindi due terzi della scala non cambierebbero nulla comunque. Piu' l'argomento dell'owner: in BYOAK gli utenti montano modelli free o da pochi centesimi, mai un modello da 25$/M — lo spread che il router ottimizza non esiste, e un router che declassa in silenzio e' peggio di nessun router. Direzione: 0016 passa da "sistemare il punteggio" a **"ritirare il punteggio, tenere il routing per tipo di chiamata"** (`dm_narration` vs `memory_compression`/`embedding` risparmia davvero — sono l'alto volume). Il pillar CLAUDE.md "Intelligent AI Routing" sopravvive letto come cost routing per call type. Quando si fa: droppare anche la colonna `Turn.importance_score` (alembic) + lo schema API. Serve un design pass in place su 0016 (e' Proposed, si puo' — precedente: 0003 ha superseduto la sua bozza in place). ADR 0003 ha cancellato solo la riga morta (C1b), non l'ha sostituita.

## ADR 0017 (Proposed) — follow-up
[ ] **`invoke_npc` promette azioni e consegna battute** (trovato 2026-08-04): la descrizione del tool dice *"Make an NPC speak **or act**"* ma la riga dopo dice *"will generate dialogue in character"*, e il meccanismo restituisce solo dialogo (`tools_npc.py:56`). Scollamento prompt/meccanica da sanare quando 0017-B1 riscrive il contratto in lista di 1..N battute — decidere se le azioni NPC entrano davvero o se la descrizione va ristretta.

## ADR 0010 (Proposed) — vincolo da ADR 0003
[ ] **il prune dei cadaveri non deve mangiare il loot**: 0003-B2 pota i record `auto_created` morti dopo N giorni-gioco, ma 0010-I8 mette addosso ai mook le pool di oggetti della loro `npc_class`. 0003 fissa il vincolo (`require_empty_inventory: true`); quando 0010 introduce gli oggetti va verificato che il guard regga davvero — e' l'unica cosa che impedisce al bottino di svanire col cadavere.

## ADR 0007 (Proposed) — direzioni adottate dalla Voyage
[ ] massima configurabilita' della memoria + modelli per-sottosistema [§2 — direzione; primi frutti: whitelist 0004, famiglia recall.* in 0002 S1]

## ADR 0010 (Proposed — design pass 2 fatto 2026-07-12) — customizzazione PG
[ ] implementazione S1-S5 (rulebook / runtime / progressione / item / FE): piano nell'ADR §7. Gate di 0012, 0014 e 0015.

## ADR 0011 (Accepted) — E2E frontend mockato
[ ] variante E2E con backend reale + Docker (make test-infra-up + DB seedato + action→dado); oggi le /api sono mockate in-browser
