# ADR 0020 — Rifacimento della produzione della memoria

- **Status**: **Proposed** — intervista owner 2026-11-08/09 e contratti tecnici S0 documentati; implementazione, valori e variante production subordinati alle verifiche e ai gate dell'eval (§11, §20–22).
- **Date**: 2026-11-09.
- **Context items / sources**: issue [#79](https://github.com/tommasomattarelli/saga/issues/79), [#80](https://github.com/tommasomattarelli/saga/issues/80); intervista owner; ADR 0001, 0002, 0017, 0018 e 0019.

## 0. Provenienza, stato e gate

Questo ADR è una copia adattata del piano `memory-production-refactor.md` dell'intervista owner, non una seconda progettazione. Le decisioni e il dettaglio delle sezioni 1–16 sono conservati; la verifica tecnica S0 li concretizza senza riaprire l'intervista. Il piano esterno originale non viene modificato né richiede manutenzione parallela: questo documento è il riferimento versionato per l'implementazione.

La copia iniziale era identica al piano, SHA-256 `ba68ffd1a60254961d1b344324cf859fcb131a5c2a20f4fbedf0f02f14280a86`. Le aggiunte S0 sono datate e distinguibili dalle decisioni dell'intervista.

Legenda: **Decided** = semantica scelta dall'owner; **Refined (S0)** = concretizzazione tecnica compatibile; **TODO / gate** = scelta esplicitamente aperta, da chiudere nel punto indicato. Proposed non significa che i gate numerici o live siano già superati.

### Stato di partenza verificato al catchup S0

- Repository: `/home/tommasomattarelli/Desktop/saga`.
- Branch al catchup: `main`, allineato a `origin/main`, working tree pulito; confermato nuovamente in S0.
- HEAD verificato: `a09ebfc`, merge PR #112, riorganizzazione `backend/eval/`.
- Release più recente osservata: v0.3.1.
- L'owner ha confermato `saga_check full` verde e chiesto di NON ripeterlo prima di partire. Verificare eventuali modifiche intervenute nel frattempo; non lanciare un check iniziale per riflesso.
- Al catchup i servizi erano spenti. Avviare l'infrastruttura di test quando servono i test DB, non per la sola progettazione.
- **Nel primo commit** eliminare da `TODO.md` la sottovoce harness «sistemare cartella», già completata dalla PR #112; le altre voci non sono chiuse dalla sola progettazione.
- Le altre voci TODO si potano quando il relativo lavoro è effettivamente completato.

### Preferenze operative dell'owner

- Per leggere/mappare codice delegare a **GPT-6 Luna**, anche con più agenti in parallelo. Modello risolto e disponibile: `openai/gpt-6-luna`. Non sostituirlo con altri modelli senza richiesta.
- L'agente principale legge direttamente i passaggi critici e verifica i report: un errore importante del primo report è stato corretto proprio così, vedi §2.
- Usare il tool domande per decisioni ancora aperte, non assumere implicitamente numeri, budget o autorizzazioni.
- Lavoro diviso in branch operativi, merge **`--no-ff`** nell'integrazione, **una sola PR finale verso main**.
- L'owner non vuole comprimere artificialmente un lavoro grande in 6–7 commit totali. Le unità devono essere reviewabili e i commit logici; se una fase si allarga, suddividerla ulteriormente invece di creare mega-commit.
- Il DB locale di test è sacrificabile, ma questo non autorizza cancellazioni indiscriminate di altri database. Nessuna cancellazione è stata eseguita in questa sessione.

## 1. Obiettivo e confine concordato

Riprogettare la **produzione della memoria**: contesto integrale, summary intermedi, globale, fact extraction, fonti strutturate, avanzamento durevole, salvataggi coerenti ed export completo.

L'owner vuole correggere il disegno iniziale, non soltanto applicare due patch ai bug noti.

### Dentro questo lavoro

1. Tre livelli temporali con copertura esplicita: raw recenti → summary intermedi → globale remoto.
2. Estrazione di fatti a batch, ricchi di metadati e con provenienza verificabile.
3. Esiti delle operazioni e delta prima/dopo per alimentare le generazioni.
4. Lavori persistenti, retry limitati, idempotenza della pubblicazione, recupero dopo restart.
5. Soglie di arretrato che impediscano crescita illimitata del contesto.
6. Salvataggi e continuazioni che isolino correttamente la storia attiva.
7. Export di tutta la campagna, incluse storie conservate e memoria.
8. Misure deterministiche, eval della qualità e verifica della pipeline reale.
9. Ritiro della vecchia compressione per-turno e degli embedding dei suoi summary.

### Lavoro successivo

- Query semantica arricchita, ranking, soglie, scoring, uso dei metadati nel retrieval.
- Eventuali collegamenti tra fatti di batch diversi, riconciliazione o fatti di stato aggiornabili.
- Indicizzazione semantica dei nuovi summary, se il futuro retrieval ne dimostra l'utilità.
- Filtri più elaborati per categoria di evento, se l'eval mostra rumore.

**Eccezione necessaria di correttezza:** anche il retrieval attuale deve escludere fatti di storie/futuri non attivi. Questo filtro appartiene a questo branch; non equivale a ridisegnare il ranking.

Il progetto si applica a **nuove campagne**. L'owner ha escluso conversione/backfill della vecchia memoria. Questo non elimina la necessità di migrazioni forward dello schema e di verificare l'installazione da DB vuoto.

## 2. Stato reale del codice e prove da non perdere

### Difetto decisivo: compressore non raggiunto dai turni normali

`backend/app/api/turns.py:169` genera sempre il summary euristico; `:190-204` lo salva sul nuovo Turn. `backend/app/memory/compressor.py:148-159` cerca soltanto `summary IS NULL`. Quindi il compressore LLM **non elabora normalmente i turni nuovi**.

Il chunk hardcoded di 5 in `compressor.py:165` è un massimo, non un'attesa di batch completi. Il primo report Luna lo descriveva erroneamente come writer già a batch fissi; la verifica diretta e il follow-up hanno corretto la conclusione. Non usare quella descrizione errata come baseline dell'ADR.

### Altri punti verificati

| Area | Evidenza attuale |
|---|---|
| Raw | `ai/context.py:69-88`: ultime N righe Turn, default `gameplay.context_window_turns: 8`, più azione corrente. |
| Reader summary | `ai/context.py:91-118`: massimo 5 righe, deduplica per testo; non 5 batch distinti. Issue #79 aperta. |
| Taglio del contesto | `ai/context.py:36-66`: stima caratteri/4 su system+messaggi, elimina coppie raw senza compensare la copertura. `context_token_cap: 12000`. Non è un limite effettivo garantito del modello. |
| Globale | `memory/global_summary.py:55-117`: precedente globale + ultimi N turni calcolati da current_turn. Trigger modulo N in `api/turns.py:254-260`; nessun watermark, retry durevole o fencing. Un aggiornamento saltato non viene recuperato dal successivo. |
| Fact extraction | `memory/fact_extractor.py`: chiamata per turno, cap hardcoded 5, input azione+narration; errori di parsing e lista vuota confluiscono in `[]`. Issue #80 aperta. |
| Scheduling | `api/turns.py:243-260`: task fire-and-forget dopo il commit, distinti dalla coda persistente degli embedding. |
| Recall | `core/dm/dm_nodes.py:55-72`, `memory/recall.py`, `memory/semantic.py`: embedding della sola azione, top-3 cosine, solo fatti, niente cutoff di similarità. |
| Indice | Indici versionati e `source_embeddings` da ADR 0018; non confondere le colonne legacy Vector(384) con lo storage realmente usato dal recall. |
| Tool | `core/dm/dm_tools_executor.py:122-152`: eventi solo per tool `visible()`, con args/description/extra, senza delta o outcome uniforme. |
| NPC | `core/dm/npc_beat.py:79-114`: effetti applicati fuori dal percorso ordinario degli eventi tool. |
| Load | `api/saves.py:95-100`: ripristina mondo/personaggio/quest/numero turno, ma non storia, fatti, globale, embedding o task. |
| Identità turni | `turn_number` non è univoco per campagna. Il load può riusare numeri con vecchie righe ancora presenti. |
| Export | `api/export.py:46-78`: non esporta summary/global, tool events o metadati ricchi. Nessun endpoint import campagne individuato. |

`Save.scene_summary` è scritto e restituito dall'API ma non ha un consumer frontend individuato. L'autosalvataggio può usare un'etichetta semplice come il manuale, senza mantenere la vecchia sintesi euristica.

### Issue e documenti

- #79 OPEN: <https://github.com/tommasomattarelli/saga/issues/79>.
- #80 OPEN: <https://github.com/tommasomattarelli/saga/issues/80>.
- #55, #77 e #78 risultavano CLOSED. Non trattare i vecchi difetti embedding/troncamento/reasoning come ancora aperti senza nuova evidenza.
- `docs/adr/README.md`: leggere prima degli ADR. Al catchup l'ultimo ADR era 0019; questo record aggiunge 0020.
- ADR 0002 è Proposed: contiene un progetto di recall/grafo, non un'autorizzazione ad implementarlo qui.
- ADR 0018 Accepted: rispettare identità degli spazi embedding, policy/credenziali correnti e separazione storage sorgenti/vettori. Il ritiro delle sorgenti TURN richiede una nuova decisione documentata; non modificare retroattivamente l'ADR Accepted.
- ADR 0017 Accepted: usare transcript completi con parlato NPC. I vecchi tagli a 300 caratteri non sono la baseline corrente.
- I test eval che simulano summary duplicati su 5 turni riproducono un percorso possibile, non dimostrano che il writer venga raggiunto dalla produzione normale.
- Il vecchio harness può iniettare recall authored e non certifica la qualità del retrieval reale.

## 3. Modello dei tre livelli

### Parametri

- **R**: minimo di turni completi da mantenere integralmente.
- **B**: numero di turni completi in un batch di compattazione.
- **K**: numero di summary intermedi normalmente presenti.
- **H**: tolleranza di arretrato espressa in batch aggiuntivi.

R, B e K restano **knob distinti**. Nessun default è stato scelto: prima si misurano le dimensioni, poi l'owner sceglie la matrice dell'eval.

Si contano turni realmente completati della storia attiva, non differenze aritmetiche di `turn_number`: un tentativo fallito può lasciare buchi nei numeri.

### Raw → intermedio

1. Con meno di R+B turni raw non serve compattare.
2. Quando si raggiungono R+B, il batch è costituito dai B più vecchi, identificati stabilmente e persistiti come input del lavoro.
3. Il job genera summary e fatti dal batch completo.
4. Finché manca un risultato valido e salvato, quei turni restano disponibili come raw.
5. Dopo pubblicazione atomica del batch, il suo summary sostituisce quei raw nel prompt; i fatti sono persistiti e accodati per embedding.

In condizioni normali i raw oscillano da R a R+B−1; durante il lavoro possono essere di più, entro la tolleranza. Le trascrizioni **non vengono cancellate dal DB** quando escono dal prompt.

### Intermedio → globale

1. I summary intermedi sono dettagliati, senza replicare la stessa stringa sulle righe Turn.
2. Quando il livello deve superare K, il batch più vecchio è candidato ad entrare nel globale.
3. Input: **globale precedente + trascrizioni originali di quel batch**, con le fonti strutturate pertinenti disponibili; non si usa il suo summary come unica fonte.
4. Output: un nuovo globale completo e consolidato, generato dal modello.
5. Ogni checkpoint valido è immutabile; l'attivazione avanza un puntatore soltanto dopo validazione e persistenza.
6. Il batch esce dal livello intermedio soltanto quando è incorporato nel checkpoint pubblicato.

Il globale avanza **un batch alla volta**. B determina anche la quantità nuova incorporata: non introdurre una seconda dimensione indipendente dei segmenti globali.

### Copertura

- Globale remoto, batch intermedi e raw descrivono segmenti temporali disgiunti della storia attiva, senza buchi di copertura dovuti allo scheduling.
- La copertura non promette conservazione testuale di ogni dettaglio: quella è una proprietà di qualità da misurare.
- Il globale conosce solo il passato che ha incorporato. Una promessa ancora aperta nel remoto può essere già stata risolta nei raw; non reinterpretare il globale come stato corrente autorevole.
- Le membership esplicite dei batch e i checkpoint sono la fonte della verità, non prefissi testuali `[Turns x-y]` o deduplica di stringhe.
- Non introdurre capitoli, saghe o ulteriori livelli gerarchici.

### Esempio soltanto illustrativo

Con R=12, B=8, K=4: dopo 20 turni completi si può compattare 1–8, mantenendo 9–20 raw. A 44 turni: quattro batch intermedi 1–32 e raw 33–44. A 52: il batch 1–8 può entrare nel primo globale, gli intermedi coprono 9–40, i raw 41–52. Questi numeri NON sono default approvati e presuppongono turni consecutivi e job completati.

## 4. Soglie, attese e durevolezza

### Rimozione del vecchio cap

Eliminare `gameplay.context_token_cap` e il taglio automatico di coppie raw. La dimensione è governata dalle regole dei livelli e dall'arretrato ammesso, non da un taglio silenzioso a 12.000 token stimati.

La finestra fisica del modello continua ad esistere. Un rifiuto per input troppo lungo deve essere riconoscibile; non reintrodurre tagli silenziosi o riduzioni arbitrarie dei batch. Dimensionare i knob anche rispetto ai modelli scelti nell'eval.

### Tolleranza

- Conservare le fonti mentre il sostituto è pendente, entro H batch aggiuntivi.
- Proteggere **entrambi** i livelli: raw in attesa della compattazione e intermedi in attesa del globale.
- Precisare in S0 formule ed edge case della cascata. Base proposta: R+B è la soglia di lavoro raw; K+1 è la soglia di lavoro globale; H indica margine ulteriore rispetto a tali soglie, senza aumenti illimitati quando si accumulano job.
- La coordinazione deve considerare i batch in volo che produrranno nuovi intermedi, non soltanto le righe già pubblicate.
- H e i parametri operativi numerici sono da confermare; non inventarli come decisioni dell'owner.

### Gating dei turni

- Un turno già completato viene salvato e restituito normalmente; non trasformarne la risposta in un errore di compattazione post-commit.
- Il controllo della capacità avviene **prima di accettare/numerare/generare il turno successivo**.
- Alla soglia: attesa se il lavoro è attivo, errore strutturato con retry esplicito se i tentativi sono esauriti.
- L'attesa deve essere finita e compatibile con i timeout del trasporto. A scadenza restituire uno stato temporaneo senza consumare il turno. Valore numerico da fissare prima di attivare il flusso.
- Il frontend mostra l'errore della memoria **solo quando blocca**. Nessun nuovo pannello diagnostico generale richiesto.
- Dopo il retry, una nuova richiesta non deve duplicare un turno già eseguito. Testare precisamente la distinzione fra richiesta non iniziata e turno committato.

### Job

- Job specifici per le transizioni della memoria, senza framework generico di workflow.
- Input immutabili e identificati: batch/membership, policy della campagna, checkpoint predecessore per il globale, versione del produttore/prompt.
- Stato, tentativi, claim/lease, esito e possibilità di pubblicazione persistiti.
- Retry automatici limitati e configurati per errori recuperabili/output non valido; il conteggio non riparte su un nuovo turno o al restart.
- Dopo esaurimento serve retry esplicito. Errori di credenziali/policy richiedono intervento, non un ciclo pagato indefinito.
- Il riavvio riprende lavoro interrotto senza dichiararlo riuscito e senza duplicare i risultati.
- Un risultato valido ma ormai non pubblicabile per un cambio di storia è distinto da errore LLM o output malformato; non va rigenerato automaticamente come se il modello avesse fallito.
- La pubblicazione dei risultati visibili e degli avanzamenti è atomica e idempotente. Non promettere exactly-once per le chiamate esterne: un crash dopo una risposta provider può richiedere un nuovo tentativo.
- Nessuna sessione DB o lock transazionale mantenuto durante chiamate LLM/embedding.
- Verificare in S0 anche sovrapposizione di richieste-turno, load e job: un risultato del DM iniziato prima di un restore non può sovrascrivere lo stato ripristinato.

## 5. Generazione: una chiamata contro due

### Decisione

Candidato principale: **una chiamata di batch** restituisce summary intermedio e fatti. L'owner rimane scettico: la scelta deve essere dimostrata nell'eval, non adottata per principio.

- Due file YAML specialistici separati: istruzioni summary e istruzioni fact extraction.
- Nel candidato unico vengono composti con un unico contratto di output, senza concatenare due richieste incompatibili di “restituisci soltanto…”.
- Confronto con due chiamate specializzate usando gli stessi materiali e istruzioni, con provenienza/modello/costo registrati.
- Non è richiesto consegnare due pipeline production configurabili: scegliere quella validata, mantenendo nell'eval il confronto necessario.
- Il globale rimane una generazione distinta alla propria transizione.
- Tutte sono chiamate semplici di generazione: niente tool, agenti o loop agentici.
- Usare il routing/configurazione personale già previsti da SAGA; nessuna chiamata diretta ad hoc a provider.

### Validità

- Il batch è completato **soltanto quando summary e fatti sono entrambi validi**.
- `facts: []` è un successo legittimo; output malformato, campi mancanti o riferimenti invalidi non lo sono.
- Non avanzare la copertura salvando solo la metà valida. Nella variante separata la pubblicazione finale rimane atomica.
- Il massimo di fatti viene comunicato al modello e validato; evitare il vecchio slicing silenzioso che perde elementi senza evidenza.
- Un globale non valido lascia attivo il checkpoint precedente.

## 6. Fonti: transcript e operazioni

Input dei batch: azioni player + narrazione finale completa, incluso parlato NPC, più esiti strutturati pertinenti delle operazioni.

### Registro delle operazioni

- Indipendente dalla visibilità UI dei tool.
- Identità stabile dell'operazione, turno sorgente, ordine nel turno, origine/operazione e outcome esplicito.
- Argomenti ed esito utili a distinguere tentativo, rifiuto e risultato.
- Delta **per operazione**, contenente soltanto campi modificati prima/dopo, inclusi inserimenti e rimozioni distinguibili dal valore null.
- Coprire world_state, character_data e quest, oltre ai percorsi NPC e di finalizzazione pertinenti.
- Un delta vuoto non significa fallimento: un attacco mancato o una verifica riuscita senza cambiamenti persistenti restano esiti validi.
- Non inviare snapshot completi pre/post per ogni tool.
- Escludere rumore di routine come il solo cambio mood o avanzamento clock; non perdere però viaggio/interruzioni e altre azioni importanti soltanto perché modificano anche il tempo.
- Per ora l'estrattore seleziona i fatti significativi tramite prompt. Filtri sofisticati per categoria sono eventuale seguito, guidato dall'eval.
- Dati ed eventi del turno sono persistiti atomicamente con il turno, non affidati a una seconda task volatile.
- I vecchi turni non hanno delta ricostruibili con certezza; non inventarli. Nell'eval distinguerli dai nuovi dati completi.

## 7. Contratti dei documenti e metadati

Le seguenti sono specifiche logiche. In S0 fissare nomi fisici, tipi e vincoli senza cambiare la semantica approvata. Nessun `any` o JSONB non validato ai confini.

### 7.1 Fatti

Fatti **storici immutabili**. Nessuna ricerca di fatti vecchi durante l'estrazione, nessun collegamento “fulfills/supersedes” e nessuno stato di verità aggiornabile in questo lavoro.

| Campo | Contratto |
|---|---|
| `content` | Testo autonomo e comprensibile fuori dal dialogo; conserva nomi e attribuzione. |
| `category` | Una categoria principale fra evento, informazione/indizio, impegno/accordo, relazione, cambiamento di stato. Usare valori tecnici stabili, per esempio `event`, `information`, `commitment`, `relationship`, `state_change`. Definizioni/esempi chiariscono i confini. |
| `assertion_type` | Distingue accadimento, dichiarazione, convinzione esplicitamente espressa e intenzione. Non trasforma discorso o credenza in verità del mondo. |
| `entities` | Più entità, con nome, tipo e ruolo descrittivo nel fatto. Riferimento canonico solo se verificato e non ambiguo. |
| `attribution` | Chi dichiara/crede/intende, quando pertinente, riferito alle entità del fatto. Non dedurre credenze nascoste dal nulla. |
| `source_turns` | Uno o più turni del batch realmente a supporto del fatto. Il modello cita riferimenti dell'input; il codice valida membership e li risolve agli ID immutabili. |
| `temporal_references` | Tempi dell'evento o scadenze espliciti nel materiale, conservati come testo; niente normalizzazione in date/calendario o inferenza arbitraria. Il momento dell'apprendimento può differire da quello dell'evento. |
| `importance.level` | Livello appartenente alla rubrica configurata della campagna. Inizialmente due: `ordinary`, `critical`. |
| `importance.reason` | Breve frase basata sulle fonti che motiva il livello, utile come metadato per debug/eval. |

Il codice assegna ID, campagna, batch/provenienza e metadati di generazione. Gli ID canonici non sono un'invenzione del modello; per le entità non risolte conservare nome/tipo/ruolo senza forzare un collegamento.

La risoluzione può usare ID realmente presenti negli esiti strutturati e i resolver esistenti; non aggiungere chiamate LLM o creare entità di mondo solo per normalizzare i fatti.

#### Importanza configurabile

- Il codice è agnostico rispetto al numero dei livelli, ma valida i valori ammessi.
- Una definizione unica in configurazione contiene livelli, criteri ed esempi ed alimenta sia prompt sia validazione.
- Non lasciare le etichette soltanto nel testo del prompt e non aggiungere un punteggio numerico nascosto.
- I livelli riguardano fatti già significativi: `ordinary` non autorizza microazioni decorative.
- L'owner ha scelto due livelli; un terzo si valuta solo se l'eval ne mostra il bisogno.
- Una modifica futura della rubrica non riclassifica automaticamente fatti già generati.

#### Quantità, lingua, embedding

- Nessun minimo obbligatorio di fatti.
- Massimo numerico **per batch** configurabile nel YAML; default da scegliere nell'eval.
- Testi, motivazioni e summary nella lingua della campagna; chiavi e valori tecnici stabili.
- Embedding del solo `content` per ora, come sorgente del retrieval esistente. Metadati memorizzati non vengono aggiunti automaticamente al testo embeddato.
- Questa scelta viene riaperta esplicitamente nel futuro branch retrieval.
- I fatti appena persistiti possono aspettare il worker embedding prima di essere ricercabili. Il completamento del batch non richiede che l'embedding sia già riuscito: la coda deve essere durevole e il summary già disponibile.

#### Esempio di semantica richiesta

- “Mira ha dichiarato che la chiave apre la cripta”: dichiarazione attribuita, non proprietà verificata della chiave.
- “Neris ha ricevuto la chiave”: evento storico, non “Neris la possiede tuttora”.
- “Neris ha promesso di restituirla”: promessa, non restituzione compiuta.
- Se il fatto è confermato da un esito del motore, il testo non deve contraddirlo.

### 7.2 Summary intermedio

Payload generato: `{ "text": "..." }`.

- **Resoconto dettagliato**, idealmente molto più ricco degli esempi brevi dell'intervista.
- Elimina ripetizioni e descrizioni inutili, preserva contenuto sostanziale, sequenza, dialoghi/accordi rilevanti e conseguenze.
- Non mantenere la richiesta attuale di 2–3 frasi come vincolo.
- Un documento per batch con identità e membership proprie; non una copia su ciascun Turn.
- Metadati a livello documento: ID, campagna/contesto storico, batch e turni effettivi, versione dello schema/produttore/prompt e provenienza della generazione.
- Nessuna citazione obbligatoria frase per frase.

### 7.3 Globale

Payload generato con **quattro campi fissi**:

```json
{
  "story_so_far": "...",
  "open_threads": [],
  "relationships": [],
  "resolved_threads": []
}
```

- `story_so_far`: percorso narrativo e conseguenze principali.
- `open_threads`: promesse, misteri, debiti e questioni aperte nella storia incorporata.
- `relationships`: rapporti, motivazioni ed eventi che li spiegano.
- `resolved_threads`: brevi tracce delle vicende concluse; non introduce un sistema di archi/quest. Il nome iniziale `closed_arcs` è stato sostituito per evitare quell'equivoco.
- Liste di stringhe; possono essere vuote. Nessuna entità o citazione per singola voce richiesta.
- Conservare le vicende concluse in forma molto breve, accorpandole quando necessario; non appendere indefinitamente ogni dettaglio.
- Obiettivo di lunghezza **indicativo e configurabile**, non taglio meccanico del testo. Valore da decidere nell'eval.
- Ogni generazione produce un documento consolidato completo, non una patch né un append deterministico.
- Metadati documentali: identità del checkpoint, campagna/storia, predecessore, nuovi batch incorporati, copertura cumulativa derivabile, versioni e provenienza.
- Conservare tutti i checkpoint validi; usare soltanto quello attivo nel prompt.

### 7.4 Separazione fra contenuto e gestione

Job, lease, tentativi, hash/versioni e timestamp operativi non devono gonfiare il contenuto narrativo. Memorizzarli dove servono alla gestione e alla verifica. Il modello non decide ID, campagna o copertura del documento.

## 8. Storia attiva, salvataggi e pubblicazione tardiva

### Comportamento deciso

- Caricare un vecchio save non elimina gli altri save o il loro futuro.
- Quando si gioca una nuova azione dopo il load, si crea una **nuova continuazione** della storia a partire da quel punto.
- Il save è un punto immutabile. Il prefisso comune può essere condiviso; non copiare l'intera campagna.
- Nessuna nuova UI di timeline richiesta.
- Turni, operazioni, batch, fatti, checkpoint e lavori devono avere identità/provenienza sufficienti a selezionare una storia senza mescolare le continuazioni.

### Schema da concretizzare in S0

Preferire una rappresentazione minima di continuazioni e head immutabili, con riferimenti espliciti dei save e un puntatore attivo sulla campagna. Non basarsi su `campaign_id + turn_number`.

La scelta fisica (parent link dei turni, segmenti/continuazioni e membership) va verificata con query e vincoli del DB. Non introdurre un framework generico di versionamento. La semantica sopra è già decisa: chiedere all'owner solo se una scelta tecnica la cambia materialmente.

### Vincoli indispensabili

1. Il prefisso condiviso è accessibile alle continuazioni che ne discendono; il futuro del ramo padre oltre il punto di fork non lo è.
2. Un batch che attraversa il punto di restore non è valido solo perché alcuni fatti citano turni precedenti: verificare la compatibilità dell'**intero input produttore** con la storia attiva.
3. Un vecchio job può al massimo pubblicare un artefatto nel proprio contesto valido; non può spostare puntatori della storia attiva dopo un load.
4. La pubblicazione verifica un'identità/versione corrente del contesto di lavoro, non soltanto l'esistenza della campagna.
5. Anche i risultati del turno DM in volo al momento del load devono essere protetti da scritture tardive.
6. Gli embedding possono condividere l'indice versionato della campagna; la query deve filtrare le sorgenti compatibili con la storia selezionata, mantenendo anche i controlli di spazio/modello di ADR 0018.
7. Riprendere un save non deve diventare un modo involontario di azzerare i retry e rigenerare a pagamento all'infinito lo stesso lavoro fallito.
8. I save devono poter recuperare fonti e memoria coerenti anche quando, al salvataggio, una compattazione era ancora pendente. Definire in S0 il riuso degli artefatti completati e la ripresa del lavoro mancante.

## 9. Configurazione

- YAML come fonte dei default delle nuove campagne.
- **Snapshot per campagna** delle regole della memoria: R, B, K, tolleranza, rubrica importanza, massimo fatti, target globale e policy operative pertinenti.
- Cambiare il YAML non ricompatta o ripartiziona automaticamente una campagna già avviata.
- La configurazione strutturale della memoria non congela credenziali o policy di autorizzazione: provider e permessi vengono risolti secondo il contratto personale corrente di SAGA.
- Registrare modello/provider effettivi e versione prompt/produttore per ogni artefatto; non assumere che tutta una campagna usi sempre lo stesso modello.
- Consolidare/rimuovere le vecchie chiavi superate, incluse opzioni inerti, con documentazione coerente. Non aggiungere toggle legacy o modalità production speculative.
- I nomi definitivi del blocco YAML si fissano in S0 insieme allo schema validato; mantenere un'unica fonte per i default.

## 10. Export

Export della **campagna completa**, non soltanto del percorso attivo:

- continuazioni e prefissi condivisi, save e indicazione del percorso attivo;
- turni originali ed eventi strutturati;
- summary intermedi e tutti i checkpoint globali conservati;
- fatti completi con metadati, entità e fonti;
- policy della memoria e versioni necessarie a interpretare gli artefatti;
- stato diagnostico dei job: tipo, fonti, stato, tentativi ed errore sanitizzato, senza lease/lock o autorizzazioni operative.

Non esportare credenziali. Nessun endpoint import nuovo richiesto. Non introdurre come requisito una copia dei vettori provider-specific: le fonti e i riferimenti devono comunque essere completi.

Generare uno snapshot referenzialmente coerente, non letture indipendenti che possono mescolare prima/dopo di un job. Validare offline il documento e tutti i riferimenti; i job esportati non sono direttamente eseguibili.

## 11. Evaluation e decisioni numeriche ancora aperte

### Ordine obbligatorio

1. **Prima misure deterministiche**, senza chiamate a provider.
2. Poi chiedere all'owner combinazioni di parametri, modelli e budget/run da provare.
3. Preparare input, rubriche e controlli offline.
4. Ottenere autorizzazione esplicita per ciascun run live secondo `backend/eval/README.md`.
5. Esaminare qualità e costi con l'owner prima di fissare default e variante production.

### Misure iniziali

- Usare i circa dieci turni reali indicati dall'owner, se ancora presenti, e il prompt realmente assemblato, includendo definizioni tool e sezioni di stato.
- Verificare disponibilità dei dati prima di qualsiasi reset del DB di test.
- L'owner stima circa 8k token fissi più turni e usa modelli con finestre ampie; trattare questi numeri come ipotesi da misurare, non come un limite approvato.
- Distinguere tokenizzazione effettiva, stime e proiezioni. Non presentare caratteri/4 come misura esatta per ogni modello.
- Confrontare il peso previsto di R/B/K; mostrare anche crescita transitoria fino alla tolleranza e peso dei risultati tool per i job di memoria.
- Dieci turni reali non permettono da soli di misurare la qualità di un globale dopo molte riscritture. Non spacciare ripetizione di testo o estrapolazione per una lunga campagna reale.

### Materiale da concordare

La domanda sul dataset dell'eval è rimasta senza risposta. Ci sono tre risorse possibili: turni reali disponibili, scenario lungo controllato/annotato, nuova campagna di prova con eventi completi. **Chiedere quali usare** al gate dell'eval.

**S0 note (2026-11-09, decisione owner).** Questo era il gate aperto nell'handoff: scelti turni reali + scenario lungo controllato (§21), non una nuova campagna. Matrice R/B/K rinviata esplicitamente a S3; nessuna chiamata live autorizzata.

Il vecchio `gold` è segnalato nel TODO come contaminato/non derivato; non assumerlo come oracle valido né rigenerarlo senza autorizzazione. Controllare lo stato effettivo del fixture.

### Confronti e criteri

- Chiamata unica summary+facts contro due chiamate specializzate, sugli stessi batch.
- Qualità del summary e dei fatti valutata separatamente: un summary buono non compensa fatti falsi o mancanti.
- Fedeltà: nessuna intenzione trasformata in azione riuscita; dichiarazioni/credenze attribuite; rispetto degli esiti del motore.
- Provenienza: riferimenti validi e realmente a supporto, non soltanto numeri appartenenti al batch.
- Fatti: dettagli precisi, accordi, relazioni, cambiamenti significativi; rumore, duplicazioni e rilevanza delle due classi di importanza.
- Intermedio: conservazione del contenuto sostanziale, senza regressione verso riassunti di poche frasi.
- Globale: **più aggiornamenti consecutivi**, fili aperti vecchi, risoluzioni tardive, rapporti e compressione delle vicende concluse.
- Confrontare dimensione effettiva, costo, latenza, errori di formato e retry; una sola chiamata non implica automaticamente minore latenza.
- Controlli deterministici e revisione umana degli output. Un modello giudice non è stato scelto e non va aggiunto automaticamente.
- Il successo del nuovo sistema non va inferito dalle sole probe che ricevono recall authored.

### Gate da porre all'owner durante S0/S3

- Quali dati/campagne usare e quale scenario lungo preparare?
- Quali combinazioni R/B/K provare dopo la stima?
- Quali modelli, ripetizioni e budget per il singolo run autorizzato?
- Massimo fatti per batch e obiettivo indicativo di lunghezza globale?
- Valori di H, tentativi/backoff e durata massima dell'attesa, coerenti con i timeout reali?
- Quali risultati rendono accettabile la chiamata unica? Esaminare gli output, senza inventare soglie di qualità già approvate.

## 12. Verifiche deterministiche e DB

TDD per il comportamento nuovo, con PostgreSQL reale per persistenza/core flow. Le chiamate provider nei test possono essere controllate; non sostituire con mock il DB o il produttore dei dati che si intende verificare.

Checklist minima:

1. Turno creato dal vero percorso API → input batch effettivamente eleggibile → summary letto nel contesto: regressione del writer oggi irraggiungibile.
2. Membership di batch completi, con buchi nei numeri dei turni e confini R/B/K.
3. Nessun buco/overlap fra copertura globale, intermedia e raw in ogni transizione, inclusi job lenti e restart.
4. `facts: []` valido distinto da parsing, schema o riferimenti invalidi; copertura non avanza su output parziale.
5. Retry persistenti, lease scaduta, concorrenza tra worker, duplicazione di wake-up e completamenti fuori ordine.
6. Pubblicazione atomica di summary/fatti/enqueue embedding e cursore; rollback coordinato.
7. Globale aggiornato dal predecessore corretto e dal batch originale esatto, una sola volta nella catena attiva.
8. Tolleranza raw e intermedia/cascata: nessuna crescita oltre il contratto, nessun turno consumato durante il blocco.
9. Esiti per operazione: successo senza delta, rifiuto, errore, modifica NPC/quest, cambiamenti intermedi che si annullano a fine turno.
10. Restore a metà di una zona prima compattata; save successivi ancora caricabili; due continuazioni con numeri turno uguali ma fonti distinte.
11. Completamento tardivo di job e di turno dopo load: nessuna contaminazione o sovrascrittura del percorso attivo.
12. Recall di un fatto del futuro/di un altro ramo impossibile; fatti del prefisso condiviso validamente prodotti ancora disponibili.
13. Export completo durante attività concorrente, senza riferimenti orfani o claim eseguibili; validazione offline del formato.
14. Migrazione da DB vuoto lungo la vera catena Alembic; schema corrente corretto senza modifica delle migrazioni già pubblicate.
15. Frontend: attesa, errore bloccante, retry, ripresa senza doppia submission del turno.

Non eseguire un secondo full iniziale: baseline owner già verde. Durante implementazione usare check appropriati e `saga_check`; integrare i test DB mirati se il comando non li comprende. Prima del merge finale/sessione conclusa: full di entrambi gli stack, inclusi mypy, knip e soglie coverage, più integrazioni pertinenti.

## 13. Procedura Git e branch operativi

### ADR e rapporto con il piano

Questo lavoro architetturale è registrato nell'ADR **0020**, numero verificato libero in S0. Su richiesta dell'owner, il piano è stato copiato in `docs/adr/0020-batched-memory-and-history-checkpoints.md` e viene adattato soltanto qui; l'indice viene aggiornato nello stesso commit.

Il nuovo ADR documenta anche il cambio rispetto alle sorgenti embedding di ADR 0018 e il rapporto con il futuro recall di ADR 0002. Gli ADR Accepted non si modificano. Durante implementazione aggiungere note datate al nuovo ADR Proposed quando il codice impone una correzione; un nuovo bivio di prodotto torna all'owner.

Seguire la skill `adr-implement` per l'esecuzione. L'intervista già svolta non è motivo per saltare la verifica tecnica pre-code; le decisioni numeriche riservate all'eval non vengono chiuse inventando default.

### Topologia proposta

```text
main
└── adr/0020-memory-production                 integrazione; una PR finale
    ├── adr/0020-s0-contracts-and-budget
    ├── adr/0020-s1-history-and-schema
    ├── adr/0020-s2-operation-sources
    ├── adr/0020-s3-producers-and-eval
    ├── adr/0020-s4a-durable-memory-jobs
    ├── adr/0020-s4b-turn-and-context-cutover
    ├── adr/0020-s5-restore-export-and-ui
    └── adr/0020-s6-validation-and-cutover
```

I branch operativi partono **in sequenza dalla punta aggiornata dell'integrazione**. Parallelizzare analisi o unità indipendenti, non creare anticipatamente branch che fingono già disponibili contratti non chiusi.

La divisione originale è in sette fasi operative, non sette commit complessivi; S0 ha suddiviso S4 in S4a/S4b con conferma owner (§22). Ogni fase contiene commit logici con i relativi test e changelog. Se una fase si rivela troppo larga, proporre una suddivisione coerente all'owner, mantenendo una sola PR finale.

### Checkout e worktree

Preferire un worktree aggiuntivo per il lavoro, mantenendo il checkout normale di `~/Desktop/saga` su main. Prima verificare branch/worktree esistenti e modifiche utente.

Esempio da eseguire soltanto in modalità implementazione, adeguando numero/nome se necessario:

```bash
git worktree add -b adr/0020-memory-production ../saga-memory-production main
```

Se il worktree diventa il luogo principale, spostare lì la sessione tramite lo strumento `session_move` del harness. Non trasformare mai il repository principale in bare.

Per ogni fase:

```bash
git switch -c adr/0020-sN-slug adr/0020-memory-production
# TDD, implementazione, verifiche, commit logici
git switch adr/0020-memory-production
git merge --no-ff adr/0020-sN-slug -m "chore(memory): merge sprint-N <titolo> (ADR 0020)"
```

La riga commentata descrive lavoro, non un invito ad eseguire comandi senza verifica. Usare i comandi essenziali del progetto, il runtime pinned e l'infrastruttura test reale.

**S0 note (2026-11-09, verifica del hook).** Il formato `merge: …` proposto nell'handoff è rifiutato dal hook Conventional Commits attivo. Usare `chore(memory): merge sprint-N … (ADR 0020)` senza bypass del hook; restano invariati `--no-ff`, topologia e singola PR finale.

### Commit e PR

- Conventional Commits con scope; per gli sprint suffisso `(ADR 0020 SN)`.
- Test e implementazione della stessa unità stanno insieme; non un mega-commit per l'intero sprint.
- Primo commit S0: ADR/index/CHANGELOG e **potatura della voce TODO harness già completata**.
- Aggiornare CHANGELOG nel commit del relativo cambiamento, rispettando il limite di una frase/~30 parole per bullet.
- Correzioni a una propria unità già committata: amend secondo la convenzione del repo, senza riscrivere lavoro utente.
- Nessun co-author trailer.
- Nessuna PR per sprint. PR finale dall'integrazione a main con merge commit, non squash.
- La PR finale chiude #79 e #80 se i relativi criteri sono verificati. Non riaprire automaticamente issue già chiuse.

## 14. Contenuto delle fasi

### S0 — Contratti, piano eseguibile e dimensioni

- Catchup mirato e conferma della baseline/diff, senza ripetere full iniziale.
- Nuovo ADR Proposed con tutte le decisioni sopra; indice e primo commit richiesto.
- Fissare schema logico/fisico minimo di storia, membership, checkpoint, fatti e job, con vincoli e query di appartenenza.
- Definire precisamente gating, H/cascata, salvataggio durante job pendente e fencing del turno in volo.
- Fissare payload tipizzati, vocabolari tecnici e rendering dei quattro campi globali; metadati separati dal contenuto generato.
- Inventario read-only dei dati reali prima di qualsiasi reset; prima stima deterministica di contesto/input. Nessuna chiamata live.
- Portare all'owner la matrice di esperimenti da scegliere; non bloccare il disegno su default inventati.
- Gate: nessun bivio di prodotto necessario all'implementazione lasciato implicito. Le scelte numeriche intenzionalmente riservate all'eval restano etichettate come tali.

### S1 — Storia, policy e schema persistente

- Migrazioni forward e modelli tipizzati per continuazioni/head/save, snapshot policy, batch/membership, documenti, provenienza fatti e job.
- Predisporre selezione della storia valida e vincoli contro duplicazioni/riferimenti orfani.
- Test DB su fork/prefissi, membership e rappresentazione dei checkpoint.
- Non implementare un'importazione/conversione della vecchia memoria.
- Le eventuali colonne transitorie richieste per mantenere verdi le fasi intermedie hanno un ritiro esplicito nel cutover, non diventano una modalità legacy permanente.

### S2 — Fonti delle operazioni

- Esiti strutturati e delta per operazione nei percorsi ordinari, NPC e finalizzazione pertinenti.
- Persistenza atomica con il turno e separazione dalla visibilità UI.
- Input canonico di batch con transcript completi e risultati significativi.
- Test attraverso handler reali, inclusi rifiuti e modifiche intermedie annullate.

### S3 — Produttori, prompt ed eval della qualità

- Due YAML specialistici e produttori persistence-free con schemi rigorosi.
- Globale strutturato, rubrica di importanza configurata, validazione fonti/entità/limiti.
- Harness che confronta unico/separato senza certificare forme di dati mai prodotte dal flusso reale.
- Misure offline complete e scelta owner di dataset, R/B/K, limiti, modelli e budget.
- Live run soltanto autorizzati. Revisione umana e scelta motivata della variante production/default.
- Se l'evidenza modifica un contratto, domanda all'owner e nota nell'ADR prima di propagare l'implementazione.

### S4 — Pipeline durevole e contesto

**S0 note (2026-11-09, sequenza confermata dall'owner).** Dividere in S4a/S4b e anticipare in S4b l'integrazione minima save/load e UI: attivare turni/memoria nuovi lasciando il vecchio restore a S5 renderebbe la fase non giocabile in sicurezza. Il dettaglio è in §22; l'elenco originale sotto resta il perimetro complessivo di S4.

- Scheduler/wake-up, job persistenti, claim, retry e pubblicazione atomica.
- Entrambe le transizioni con copertura esplicita e catena dei globali.
- Assemblatore a tre livelli, rimozione del taglio `context_token_cap`, tolleranza e gating prima del nuovo turno.
- Integrazione con coda embedding dei soli fatti; filtro di storia attiva nel recall attuale.
- Test restart, concorrenza, arretrato, nessun avanzamento su fallimento e percorso end-to-end API→memoria→prompt.

### S5 — Restore, export e UX del blocco

- Collegare API save/load al nuovo modello con continuazioni, altri save ancora caricabili e fencing di job/turni.
- Riattivazione coerente della memoria del save, senza mescolare output di batch che attraversano il fork.
- Export completo e referenzialmente consistente, diagnostica dei job senza claim runtime.
- UI minima di attesa/errore/retry quando la memoria blocca; evitare doppie submission.
- Test DB e frontend dei casi di ripristino/errore/export.

### S6 — Verifica integrata e ritiro definitivo

- Ritirare vecchio writer/reader summary, generazione euristica per-turno, percorsi embedding TURN, configurazione/test obsoleti e gli orfani creati dal refactor.
- Adeguare label save senza mantenere la sintesi legacy.
- Verificare eventuali percorsi rebuild/index interessati dalla rimozione delle sorgenti TURN, rispettando gli spazi dell'indice attivo.
- Eval longitudinale della pipeline effettivamente collegata, con nuova autorizzazione per ciascun run live; non limitarsi ai produttori isolati.
- Test cumulativi di restore tardivo, più continuazioni, backlog e checkpoint; evidenza leggibile per revisione owner.
- Full check entrambi gli stack e integrazioni pertinenti; docs/CHANGELOG/TODO riconciliati; stato ADR aggiornato secondo accettazione effettiva.
- Una sola PR finale, merge commit. Nessun merge verso main prima dei gate e della review.

## 15. Riferimento OpenCode /compact

L'owner ha chiesto di studiarlo per ispirare il globale. Analisi Luna e verifica diretta del prompt, senza clone o file nel repo.

- Documentazione V2: <https://opencode.ai/docs/compaction/>.
- Sorgente: `anomalyco/opencode`, branch `dev`, commit `fe0a88ce3faaee5ef562927911a370d090c2c33a`.
- File: <https://github.com/anomalyco/opencode/blob/fe0a88ce3faaee5ef562927911a370d090c2c33a/packages/core/src/session/compaction.ts>.
- `buildPrompt`, circa righe 206–244: checkpoint consolidato, aggiornamento delle questioni aperte/risolte, preservare le informazioni precedenti salvo contraddizioni/superamento espliciti.

Adattare il principio, non il template da coding agent o le soglie di OpenCode. In SAGA una dichiarazione nuova non supera automaticamente un fatto accertato: mantenere fonte e attribuzione. Le quattro sezioni RPG scelte dall'owner sono il contratto del globale.

La licenza consultata è MIT. Se si copia una porzione sostanziale del sorgente/prompt, rispettarne gli avvisi; non è necessario copiare il template per applicarne il principio.

## 16. Quando fermarsi e tornare all'owner

- Risultati dell'eval insufficienti a scegliere unico/separato o default: mostrare gli output, non decidere per ottimizzazione prematura.
- Necessità di cambiare semantica dei salvataggi, sacrificare fonti oltre la soglia, introdurre nuovi livelli o riconciliazione tra fatti.
- Proposta di migrazione della vecchia memoria, modifiche al ranking o altre estensioni fuori scope.
- Numeri/modelli/budget di un run live non autorizzati esplicitamente.
- Impossibilità di rispettare i confini dei batch o l'isolamento delle storie con lo schema proposto: correggere il design prima del codice, non mascherare con euristiche.

Per altri dettagli implementativi scegliere la soluzione più semplice compatibile con queste decisioni, verificandola con codice reale e test significativi. Questo ADR deve permettere alla prossima sessione di lavorare senza ricostruire l'intera intervista.

## 17. Deciso e aperto — indice rapido

| Area | Stato | Gate / riferimento |
|---|---|---|
| Tre livelli, batch completi, fonti mai cancellate e copertura disgiunta | Decided | §3 |
| R/B/K distinti, H aggiuntivo, niente taglio silenzioso del contesto | Decided; formule Refined (S0) | §3–4, §20.3 |
| Job persistenti, retry limitati, pubblicazione atomica e fencing | Decided; contratti Refined (S0) | §4, §8, §20.4–20.5 |
| Confronto una/due chiamate, non due pipeline production configurabili | Decided; vincitore aperto | §5, §11, gate S3 |
| Transcript completo, esiti e delta per operazione | Decided | §6 |
| Fatti storici immutabili, metadati, due livelli di importanza configurati | Decided | §7 |
| Globale consolidato, quattro campi, un batch originale alla volta | Decided | §3, §7.3 |
| Save immutabili, nuove continuazioni, prefissi condivisi e isolamento del futuro | Decided; schema/query Refined (S0) | §8, §20.1–20.2 |
| Policy della memoria per campagna, autorizzazioni e credenziali correnti | Decided | §9, ADR 0018 |
| Export completo/coerente, niente nuovo import o requisito vettori | Decided | §10 |
| Dataset reale + scenario lungo controllato | Decided in S0 | §21; preparazione in S3 |
| Matrice R/B/K, H e limiti operativi | TODO / gate owner | Matrice rinviata a S3; valori §11 prima dell'attivazione |
| Massimo fatti e target globale | TODO / gate owner | Eval S3 |
| Modelli, ripetizioni, budget e autorizzazione di ogni singolo run | TODO / gate owner | §11, `backend/eval/README.md` |
| Ranking/query retrieval, riconciliazione fatti e indicizzazione summary | Fuori scope | §1 |

## 18. Relazione con gli altri ADR

- **0001 (Accepted)**: preservare sessioni brevi e nessuna sessione/lock durante LLM o embedding; integrare il fencing senza basarsi sulla continuità dei numeri turno.
- **0002 (Proposed)**: non implementare ranking, query arricchita o grafo; la nuova provenienza sostituisce le premesse per-turno di R2/R4/G3, da riconciliare nel futuro lavoro retrieval.
- **0017 (Accepted)**: le fonti sono le trascrizioni finali complete, con parlato NPC attribuito; non reintrodurre tagli a 300 caratteri o una seconda iniezione dei dialoghi.
- **0018 (Accepted)**: questo ADR sostituisce soltanto il contratto B6 delle sorgenti `Turn.summary`: i nuovi job accodano i fatti, non i summary TURN; identità degli spazi, indice versionato, configurazione personale e consensi rimangono invariati.
- **0019 (Accepted)**: preservare il registro quest canonico e la vera catena Alembic; non assumere ancora `create_all` come produttore delle suite DB e non modificare revisioni già pubblicate.

Nessun ADR Accepted viene modificato. Il ritiro delle sorgenti TURN e l'isolamento della storia sono documentati qui, non applicati retroattivamente al testo di 0018.

## 19. Alternative rifiutate e conseguenze

### Alternative già escluse nell'intervista

- Due patch isolate ai vecchi bug invece del rifacimento: non correggono copertura, scheduling, restore e provenienza.
- Summary duplicato su ogni turno, deduplica testuale o prefissi numerici come identità: non rappresentano membership e copertura verificabili.
- Taglio silenzioso dei raw, batch ridotti arbitrariamente o fonti eliminate prima del sostituto: nascondono buchi di memoria.
- Globale costruito dal solo summary intermedio, append deterministico, ulteriori livelli o dimensione globale indipendente da B: cambiano le fonti o la gerarchia concordate.
- Fatti di stato aggiornabili, ricerca/riconciliazione dei vecchi fatti o normalizzazione con nuove chiamate LLM: appartengono a un eventuale lavoro successivo.
- Due pipeline production configurabili, tool o loop agentici per i produttori: il confronto appartiene all'eval, la production consegna la variante validata.
- Cancellare il futuro al restore, copiare tutta la campagna o identificare la storia con il numero turno: perdono save o mescolano continuazioni.
- Backfill della memoria precedente, nuovo import, nuovo ranking o pannello diagnostico generale: fuori dal confine concordato.

### Conseguenze

**Positive**: copertura esplicita e recuperabile, fatti con provenienza controllabile, save coerenti, export completo e confronto empirico dei produttori prima della scelta production.

**Trade-off / rischi**: più schema persistente e coordinazione; costo dei transcript originali nelle generazioni globali; crescita dello storage perché fonti/checkpoint si conservano; qualità non garantita dalla sola copertura; possibili chiamate ripetute dopo crash, ma mai doppia pubblicazione.

Il rispetto della finestra fisica del modello richiede misure e scelte R/B/K/H adeguate: la rimozione del vecchio cap non è una promessa di input illimitati.

## 20. S0 — contratti tecnici (2026-11-09, pre-code)

Questa sezione concretizza l'intervista, senza implementare modelli o migrazioni. Le query e il modello delle soglie vengono verificati separatamente; la verifica dello schema migrato e dei flussi reali appartiene a S1–S6. Non confondere una verifica del modello con una pipeline già collegata.

### 20.1 Storia: continuazioni e turni come head immutabili

**Refined (S0).** Usare il turno completato stesso come head della storia, con un parent link; non aggiungere una seconda tabella di head che duplichi l'identità del turno. Il prefisso vuoto è `head_turn_id = null`.

| Oggetto fisico | Campi / vincoli essenziali |
|---|---|
| `history_continuations` | UUID, campagna, continuazione padre e `fork_head_turn_id` nullable; radice senza padre/fork, nuova continuazione creata soltanto alla prima azione accettata dopo un load. |
| `turns` | UUID esistente, `continuation_id`, `parent_turn_id`, `history_depth`; identità, azione, transcript ed eventi immutabili dopo commit. `turn_number` resta etichetta, non identità o conteggio. |
| `campaigns` | `active_continuation_id`, `active_head_turn_id`, `active_memory_state_id`, `context_epoch`, `active_action_request_id`, `fork_on_next_action`; puntatori modificati in transazioni brevi sulla riga campagna. |
| `saves` | Stato mondo/personaggio/quest già esistente più continuazione, head, policy e due cursori della memoria (§20.2); riferimenti congelati, non puntatori a contenuto sovrascrivibile. |
| `memory_policies` | UUID, campagna, versione schema, payload tipizzato e hash; uno snapshot immutabile delle regole alla creazione della campagna. |

Tutti i riferimenti incrociati usano FK composite con `campaign_id`, sostenute da unique key sui destinatari; una UUID esistente in un'altra campagna non è un riferimento valido. Indici sui parent link e sulle FK di appartenenza. La continuazione è provenienza del segmento, non il filtro esclusivo dei turni: i discendenti leggono anche i parent.

`history_depth` conta nodi completati del prefisso, non numeri visualizzati. Una radice ha profondità 1; un figlio ha profondità del padre +1. Il vincolo può essere espresso con FK a `(parent_turn_id, campaign_id, parent_depth)` e `parent_depth` generato da `history_depth - 1`, più check radice/parent: non basta un CHECK che tenti di leggere un'altra riga. Parent e profondità non vengono aggiornati dopo l'inserimento.

Il load ripristina head e stato del save, incrementa `context_epoch`, invalida la richiesta DM in volo e prepara `fork_on_next_action`. Non crea turni o una nuova continuazione da solo. La prima azione realmente ammessa crea il segmento figlio nel proprio claim; i turni successivi estendono quel segmento. Gli altri save e i loro futuri restano intatti.

La query di riferimento è un recursive CTE dal `head_turn_id` selezionato ai suoi parent, ordinabile per `history_depth`. Raw, journal/storia visualizzata, membership e recall devono leggere questo stesso percorso, non `campaign_id + turn_number`. L'export conserva invece tutte le continuazioni e tutti i turni.

### 20.2 Batch, documenti e due cursori della copertura

| Oggetto fisico | Campi / vincoli essenziali |
|---|---|
| `memory_batches` | UUID, campagna/policy, `previous_batch_id`, head finale delle fonti, hash del manifest; membership congelata di esattamente B turni contigui della storia selezionata. |
| `memory_batch_turns` | Campagna, batch, `ordinal`, turno; unique `(batch_id, ordinal)` e `(batch_id, turn_id)`, FK composite. Uno stesso turno può appartenere a batch diversi di continuazioni differenti. |
| `memory_summaries` | Un documento immutabile per batch, payload `{text}`, riferimento alla generazione. Nessuna copia su Turn. |
| `memory_facts` | UUID, campagna/batch, ordinale nel risultato, `content`, categoria/assertion e metadati tipizzati; unique `(batch_id, ordinal)`. Solo `content` alimenta l'embedding. |
| `memory_fact_sources` | Fatto, batch, campagna, turno; FK al fatto e alla membership `(batch_id, turn_id)`, così la citazione non può uscire dal batch. |
| `memory_global_checkpoints` | UUID, campagna/policy, predecessore nullable, batch incorporato, payload a quattro campi, generazione; checkpoint immutabili, unicità della transizione anche per il predecessore null. |
| `memory_states` | UUID del contesto di lavoro, campagna/policy, epoca, `global_checkpoint_id`, `last_compacted_batch_id`, revisione; nessun contenuto narrativo duplicato. |

La catena `previous_batch_id` rappresenta una partizione ordinata del prefisso. Il primo membro di un batch segue l'ultimo del predecessore; il primo batch comincia alla radice. Cardinalità B, ordinali, continuità parent/depth e immutabilità delle membership vanno garantiti anche alla frontiera DB, con validazione differita a fine transazione quando servono controlli su più righe. La sola validazione del JSON non garantisce questa proprietà.

I due cursori bastano a derivare i livelli:

1. Il checkpoint attivo copre cumulativamente la catena fino al suo ultimo batch incorporato.
2. I batch successivi, fino a `last_compacted_batch_id`, sono gli intermedi attivi.
3. I nodi del percorso dopo tale prefisso sono raw; finché un batch non è pubblicato rimangono raw anche se riservati da un job.

La transizione raw avanza soltanto `last_compacted_batch_id`; la transizione globale incorpora il primo intermedio, dal predecessore globale corrente, e avanza soltanto `global_checkpoint_id`. Checkpoint e ultimo batch devono appartenere alla stessa catena. Non servono liste duplicate di summary sulle righe Turn o un framework generale di versionamento.

**Compatibilità di un artefatto.** Nessun membro dell'intero input produttore può essere fuori dall'ancestry selezionata; per un globale devono essere compatibili anche il predecessore e tutta la sua copertura. Il batch 1–8 non è utilizzabile dopo restore al turno 5, nemmeno per un suo fatto che cita soltanto il turno 2. Un batch 1–4 interamente condiviso può invece fornire fatti a entrambi i discendenti.

**Compatibilità non equivale ad attivazione.** Un documento prodotto più tardi ma con fonti tutte nel prefisso del save è riusabile senza nuova generazione; non autorizza a compattare troppo presto. Con N nodi al restore, al massimo `floor(max(N-R, 0) / B)` batch possono sostituire raw e al massimo `max(floor(max(N-R, 0) / B) - K, 0)` possono essere incorporati nel globale. La memoria può essere indietro rispetto a tali limiti, non oltre. Questo preserva i raw protetti e il dettaglio degli intermedi anche riusando artefatti completati dopo il save.

Il save congela head e cursori allora pubblicati, non attende job pendenti. Il load crea un nuovo stato di lavoro dai riferimenti congelati e riconcilia gli artefatti già riusciti, nei limiti sopra. Per il lavoro mancante riusa l'identità logica dei job; non copia batch, fatti o retry budget. Se un batch attraversava il fork, la nuova membership è un input diverso, non un retry del vecchio lavoro.

Il limite si calcola sul head e sulla policy **del save**, non sulla campagna futura; i cursori congelati di un save valido lo rispettano già. Posto `g` il numero di batch globali, per uno stato raggiungibile dopo la fase iniziale vale `N=(g+i)*B+r` e quindi `floor((N-R)/B)=g+i+d(r)`. Il trigger globale `i+d(r)>K` consente il prossimo avanzamento senza superare il limite. Un job successivo non modifica questi riferimenti immutabili del save. Un riferimento incompatibile è un errore di integrità, non un invito ad arretrare silenziosamente un checkpoint valido.

### 20.3 Capacità, H e cascata

**Decisione owner S0 (2026-11-09).** Raggiunto il tetto di uno dei due livelli si fermano tutte le nuove azioni, anche se un altro raw non produrrebbe immediatamente un intermedio aggiuntivo. Rifiutata l'ammissione più permissiva «purché non peggiori il livello pieno»: il tetto è un punto di attesa, non soltanto un vincolo sul prossimo incremento. Nessun valore numerico di H è stato scelto.

Definizioni sul percorso attivo, usando nodi completati:

- `r`: raw non ancora sostituiti da documenti pubblicati; include le fonti di job raw in volo.
- `i`: intermedi pubblicati non ancora incorporati nel checkpoint attivo; include quello di un job globale in volo.
- `d(r) = floor(max(r-R, 0) / B)`: batch raw completi destinati a diventare intermedi, già riservati **o ancora da riservare**.
- `q = i + d(r)`: pressione intermedia proiettata. Contare solo i job già claimati lascerebbe una finestra di sovra-ammissione.
- `raw_ceiling = R + B + H*B`; `intermediate_ceiling = K + 1 + H`.

Il lavoro raw è eleggibile a `r >= R+B`. Il globale è eleggibile a `q > K` e quando esiste un intermedio pubblicato da incorporare; può preparare spazio prima che pubblichi il raw in volo. Una sola transizione raw e una sola globale alla volta per lo stato attivo: possono lavorare insieme su fonti disgiunte, non riservare due volte lo stesso segmento.

L'ammissione richiede **entrambe** le disuguaglianze strette correnti `r < raw_ceiling` e `q < intermediate_ceiling`. Nella stessa transazione si verifica anche la proiezione inclusiva `r+1 <= raw_ceiling` e `i+d(r+1) <= intermediate_ceiling`, si riserva lo slot di azione e si assegna il numero. Si può quindi arrivare al tetto; è l'azione successiva a fermarsi. Una richiesta non ammessa non consuma numero o turno. L'unico slot DM evita due ammissioni concorrenti basate sullo stesso margine.

Pubblicare un batch raw cambia `(r, i)` in `(r-B, i+1)`, lasciando q invariato; pubblicare un globale cambia `(r, i)` in `(r, i-1)`, riducendo q di uno. Non sommare di nuovo le B fonti dei job raw né l'intermedio riservato dal globale: sono già in r e i. Questo limita la cascata anche se il worker non ha ancora riservato tutto l'arretrato.

Con H=0 si può arrivare alla soglia di lavoro, poi si attende il sostituto prima di proseguire. La condizione iniziale N<R non crea debito; B è positivo e R/K/H sono conteggi interi non negativi. Questa definizione del dominio non sceglie valori zero né altri default: i valori da provare e quelli production restano al gate owner.

L'attesa avviene fuori da transazioni/lock; ogni risveglio ripete controllo e claim atomici. A scadenza: errore temporaneo strutturato `memory_busy`, senza accettare l'azione. Se il lavoro necessario è esaurito o bloccato da policy/credenziali: `memory_retry_required` o `memory_configuration_required`, con azione esplicita pertinente. Un turno già committato non può fallire retroattivamente per questa attesa.

### 20.4 Turni concorrenti e idempotenza dell'invio

**Decisione owner S0 (2026-11-09).** Un retry dello stesso invio ancora in corso riceve subito uno stato strutturato «in corso», senza una seconda generazione e senza polling automatico aggiunto. Rifiutato l'aggancio della richiesta duplicata alla stessa attesa HTTP: aumenta la coordinazione senza essere necessario alla UX minima.

Il client crea un `request_id` UUID per l'azione logica e lo conserva durante attese, errori di rete e retry; una nuova azione volontaria usa un nuovo ID. Il contratto action porta anche head/epoca attesi, così un load mentre si attende capacità non trasforma silenziosamente una vecchia intenzione in un'azione sulla storia ripristinata.

`turn_requests` è una tabella specifica dell'endpoint action: campagna, request ID, hash del payload, head/epoca di partenza, stato, token di esecuzione/scadenza, turno risultato ed errore sanitizzato. Unique `(campaign_id, request_id)` e un solo slot attivo per campagna. Non è una coda generale di azioni.

1. Nel claim breve: verificare ID/payload e contesto, capacità, slot libero; poi assegnare numero e token. Due invii nuovi concorrenti non eseguono due grafi dallo stesso stato.
2. LLM e graph fuori da sessioni/lock. Il graph legge lo snapshot di mondo, quest, storia e memoria catturato per il claim, non ricarica un mondo eventualmente ripristinato dopo il claim.
3. Nel commit breve: verificare insieme request ID/token, epoca e head di partenza; pubblicare stato, turno, eventi, nuovo head, auto-save e completamento della richiesta nella stessa transazione.
4. Un retry già committato recupera il risultato, senza graph. Se il contesto attivo è cambiato nel frattempo, risponde come risultato storico/non applicabile, con riferimento al turno e richiesta di riallineamento: non riapplica alla UI il vecchio snapshot come stato corrente.
5. Stesso ID con payload differente: conflitto. Richiesta ancora attiva: `action_in_progress`; cambio di storia: `action_context_changed`. Nessuna nuova numerazione per questi casi.
6. Il load, sotto la stessa serializzazione breve, incrementa epoca e invalida il token precedente. Il risultato DM tardivo non scrive nemmeno se il numero visualizzato coincide.

Il crash di una richiesta accettata ma non committata lascia un tentativo interrotto, non un turno completato. Il recupero rilascia soltanto slot scaduti/invalidati con fencing del vecchio token; nessuna rigenerazione a pagamento automatica al restart. La scadenza di esecuzione e i timeout devono essere finiti e concordati prima dell'attivazione. Un numero già claimato può restare un buco, come in ADR 0001.

### 20.5 Job, tentativi e pubblicazione

`memory_jobs` contiene UUID, campagna, tipo `batch`/`global`, batch, policy, predecessore globale quando pertinente, manifest/versioni/hash delle fonti e delle istruzioni, stato, tentativi persistenti, prossimo tentativo, token/scadenza del claim ed errore sanitizzato. Il manifest congela lingua, riferimenti e versioni del produttore: il restart non applica di nascosto prompt nuovi a un lavoro vecchio.

La chiave logica unica comprende input ordinato, policy, versione produttore/prompt e predecessore per il globale. **Non** comprende epoca di load, numero del turno corrente o wake-up: restore e restart non producono budget nuovi per lo stesso lavoro. Registrare separatamente i tentativi/provider call e la loro provenienza; la variante a due chiamate può avere due provenienze senza alterare l'atomicità del batch.

Stati minimi: `queued`, `running`, `retry_wait`, `blocked`, `exhausted`, `succeeded`. Un risultato valido dopo cambio di storia è `succeeded` con attivazione `detached`, non errore LLM né motivo di rigenerazione. Un riuso successivo attiva artefatti validi senza una nuova chiamata. Output parziale rimane candidato non visibile, non un avanzamento della copertura.

Il worker riserva un tentativo prima della chiamata, con token e lease basati sul clock DB; gli esiti incerti dopo crash contano come tentativi, non scompaiono. Non sommare retry SDK invisibili ai retry persistenti: budget e tentativi esterni devono restare tracciabili. Credenziali e policy si rivalidano al momento della chiamata secondo 0018. Nessuna credenziale vive nel manifest.

La lease supera il tempo massimo del tentativo, comprendendo tutte le chiamate eventualmente necessarie e il margine di pubblicazione; i valori non sono ancora fissati. Claim scaduti possono essere recuperati senza attribuire successo al vecchio worker. Il commit richiede ancora token/lease validi, altrimenti non pubblica.

Pubblicazione in una transazione, lock campagna prima delle altre righe per comporsi con `enqueue_source_embedding`:

- Per il batch: documento summary, fatti/fonti/metadati, enqueue embedding dei fatti e avanzamento del cursore raw insieme.
- Per il globale: checkpoint consolidato e avanzamento del puntatore insieme; predecessore atteso e primo intermedio devono coincidere.
- Per il contesto attivo: epoca/stato di lavoro ancora correnti, intero input nell'ancestry e cursore pertinente ancora atteso. La revisione serializza gli aggiornamenti, ma un avanzamento dell'altro livello non richiede una nuova generazione.

**Non richiedere uguaglianza fra head corrente e head al momento dello scheduling dei job.** Turni normali possono estendere la stessa storia mentre il modello lavora: bastano epoca invariata, ancestry compatibile e cursori corretti. L'uguaglianza esatta del head è invece necessaria al writeback DM. Dopo un load, un job precedente può conservare atomicamente artefatti nel contesto originario, ma non avanzare i puntatori attivi; la riconciliazione del nuovo contesto decide il riuso.

Il retry esplicito dopo esaurimento autorizza un nuovo ciclo limitato, registrato; il totale storico dei tentativi non viene azzerato. Aprire una campagna, inviare un turno o caricare un save non equivale a tale autorizzazione.

**S1 note (2026-11-09, implementation).** The `saga_memory_job_sources` trigger is a PostgreSQL
constraint trigger declared `AFTER INSERT`; its return value (`NEW` / `NULL`) is ignored by the
executor, so the effective enforcement is the `RAISE EXCEPTION` on manifest mismatch. No contract
divergence from §20.1–20.5; `MemoryProductionPolicy` remains without YAML defaults as intended by
§20.8.

### 20.6 Payload generati e metadati

Tutti i payload hanno modelli Pydantic rigorosi (`extra="forbid"`, tipi stretti e limiti da policy), con schema condiviso da prompt e validazione; le controparti API/export hanno schemi runtime equivalenti. Nessun campo generico `any`; i contenitori JSON usano valori JSON ricorsivi validati e contratti specifici dove la forma è nota.

| Payload | Forma / validazione |
|---|---|
| Summary | `{"text": non_empty_string}`; documento dettagliato, nessun limite fisso di 2–3 frasi. |
| Batch unico | `{"summary": SummaryPayload, "facts": list[FactPayload]}`. |
| Fact extraction separata | `{"facts": list[FactPayload]}`; `[]` valido, lista assente o malformata no. |
| Globale | Esattamente `story_so_far: non_empty_string`, `open_threads: list[str]`, `relationships: list[str]`, `resolved_threads: list[str]`; elementi non vuoti, liste anche vuote. |

`FactPayload` contiene soltanto `content`, `category`, `assertion_type`, `entities`, `attribution`, `source_turns`, `temporal_references`, `importance`. Vocabolari tecnici:

- `category`: `event`, `information`, `commitment`, `relationship`, `state_change`, con i confini descritti in §7.1.
- `assertion_type`: `occurrence` (accadimento), `statement` (dichiarazione), `belief` (convinzione esplicitamente espressa), `intention`; non una classificazione di verità aggiornata.
- Ogni entità generata ha `name`, `type`, `role`; `type` distingue `player`, `npc`, `faction`, `location`, `item`, `quest`, `other`. Il ruolo è descrittivo, non un nuovo grafo.
- `attribution` riferisce indici validi di `entities`; è non vuota per dichiarazioni, convinzioni e intenzioni. L'attore di un evento sta nelle entità e non viene trasformato in una fonte dichiarativa.
- `source_turns` contiene riferimenti locali non vuoti e non duplicati forniti nel batch (`t1`, `t2`, …); il codice li risolve a UUID e valida membership, senza affidare al modello gli ID persistenti.
- `temporal_references` è una lista di testi espliciti, non date normalizzate.
- `importance` ha `level` appartenente alla rubrica snapshot e `reason` non vuota; il massimo fatti si valida sull'intera lista, senza slicing.

I metadati persistenti aggiungono canonical ref solo se verificata, UUID, campagna/batch/fonti, versioni di schema/produttore/prompt, lingua e generazione effettiva. Canonical ref è una coppia tipo/ID risolta dalle fonti strutturate e da resolver non ambigui; non usare lo stato futuro della campagna per inventare retroattivamente l'identità di un'entità del batch. Per quelle irrisolte il riferimento rimane assente.

Il globale viene renderizzato deterministicamente come quattro sezioni ordinate dentro `<global_summary>`, con testo escapato e liste ordinate; le sezioni vuote rimangono rappresentabili. Non inviare l'intero record gestionale o i checkpoint precedenti al DM; non presentare `open_threads` come stato corrente autorevole. Il checkpoint precedente entra invece nella successiva generazione globale insieme al batch originale.

### 20.7 Operazioni e delta

`turn_operations`: UUID, campagna/turno, ordinale unico nel turno, step/beat se pertinenti, `origin` (`tool`, `npc`, `finalization`), nome operazione, argomenti, outcome (`succeeded`, `rejected`, `failed`), risultato e lista delta. UUID/ordine assegnati dal codice; outcome esplicito dal percorso esecutore, mai inferito dal testo o dall'assenza di cambiamenti.

Il risultato conserva l'esito meccanico rilevante: un check eseguito correttamente ma fallito nel gioco può essere `succeeded` con `check_success=false`; non diventa un errore tecnico o un'azione riuscita. Argomenti/esiti noti hanno schemi propri, non un dizionario illimitato che aggira la validazione.

Ogni delta contiene `scope` (`world_state`, `character_data`, `quests`), path e due valori discriminati: `{"presence":"absent"}` oppure `{"presence":"present","value": JsonValue}`. Inserimento, rimozione e null esplicito sono distinti. Si acquisiscono prima/dopo **per operazione**, così due cambiamenti che si annullano nel turno restano osservabili; non si producono snapshot completi dello stato per ogni tool.

Registrare anche i percorsi NPC (identità/psicologia/interazioni pertinenti) e finalizzazione. La proiezione per i job esclude soltanto routine identificata come tale, per esempio solo mood o solo clock: un viaggio o un'interruzione non scompare perché modifica anche l'orologio. La visibilità UI non decide l'esistenza del record. `world_updates.tool_events` preesistente non viene spacciato per questo registro: nei dati precedenti le operazioni complete sono **non registrate**, non una lista vuota certa.

Turno, head, stato ed eventi sono committati insieme. Nessuna task successiva tenta di ricostruire delta ormai perduti. La scelta dei fatti significativi rimane nel prompt, senza introdurre nuovi filtri sofisticati per categoria.

**S2 note (2026-11-10, implementation).** `turn_operations` conserva UUID, campagna/turno,
ordinale, step e beat come colonne; `payload` contiene origine, nome, argomenti, outcome,
risultato discriminato e delta validati. `turns.operations_version` e `operation_count`
distinguono una registrazione completa, anche vuota, dalle operazioni storiche non registrate
(`NULL`): la migrazione non ricostruisce dati e i vincoli differiti verificano cardinalità,
ordinali contigui e appartenenza alla campagna. Record e marcatori committati sono immutabili.

Gli argomenti conosciuti hanno un contratto persistente v1 indipendente dal registro runtime
dei tool: ritirare un tool non rende illeggibili le sue fonti già salvate. Un tentativo
rifiutato per argomenti invalidi conserva il JSON originale sotto un esito di errore esplicito,
non viene validato come una chiamata riuscita. Modifiche future della forma persistita
richiedono una nuova versione, non la reinterpretazione delle righe esistenti.

L'autocreazione NPC viene registrata prima della chiamata all'attore, separatamente dal suo
eventuale fallimento; l'ordine segue validazione, mutazioni e applicazione dei risultati,
non il riordino dei messaggi per il provider. La finalizzazione precedente modificava gli HP
attraverso una copia superficiale di `char_data`: ora usa una copia profonda e restituisce
esplicitamente il personaggio aggiornato, rendendo osservabile il delta senza mutare l'input
del nodo. Interazioni e verifica morte/fato sono operazioni distinte.

Il loader canonico legge membership e fonti persistite, conserva azioni e narrazioni anche
vuote e distingue `operations: null` da una registrazione vuota. Solo la proiezione per i
produttori esclude mood/clock isolati, verifiche morte senza conseguenze e aggiornamenti
meramente archivistici di `last_interactions`; il registro completo resta intatto. Il parlato
NPC compare nel transcript finale, non viene reiniettato tramite righe/descrizioni dell'esito
o copie della cronologia interazioni; identità, intenzioni ed effetti strutturati rimangono.
Viaggi, interruzioni, errori ed esiti significativi senza delta non vengono filtrati.

Turno, stato, operazioni, eventi UI e autosave usano la stessa transazione di persistenza;
head, claim/idempotenza, restore e attivazione della pipeline nuova restano al collegamento
S4b già previsto in §22. Nessuna campagna o memoria precedente viene convertita. I test
attraversano API, graph e handler reali con provider controllati e PostgreSQL reale, inclusi
rollback coordinato, cambiamenti poi annullati e fallimento NPC dopo autocreazione. Full
check: backend **1698/1698**, frontend **273/273**, lint, format, mypy, vulture, knip,
coverage e build verdi; nessuna chiamata live o scelta dei default discende da queste prove.

### 20.8 Configurazione e timeout

Namespace scelto per la nuova definizione: `memory.production`, con una sola definizione tipizzata dei default e snapshot `MemoryPolicy` per campagna. Questa è la forma, **non** un YAML da attivare con numeri provvisori:

| Percorso | Tipo / unità | Gate valore |
|---|---|---|
| `raw_turns`, `batch_turns`, `intermediate_limit`, `backlog_batches` | Interi R/B/K/H; B positivo, R/K/H non negativi | Owner dopo misure, §11 |
| `facts.max_per_batch` | Intero non negativo; nessun minimo di output | Eval S3 |
| `facts.importance_levels` | Lista unica di `{name, criteria, examples}` con nomi univoci; inizialmente ordinary/critical | Etichette decise; criteri/esempi verificati nell'eval |
| `global.target_words` | Obiettivo indicativo positivo espresso in parole; non taglio meccanico | Eval S3 |
| `jobs.max_attempts` | Intero positivo, comprende il tentativo iniziale | Owner prima dell'attivazione |
| `jobs.retry_backoff_seconds` | Sequenza finita di attese coerente con i tentativi ammessi | Owner prima dell'attivazione |
| `jobs.request_timeout_seconds`, `jobs.lease_seconds`, `jobs.poll_seconds` | Secondi positivi finiti; lease coerente con il tentativo completo | Owner prima dell'attivazione |
| `admission.wait_timeout_seconds` | Secondi positivi finiti per l'attesa pre-claim | Owner dopo verifica timeout di trasporto |

La policy snapshot congela tali regole di produzione, non provider/modello/credenziali, permessi amministrativi o timeout infrastrutturali del deployment. Il tetto output condiviso di 0018 rimane tale; non aggiungere cap per summary/fatti/globale senza una nuova decisione motivata. Le vecchie opzioni superate vengono ritirate nel cutover, non mantenute come fallback.

**Grounding S0.** Axios oggi non imposta un timeout (`frontend/src/shared/api/client.ts:11–14`); il mutation hook non conserva una chiave idempotente (`features/game/hooks/use-submit-action.ts:8–42`). Il claim del turno precede il graph e non ha un deadline endpoint dichiarato (`backend/app/api/turns.py:66–153`). Non esiste quindi già una durata verificata da copiare: prima di S4/S5 vanno fissati deadline server, margine client/proxy e timeout dell'esecuzione accettata, senza scambiare timeout di rete per mancato commit.

### 20.9 Export e verifica forward dello schema

L'export legge tutti gli oggetti della campagna in una transazione PostgreSQL `REPEATABLE READ READ ONLY`; restituisce un formato versionato e tipizzato con puntatori attivi, continuazioni, save, fonti, documenti, fatti, policy e diagnostica sanitizzata. Nessun claim/lease operativo, chiave o vettore obbligatorio. La validazione offline controlla tutti i riferimenti, anche quelli fuori dalla storia attiva.

Le migrazioni nuove seguono `009_campaign_language`; nessun dato storico viene convertito in una storia inventata. Eventuali campi nullable servono alla transizione dello schema, non a un writer/reader legacy permanente. Le campagne senza il nuovo contratto non devono entrare silenziosamente nella pipeline nuova. La gestione esplicita del cutover e i messaggi per i dati fuori contratto vengono verificati prima del ritiro definitivo, senza cancellazioni automatiche.

S1 deve provare vincoli, ancestry, partizione e migrazione 000→head su PostgreSQL reale. I test DB del progetto usano già Alembic (0019): non riproporre `create_all` o riscrivere fingerprint/revisioni congelate per far passare uno schema costruito a mano.

## 21. S0 — misure deterministiche iniziali (2026-11-09)

### Metodo e limiti dell'evidenza

- Inventario del DB locale esistente in `REPEATABLE READ READ ONLY`, con `transaction_read_only=on`: una campagna, 14 turni persistiti con numeri distinti 1–14, 64 fatti e un save; revisione `009_campaign_language`. Nessun reset, migrazione, backend/worker o chiamata provider.
- Un turno persistito ha narrazione vuota (numero 4); è distinto da un tentativo senza riga Turn. Non definire «completato» come «ha narrazione non vuota». Il vecchio reader lo salta, ma la nuova provenienza deve conservare anche l'azione e gli esiti del turno completato.
- Modello personale osservato: OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`, letto senza credenziali. Per la misura sono stati scaricati soltanto i file tokenizer/template pubblici NVIDIA, non pesi né codice remoto, con autorizzazione owner ad aggiungere un tokenizer esistente.
- Tokenizer ufficiale `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16`, revisione `77df655d5e9f8362164ed14dd8b48f8bce657498`; `transformers 5.22.2`, `tokenizers 0.23.3`. Nessun tokenizer artigianale o conversione caratteri/4 presentata come misura esatta.
- Ricostruzione del **primo step successivo** sullo stato attuale, usando l'ultima azione salvata come riferimento fisso: renderer production `render_dm_prompt`, reminder iniziale e 16 schemi tool reali. Non è il payload storico registrato di un turno già giocato né la misura di tutti i successivi step agentici.
- Nessun embedding/lookup semantico: il recall è escluso ed esplicitamente non misurato. Il conteggio con `apply_chat_template(..., tools=..., add_generation_prompt=True)` usa il template NVIDIA; il provider potrebbe adattarlo. **Token del template locale non significa token fatturati o finestra effettiva verificata su OpenRouter.**
- Download di artefatti e installazione temporanea del tokenizer separati dalla misura; durante rendering/tokenizzazione sono attivi flag offline e un audit hook che rifiuta accessi socket. Nessun prompt o testo della campagna viene inviato all'esterno o committato.

SHA-256 `tokenizer.json`: `623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7`; `chat_template.jinja`: `82753bef5cedc4932c1ed509b5c9a12be680fd86d1adb65bc3f7398d11c8eebc`. Snapshot letto per la misura, hash `489761659687a09b74574eded14227d0383538ff0cb1f3d7c65e1ed5ec480444`; codice production a `a09ebfc`.

### Risultati

| Componente | Caratteri | Byte UTF-8 | Token testo NVIDIA |
|---|---:|---:|---:|
| System senza memoria, con stato attuale e reminder | 12.466 | 12.468 | 2.786 |
| Schemi dei 16 tool, JSON compatto | 10.050 | 10.073 | 2.383 |
| Summary legacy effettivamente letti | 625 | 629 | 143 |
| Globale legacy | 0 | 0 | 0 |
| Azione di riferimento | 45 | 45 | 11 |

I componenti tokenizzati separatamente non sono additivi rispetto al template chat, che contiene proprie istruzioni/formattazioni dei tool. Con schema tool e template ufficiale il totale senza storia/recall è **6.161 token**, non la somma ingenua delle righe. L'ipotesi «circa 8k fissi» non è confermata su questo stato/modello: non è però una garanzia per tutte le scene o i modelli.

| Assemblaggio | Token template locale | Byte envelope JSON |
|---|---:|---:|
| Attuale: 8 raw + summary legacy, prima del cap | 8.586 | 33.599 |
| Stesso assemblaggio, dopo il cap attuale | 8.586 | 33.599 |
| Senza memoria/recall, ultimi 4 raw reali | 7.336 | 27.958 |
| Senza memoria/recall, ultimi 8 raw reali | 8.430 | 32.916 |
| Senza memoria/recall, ultimi 12 raw reali | 9.382 | 37.164 |
| Senza memoria/recall, tutti i 14 raw | 9.899 | 39.589 |

Il cap attuale non elimina coppie su questo snapshot: ciò non lo rende corretto in generale. Nei 14 turni, azione + narrazione hanno media **254 token testo**, mediana 258,5, minimo 10 (narrazione vuota) e massimo 365; sono dati di questa campagna, non massimi futuri. Gli eventi UI storici non permettono di misurare il peso dei nuovi delta completi, che rimane da rilevare su dati S2.

Per confrontare R/B/K senza inventare risultati generati: `prompt ≈ F + G + somma(S_1..S_i) + somma(raw_1..raw_r) + recall`, con `r <= R+B+H*B` e `i <= K+1+H` coordinati da q (§20.3), non due massimi indipendenti necessariamente simultanei. F è misurato qui per una scena; G e i nuovi S vanno prodotti/valutati in S3. La proiezione grezza `254*r` è una stima su questo campione, non una tokenizzazione dei futuri turni o del prompt finale.

Input del job raw: B transcript originali più risultati delle operazioni e istruzioni/output schema; input globale: precedente checkpoint completo più gli stessi originali di un batch e fonti strutturate. B non si deduce da R; K non cambia il numero di turni nuovi incorporati dal globale. Mancano ancora dimensioni reali dei documenti nuovi e degli eventi completi: nessuna matrice viene dichiarata validata da questi soli 14 turni.

### Gate eval ancora aperti

Prima di preparare esperimenti live, scegliere con l'owner quali dati reali usare, se costruire uno scenario lungo controllato e/o una nuova campagna con eventi completi, poi matrice R/B/K e modelli/ripetizioni/budget. Le misure sopra non autorizzano alcun run, non selezionano default e non riabilitano `gold` contaminato. H, limiti/retry/attese, massimo fatti e target globale restano al gate indicato in §11 e §20.8.

**Decisione owner S0 (2026-11-09, dataset).** Preparare i 14 turni reali come campione di fedeltà/dimensioni e uno scenario lungo controllato e annotato, con operazioni prodotte dai veri handler. Rifiutato usare soltanto i turni reali come prova longitudinale; non richiesta ora una nuova campagna di prova. Nessuna autorizzazione live discende dalla scelta del dataset. La lunghezza dello scenario dipende dalla matrice R/B/K e dai checkpoint consecutivi da osservare.

**Decisione owner S0 (2026-11-09, matrice).** Scegliere R/B/K in S3, non adesso. La proposta esplorativa `R={8,16}, B={4,8}, K={2,4}` e l'alternativa ridotta con K=4 restano **non adottate**: non sono default, run preparati o budget approvati. La stima di circa 267 token/raw comprende la media testo del campione e il framing chat locale; non risolve ancora il peso dei summary/globale. Per la sola pianificazione vale `N_primo_globale = R+(K+1)*B` e, per J aggiornamenti, `N = R+(K+J)*B`; non è stato scelto J né fissata la lunghezza dello scenario.

## 22. S0 — piano eseguibile, review e verifiche

**Decisione owner (2026-11-09).** Accettata la suddivisione S4a/S4b per mantenere ogni sprint giocabile, senza toggle legacy; invariati integrazione unica, branch consecutivi, merge locali `--no-ff` e una PR finale.

| Fase | Confine delle unità logiche e gate di uscita |
|---|---|
| S0 | Copia/adattamento ADR, schema/query e contratti, evidenza deterministica, gate owner; un commit documentale con indice/CHANGELOG e sola voce TODO già completata. Nessun codice production. |
| S1 | Policy/storia/identità dei turni; batch/documenti/fatti; job/provenienza/cursori; migrazioni e vincoli reali. Raggruppare modello con migrazione e relativi test, non commit microscopici per tabella. |
| S2 | Contratto outcome/delta; tool ordinari; NPC/finalizzazione; input canonico con persistenza atomica. Flussi provati dai veri handler. |
| S3 | Payload/rubrica, due YAML specialistici, produttori, harness/offline; run solo dopo approvazione specifica e scelta production/default solo dopo review owner. |
| S4a | Claim/tentativi/lease e recupero; due transizioni/pubblicazione atomica; coordinatore/scheduler e riconciliazione degli artefatti. Moduli verificati su DB, senza anticipare un cutover API parziale. |
| S4b | Claim/idempotenza dei turni e snapshot di lettura; storia/policy nel vero percorso, contesto a tre livelli, gating, filtro recall ed embedding fatti; save/load/fencing e gestione UI minima coerenti nello stesso collegamento. La regressione API→memoria→prompt si verifica qui. |
| S5 | Casi completi di restore/recovery, export referenzialmente coerente, completamento UX/retry e test cross-stack. Non è il primo momento in cui il load viene protetto. |
| S6 | Ritiro di writer/reader/config/test legacy e colonne transitorie; verifica cumulativa, eval longitudinale reale nuovamente autorizzata, full check e revisione finale. |

S4a lascia ancora intatto il percorso pubblico precedente; S4b sostituisce il percorso e i suoi consumer insieme, non introduce due modalità production selezionabili. Il ritiro finale degli orfani rimane in S6, ma un writer legacy non continua a produrre memoria in parallelo dopo il collegamento nuovo.

S1 può definire schema e policy tipizzati usando valori espliciti nei test, senza inventare default YAML per le campagne pubbliche: il nuovo percorso di creazione/snapshot viene collegato dopo il gate S3 e insieme al cutover S4b. Non convertire a posteriori le campagne di prova create dal vecchio percorso durante le fasi intermedie.

### Verifiche S0 eseguite, non sostitutive di S1–S6

- PostgreSQL 16 locale, query prototype CTE in transazione read-only: nove asserzioni su ancestry di due continuazioni, restore al prefisso, batch interamente compatibile, fatto che cita un turno condiviso ma deriva da batch futuro, numeri visualizzati uguali e non consecutivi. Nessuna tabella o campagna modificata; non è una verifica delle migrazioni ancora da scrivere.
- Modello astratto delle soglie: 43.020 stati enumerati, 33.300 ammissioni, 19.260 pubblicazioni raw, 20.550 globali e 9.720 blocchi al tetto; verificati tetti inclusivi dopo ammissione, q invariato nel trasferimento raw→intermedio e q ridotto dal globale. I domini usati nell'enumerazione non sono default o combinazioni eval approvate.
- Misure ripetute sullo stesso snapshot con tokenizer/template ufficiali e rete bloccata; nessuna chiamata generation/embedding. Risultati riportati in §21, non spacciati per eval di qualità.
- Review indipendente GPT-6 Luna sui contratti S0: dopo verifica dei due controesempi inizialmente ipotizzati e chiarimento della proiezione inclusiva/cursori immutabili, nessun blocco tecnico individuato. Non è accettazione della pipeline non ancora implementata.
- Controllo documentale `git diff --check` e `saga_check affected`: pass, nessuna modifica runtime pertinente; piano originale verificato con SHA-256 invariato. Il risultato noop di affected non è un nuovo full check.
