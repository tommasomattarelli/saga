# SAGA v1 — Findings Completi
*Sintesi di: chat Gemini + chat Claude. Tutti i punti discussi, con stato e decisioni prese.*

---

## 1. TURN PIPELINE — Componenti Mancanti o Incompleti

### 1.1 Semantic Resolver (ex "Intent Extractor") — NON ESISTE NEGLI MD

**Problema:** Il Context Assembler attuale costruisce il contesto solo sulla location corrente del player nel DB. Se il player scrive "vado a Neverwinter" o "vado con lei", il backend non sa cosa caricare e il DM riceve un prompt senza quei dati, allucinando luoghi e personaggi.

**Decisione presa:** Aggiungere un componente `SemanticResolver` come step esplicito nel pipeline, prima del Context Assembler. È una mini-call a un budget model (no reasoning) con latenza ~200ms (trascurabile).

**Cosa fa:**
- Estrae location esplicite ("Neverwinter", "la città di fianco" → risolto con contesto sessione)
- Estrae NPC espliciti e pronominali ("lei" → "Grenda" perché è l'unica companion femminile attiva)
- Stima il tempo narrativo dell'azione (vedere punto 4)
- Output: `{ target_locations: [], target_npcs: [], time_estimate_minutes: int }`

**Perché il modello piccolo funziona:** Riceve il contesto della sessione (companion attivi, location recenti), quindi risolve correttamente anche i riferimenti impliciti che un parser regex non gestirebbe mai.

**Dove si inserisce nel pipeline:**
```
Sanitizer → [Semantic Resolver] → Context Assembler → DM call
```

**File da creare:** `backend/app/ai/semantic_resolver.py`

---

### 1.2 DMResponse Schema Incompleto — 2 Campi Mancanti

Il Pydantic model `DMResponse` in `backend/app/ai/schemas/dm_response.py` definisce:
`narration`, `dice_required`, `companion_actions`, `world_updates`, `scene_mood`, `suggested_actions`, `ambient_detail`, `scene_image_prompt`.

**Mancano questi campi:**

**Campo 1: `invoke_npcs: list[str] = []`**
Il DM decide chi parla in questa scena, non il backend. Senza questo campo, il backend non sa quali NPC chiamare per il dialogo autonomo. Questo è il punto di innesco del pattern Actor-Director (vedere punto 2).

**Campo 2: `time_passed_minutes: int = 5`**
Il DM dichiara quanto tempo narrativo è passato durante l'azione. Default 5 minuti per un turno generico. Il DM usa 0 per puro dialogo, 5-15 per esplorazione locale, 60 per viaggio breve, 480 per riposo lungo. Il backend accumula in `world_state.clock.total_minutes` e deriva ora/giorno/stagione. Il DM gestisce questo naturalmente perché ha contesto narrativo — sa se stai cavalcando per ore o parlando con un mercante.

**Campo 3 (rimosso dal DM): `requires_player_action: bool`**
Discusso e rimosso. Non va chiesto al DM — è troppo fragile e il DM sbaglia spesso questo giudizio. Va derivato deterministicamente dal backend (vedere punto 3).

---

### 1.3 Healing Parser — Non Esiste

**Problema:** Il parser attuale in `backend/app/ai/parser.py` fa il retry se il JSON è malformato, ma non tenta di ripararlo. Gli LLM producono frequentemente JSON con markdown code blocks (` ```json ... ``` `), virgole mancanti, preamboli testuali prima del JSON.

**Decisione presa:** Aggiungere un middleware di pulizia prima della validazione Pydantic, usando la libreria `json-repair` (Python). Il flusso diventa:

```
LLM raw output → strip markdown fences → json-repair → Pydantic validation → retry solo se ancora invalido
```

Questo riduce i retry (costosi in latenza) del ~70%.

---

### 1.4 Content Policy Handler — Non Esiste

**Problema:** Se una chiamata API ritorna `content_policy_violation` (HTTP 400 con flag moderazione), il backend attuale la tratta come un errore generico. Il turno si blocca silenziosamente o crasha con un errore tecnico incomprensibile per il player.

**Decisione presa:** Intercettare specificamente questo errore nel provider layer (`backend/app/ai/providers/`) e restituire al player un messaggio leggibile:

> *"The DM refuses to narrate this scene as described. Try rephrasing your action."*

Con una chiara distinzione nel log tra "errore tecnico" e "blocco policy" per il debug.

**Cosa blocca (per referenza nella configurazione dei prompt):**
- Violenza fantasy standard → OK (decapitazioni, combattimento, sangue contestuale)
- Tortura dettagliata e sadismo prolungato → BLOCCO
- Violenza su bambini o civili innocenti in modo esplicito → BLOCCO
- Romanticismo, baci, intimità implicita → OK
- Atto sessuale esplicito (anatomia, meccanica) → BLOCCO
- Non-consensual sempre → BLOCCO

**Soluzione architetturale per l'uncensored:** Il supporto ai modelli locali (Ollama) già nelle specs è la risposta corretta — chi vuole contenuti unrestricted hosta il proprio modello. Il `MaturityLevel: Unrestricted` nelle specs funziona solo con provider locale.

---

## 2. PATTERN ACTOR-DIRECTOR — Non Esiste Negli MD

**Problema attuale:** Il DM fa tutto — narra la scena, fa parlare tutti gli NPC, descrive le reazioni dei companion. Questo produce:
- "Voce AI omogenea": tutti gli NPC parlano con lo stesso tono e struttura di frase
- "Bleed di personalità": il DM fatica a mantenere 5 maschere diverse nello stesso prompt
- È esattamente la critica "ChatGPT wrapper" — un solo modello che simula tutto

**Soluzione: Pattern Actor-Director**

Il DM è il *Regista*. Gli NPC sono *Attori* indipendenti con la propria call.

**Flusso completo:**

```
1. DM risponde con invoke_npcs: ["Grenda", "Re Aldric"]
2. Backend lancia SUBITO le chiamate NPC in parallelo (asyncio.gather)
3. Frontend inizia a streammare la narration del DM (Approccio A - vedere punto 6)
4. Mentre il player legge la narrazione (~2-3 secondi), gli NPC generano
5. I dialoghi NPC arrivano direttamente alla UI via WebSocket (evento npc:dialogue)
6. I dialoghi NPC NON tornano mai al DM — vanno a schermo direttamente
7. Il turno finisce dopo i dialoghi NPC. Il DM riprende solo al turno successivo.
```

**Prompt per ogni NPC (budget model):**
- Nome, ruolo, professione
- Carattere e tratti di personalità
- Disposition attuale verso il player (valore numerico)
- Ultima interazione con il player (dal memory_facts, vedere punto 8)
- Azione del player che ha innescato la risposta
- Istruzione: "Rispondi in 1-2 frasi, in character, con questa personalità."

**Vantaggi:**
- Ogni NPC ha voce distinta e imprevedibile
- Il DM si sorprende delle risposte NPC → gameplay emergente autentico
- Latenza percepita zero: i dialoghi NPC avvengono mentre il player legge la narrazione
- Costo minimo: budget model, 1-2 frasi di output

**Nuovi eventi WebSocket necessari:**
- `npc:dialogue:start` — NPC X inizia a rispondere
- `npc:dialogue:chunk` — streaming testo NPC
- `npc:dialogue:end` — NPC X ha finito

**File da modificare:** `backend/app/api/websocket.py`, `backend/app/services/turn_service.py`, `backend/app/ai/prompts/npc.py`

---

## 3. REQUIRES_PLAYER_ACTION — Derivato dal Backend, Non dal DM

**Problema:** Il DM non ha abbastanza contesto meccanico per decidere correttamente se questa è una scelta obbligatoria per il player. Sbaglia frequentemente.

**Decisione presa:** Non è un campo del DMResponse. È un booleano calcolato deterministicamente dal backend dopo aver ricevuto la risposta DM:

```python
def compute_requires_action(world_state: WorldState, dm_response: DMResponse) -> bool:
    if world_state.combat_state.active:
        return True
    if dm_response.dice_required is not None:
        return True
    # Euristica narrativa: il DM ha fatto una domanda diretta o un personaggio aspetta risposta
    # Opzionale v2: analisi del testo di narration per "?" o "aspetta la tua risposta"
    return False  # default: pulsante Continua sempre abilitato
```

Il pulsante "Continua" nel frontend è abilitato quando `requires_action == False`. Se il player preme Continua senza scrivere nulla, il backend invia un'azione implicita `"wait"` al DM, che narra il passare del tempo.

---

## 4. TIME ENGINE — Non Esiste, Schema Mancante

**Problema:** Le specs hanno `schedule system` per gli NPC ma non esiste un Time Engine che faccia avanzare il clock in modo coerente. Senza tempo, le routine degli NPC e il World Simulator futuro non hanno carburante. "Quanto tempo ci vuole a esplorare questa stanza?" non ha risposta.

**Soluzione adottata:** Il campo `time_passed_minutes` nel DMResponse (vedere punto 1.2) alimenta un Time Engine leggero nel World State Updater.

**Schema da aggiungere al World State:**

```python
class GameClock(BaseModel):
    total_minutes: int = 0          # accumulato da ogni turno
    current_hour: int = 8           # derivato: total_minutes // 60 % 24
    current_day: int = 1            # derivato: total_minutes // 1440
    current_season: str = "spring"  # derivato dai giorni
    time_of_day: str = "morning"    # "dawn|morning|afternoon|evening|night|midnight"
```

Il World State Updater legge `time_passed_minutes` dal DMResponse e aggiorna il clock dopo ogni turno. `current_hour`, `time_of_day`, `current_day` vengono ricalcolati automaticamente.

Il clock alimenta:
- Descrizioni ambientali nel prompt ("è tarda sera, la taverna è piena")
- Schedule NPC ("Grenda è alla forgia di mattina, alla taverna di sera")
- World Simulator in v2 (eventi che avvengono durante la notte)
- Ciclo giorno/notte visivo nel frontend (World Panel)

**Valori guida per il DM nel system prompt:**
- Dialogo / azione singola: 1-5 minuti
- Esplorazione stanza/edificio: 10-30 minuti
- Viaggio locale (quartiere): 30-60 minuti
- Viaggio tra zone: 2-8 ore (120-480 minuti)
- Riposo breve: 60 minuti
- Riposo lungo / notte: 480 minuti (8 ore)

---

## 5. WORLD SIMULATOR — Fondamenta in v1, Logica in v2

**Problema:** Senza World Simulator, ogni volta che il player torna in un posto il mondo è congelato esattamente dove lo ha lasciato. Questo è il singolo elemento che distingue un mondo vivo da uno statico.

**Decisione presa:** Non implementare la logica in v1, ma aggiungere lo schema nel World State ora per evitare migration complesse in v2.

**Schema da aggiungere al World State ora (v1):**

```python
class WorldSimulatorState(BaseModel):
    enabled: bool = False                    # toggle utente nelle preferenze campagna
    last_simulated_turn: int = 0
    pending_world_events: list[dict] = []    # eventi schedulati non ancora narrati
    scheduled_npc_actions: list[dict] = []  # azioni NPC pianificate (routine)
```

**Logica v2 (per referenza futura):**
- Ogni N turni, una chiamata background asincrona (asyncio.create_task, non bloccante) a un budget model
- Il modello riceve: fazioni attive, NPC con goals e routine, clock corrente
- Output: lista di eventi da aggiungere a `pending_world_events`
- Questi eventi vengono narrati dal DM quando diventano rilevanti per il player
- Toggle nelle preferenze campagna: disabilitabile per risparmiare token

---

## 6. STREAMING JSON — Soluzione Approccio A

**Problema:** Come fare streaming della risposta DM se la risposta è un JSON strutturato? Il frontend non può aspettare che il JSON completo arrivi prima di iniziare a mostrare il testo.

**Decisione presa: Approccio A — Narration-first ordering.**

Il system prompt istruisce il DM a mettere `narration` come *primo campo* del JSON. Il frontend usa un parser JSON parziale (streaming JSON parser) che inizia a estrarre e renderizzare il valore di `narration` non appena individua `"narration": "` nello stream, senza aspettare il JSON completo.

```
Stream: {"narration": "Il goblin si avvicina men|
                                               ↑ frontend inizia a renderizzare qui
```

Gli altri campi (`world_updates`, `invoke_npcs`, `dice_required`, ecc.) vengono parsati solo quando il JSON è completo. Nessun impatto sulla latenza della narrazione.

**Librerie:** `jsonstream` (Python, backend), parser custom o `oboe.js` (TypeScript, frontend).

**Vantaggi rispetto agli altri approcci:**
- Zero costo extra (una sola call LLM)
- Provider agnostico (non dipende da Tool Calling nativo)
- Mantiene il TTFT < 500ms

**Ordine campi nel JSON DM (da specificare nel system prompt):**
1. `narration` — primo, streammato subito
2. `invoke_npcs` — secondo, così le call NPC partono appena arriva
3. `dice_required`
4. `scene_mood`
5. `time_passed_minutes`
6. `companion_actions`
7. `world_updates` — ultimi, sono i più pesanti
8. `suggested_actions`
9. `ambient_detail`

---

## 7. REDIS — Rinviato

**Decisione presa:** Rimuovere Redis dalla v1 MVP.

**Motivazione:** Nel contesto self-hosted single-user della v1:
- JWT sono stateless, nessuno store esterno necessario
- Rate limiting su un utente non ha senso
- Race conditions gestite con `asyncio.Lock()` per campaign ID in memoria — sufficiente perché il player non può fisicamente inviare due turni mentre uno è in elaborazione (UI disabilita l'input)

**Quando reintrodurre:** v2 SaaS multi-utente. L'aggiunta richiede ~2 ore di lavoro (dependency + `get_redis()` + rimpiazzo dei Lock). Non è un'operazione complessa.

**Cosa rimpiazza Redis nella v1:**
```python
# In-memory locks per campaign (evita race conditions)
_campaign_locks: dict[str, asyncio.Lock] = {}

async def get_campaign_lock(campaign_id: str) -> asyncio.Lock:
    if campaign_id not in _campaign_locks:
        _campaign_locks[campaign_id] = asyncio.Lock()
    return _campaign_locks[campaign_id]
```

---

## 8. MEMORIA — Architettura a 3 Pilastri + Tabella memory_facts

**Problema:** Le specs trattano pgvector, memory compression e recap system come feature separate in fasi diverse. Non esiste un'architettura unificata che chiarisca il ruolo di ognuno. Inoltre, la granularità di cosa embedare non è definita.

### Architettura a 3 Pilastri

**Pilastro 1 — Core State (sempre presente, token fissi)**
- Il World State JSON caricato selettivamente per location/scena (Contextual Loading)
- Il Recap narrativo generato ogni 25 turni (budget model, 500-800 parole)
- Il Recap va SEMPRE nel system prompt come "bussola permanente" — non solo nel JournalView
- Questo è il quadro generale: chi siamo, cosa stiamo facendo, dove siamo arrivati
- Token budget fisso: ~1500 token

**Pilastro 2 — Active Window (conversazione recente)**
- Ultimi 5-8 turni verbatim (testo esatto di input player + narrazione DM)
- Dà al DM il flow immediato della conversazione
- Turni che escono dalla finestra vengono compressi (Memory Compression Tier 2)
- Token budget: ~2000 token

**Pilastro 3 — Fatti Atomici / RAG (dettagli puntuali dal passato)**
- Non serve per il quadro generale (quello è il Recap)
- Serve per recuperare dettagli specifici persi 20+ sessioni fa: "cosa aveva detto il fabbro sulla spada?", "qual è il nome del figlio segreto del Re?"
- Granularità: singolo fatto atomico strutturato, NON capitoli di testo, NON narrazione grezza
- Top 3-5 fatti iniettati nel prompt per turno
- Token budget: ~500 token

### Tabella memory_facts — NON ESISTE NEL DB SCHEMA

Il campo `embedding` sul modello `Turn` non è sufficiente. Serve una tabella dedicata:

```python
class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id: uuid
    campaign_id: uuid (FK → campaigns)
    turn_number: int
    entity_name: str          # "Grenda", "Neverwinter", "DragonHunt"
    entity_type: str          # "npc", "location", "quest", "item", "event", "secret"
    content: str              # il fatto atomico in linguaggio naturale
    embedding: vector(1536)   # pgvector
    search_vector: tsvector   # per full-text search ibrido
    created_at: timestamp
```

### Granularità dei Fatti Atomici

Dopo ogni turno, un **Fact Extractor** (budget model, asincrono, non bloccante) estrae 1-5 fatti atomici dal testo di quel turno. Ogni fatto è una stringa strutturata:

```
"Grenda:relazione:ostile — ha scoperto il furto della borsa al turno 23"
"Neverwinter:luogo:visitato — prima visita turno 3, torre bruciata scoperta"
"DragonHunt:quest:accettata — ricompensa 500 oro promessa dal Re al turno 15"
"Re Aldric:segreto:rivelato — figlio illegittimo, confidato in privato turno 67"
"Spada di Kael:item:proprietà — incanta il fuoco, spiegato dal fabbro al turno 12"
```

Un fatto = una riga nel DB = un embedding. Granularità fine, retrieval preciso.

### Hybrid Search con pgvector

pgvector supporta la ricerca ibrida. La query del Context Assembler combina:

```sql
SELECT content,
  (1 - (embedding <=> $query_embedding)) * 0.7 +
  ts_rank(search_vector, plainto_tsquery($player_action_text)) * 0.3 AS hybrid_score
FROM memory_facts
WHERE campaign_id = $campaign_id
  AND (
    entity_name = ANY($active_npcs_in_scene)
    OR (entity_type = 'location' AND entity_name = $current_location)
    OR entity_type = 'quest'  -- quest sempre rilevanti
  )
ORDER BY hybrid_score DESC
LIMIT 5;
```

Il 70% semantico trova la similitudine di senso, il 30% keyword garantisce il match esatto su nomi propri e termini specifici. I filtri metadata (`entity_name`, `entity_type`, `current_location`) rendono il RAG "schematico" — non cerca nel vuoto ma dentro un perimetro definito.

### Come il Context Assembler usa i 3 Pilastri

Il Semantic Resolver (punto 1.1) produce gli input per le query:

```python
async def assemble_context(campaign_id, world_state, player_action, resolver_output):
    # Pilastro 1: sempre presente
    core_json = load_contextual_world_state(world_state, resolver_output.target_locations)
    recap = world_state.narrative.current_recap  # generato ogni 25 turni

    # Pilastro 2: finestra attiva
    recent_turns = await get_recent_turns(campaign_id, limit=8)

    # Pilastro 3: fatti rilevanti (query ibrida)
    active_npcs = resolver_output.target_npcs + get_npcs_in_scene(world_state)
    facts = await hybrid_search_facts(
        campaign_id=campaign_id,
        query_text=player_action,
        active_npcs=active_npcs,
        current_location=world_state.player.location,
        limit=5
    )

    return build_prompt(core_json, recap, recent_turns, facts)
```

### Fact Extractor — Pipeline Background

```
[World State Updated] → asyncio.create_task(extract_facts(turn))
                        ↓ (non bloccante, player non aspetta)
                     [Budget Model] → 1-5 fatti atomici
                        ↓
                     [INSERT INTO memory_facts]
```

**File da creare/modificare:**
- `backend/app/models/memory_fact.py` — nuovo modello SQLAlchemy
- `backend/app/memory/semantic.py` — aggiornare con hybrid search
- `backend/app/memory/fact_extractor.py` — nuovo, chiamato in background post-turno
- Alembic migration per la nuova tabella

---

## 9. CONTEXT ASSEMBLER — Contextual Loading + Coreference

**Problema:** Il Context Assembler hardcodato (carica sempre gli NPC della location corrente) non gestisce:
- Riferimenti impliciti: "vado con lei" — chi è "lei"?
- Location non esplicite: "la città di fianco" — quale?
- NPC non nella scena ma rilevanti: il companion che hai lasciato alla taverna

**Soluzione:** Il Context Assembler non usa regole fisse come logica principale. Usa l'output del Semantic Resolver come guida primaria, con le regole fisse come fallback:

```
Carica = NPC(location corrente) + NPC(risolti da Semantic Resolver) + Companion(attivi)
```

Le regole fisse (carica sempre la location corrente, carica sempre i companion) sono il minimum guaranteed. Il Semantic Resolver aggiunge tutto il resto.

---

## 10. CONFRONTO COMPETITOR — Posizionamento

### NeverEndingQuest
- Nessun DB relazionale, tutto su file di testo
- Memoria basata su riassunti testuali a cascata (no pgvector)
- NPC senza state strutturato — riassunti discorsivi che possono allucinare
- UI testuale classica, latenza 10-15 secondi per turno
- Installer one-click su Windows (vantaggio per utenti non tecnici)

**SAGA vince su:** stato del mondo matematicamente consistente, memoria strutturata, latenza <500ms, Actor-Director per NPC con voci distinte.

### Friends & Fables
- Sistema a entità strutturate (NPC → Città → Fazione), simile a SAGA
- "Memorie Atomiche" — stesso concetto della tabella `memory_facts` proposta, ma limitate per tier di abbonamento (30/100 memorie per piano)
- Tutti i dialoghi NPC gestiti da un singolo DM "Franz" → stesso problema voce omogenea
- Fortemente ancorato a D&D 5e

**SAGA vince su:** memory_facts illimitate con pgvector scalabile, Actor-Director, system agnostico (fantasy/sci-fi/post-apo), open source self-hosted, modelli locali.

---

## 11. COSTI API — Stima Marzo 2026

Prezzi di mercato medi:

| Tier | Modello esempio | Input (per 1M token) | Output (per 1M token) |
|------|----------------|---------------------|----------------------|
| Premium | GPT-5 / Claude Opus | ~2.50€ | ~10.00€ |
| Mid | GPT-4o / Gemini 2.5 Pro | ~0.80€ | ~3.00€ |
| Budget | GPT-4o-mini / Gemini Flash | ~0.15€ | ~0.60€ |
| Embedding | text-embedding-3 | ~0.02€ | — |

**Costo per turno "pesante" (narrazione DM + 2 NPC + fact extraction):**
- DM call (mid): ~2000 token input + 200 output = ~0.0022€
- NPC x2 (budget, parallele): ~500 token input × 2 + 50 output × 2 = ~0.0002€
- Fact extractor (budget): ~300 token input + 100 output = ~0.00007€
- **Totale per turno: ~0.0025€** (meno di un quarto di centesimo)

**Per il player:**
- Sessione 2 ore / 50 turni: ~0.12€
- Mese hardcore / 15 sessioni / 750 turni: ~1.90€

L'AI Router che usa budget models per NPC e fact extraction mantiene i costi irrisori anche a lungo termine.

---

## 12. DOCKER & SETUP — Problemi Noti per Self-Hosted

**WSL2 su Windows:** Docker Desktop su Windows richiede WSL2 abilitato. Molti utenti non tecnici trovano questo scoglio. `INSTALL.md` deve includere una sezione specifica con istruzioni WSL2 step-by-step e link a video tutorial.

**Conflitti di porta:** Se l'utente ha già PostgreSQL installato sulla porta 5432, `docker compose up` crasha. Nel `docker-compose.yml` mappare PostgreSQL su porta esterna non standard (es. `54320:5432`). Stesso per Redis se presente (es. `63790:6379`).

---

## 13. POLICY CONTENT — Configurazione Maturity Level

Il `MaturityLevel` nelle specs (Standard/Mature/Unrestricted) deve avere comportamenti chiari nel system prompt DM:

- **Standard:** Violenza fantasy accettabile (combattimento, sangue), romanticismo implicito, atti sessuali → fade to black. Istruzione al DM: "sfuma al nero per scene esplicite e violenza gratuita."
- **Mature:** Violenza più esplicita accettata, romanticismo più diretto ma non pornografico. Solo provider che lo supportano (Anthropic è più restrittivo di OpenAI su questo).
- **Unrestricted:** Solo con provider locale (Ollama + modello uncensored). Il backend deve bloccare questa opzione se il provider configurato è cloud.

Il content policy handler (punto 1.4) deve distinguere tra errori da policy e errori tecnici nel log.

---

## 14. RECAP SYSTEM — Ruolo Chiarito

Il Recap System (Fase D2 nella roadmap) ha un ruolo duale che non è esplicitato:

**Ruolo 1 — JournalView (già nelle specs):** Il recap è visibile al player come sommario narrativo dell'avventura. Feature UI.

**Ruolo 2 — System Prompt (nuovo, critico):** Il recap più recente viene iniettato nel system prompt del DM come "bussola permanente" a ogni turno. Non è opzionale — è il modo in cui il DM mantiene il quadro generale senza tenere 100 turni di storia nel contesto. Senza questo, il DM alla sessione 5 dimentica chi siamo e perché siamo qui.

**Trigger:** Ogni 25 turni, un budget model legge gli ultimi 25 turni + il recap precedente e genera un nuovo recap cumulativo di 500-800 parole. Il recap vecchio viene archiviato (per il JournalView), il nuovo sostituisce quello nel system prompt.

**Token budget:** Il recap usa ~600-700 token del system prompt. Non va mai rimosso per fare spazio ad altro — è il secondo elemento più importante del prompt dopo le rules del DM.

---

## 15. RIEPILOGO MODIFICHE PER MD ESISTENTI

### Da aggiungere a SAGA_v1_specs.md

- Sezione 4.1 (Turn Pipeline): aggiungere Semantic Resolver come step esplicito
- Sezione 4.3 (DM Output): aggiungere campi `invoke_npcs`, `time_passed_minutes`; rimuovere `requires_player_action` dal DM; aggiungere nota su ordine dei campi per streaming
- Sezione 4.4 (Streaming): aggiungere specifica Approccio A (narration-first + streaming JSON parser)
- Sezione 6 (NPC & Companion): aggiungere pattern Actor-Director con chiamate parallele budget model
- Sezione 9 (Memory): riscrivere come architettura a 3 pilastri con ruoli espliciti
- Sezione 13 (Database): aggiungere modello `MemoryFact`; aggiungere `WorldSimulatorState` e `GameClock` al World State schema
- Sezione 15 (Sicurezza): aggiungere nota content policy handler
- Nota finale: rimuovere Redis dalla lista dipendenze v1

### Da aggiungere a SAGA_v1_roadmap.md

- Fase A1: aggiungere task Healing Parser + campo `invoke_npcs` + `time_passed_minutes` + content policy handler
- Fase A2: aggiungere Time Engine (clock nel world state)
- Fase B (nuova sezione B0 o B1.0): Semantic Resolver implementation
- Fase B3 (Memory): aggiungere tabella `memory_facts`, Fact Extractor background task, hybrid search query
- Fase B1 (World State): aggiungere `WorldSimulatorState` schema stub, `GameClock`
- Fase D1 (pgvector): riscrivere con granularità atomica e hybrid search
- Aggiungere nota: World Simulator logica → v2, schema → v1
- Aggiungere nota: Redis → v2

### Da aggiungere a SPECS.md

- Sezione "Key Architectural Decisions": aggiungere Semantic Resolver, Actor-Director pattern, Time Engine, 3-pillar memory
- Aggiornare schema `DMResponse` nei riferimenti
- Aggiungere `memory_facts` table agli schemi DB

---

*Documento generato il: Marzo 2026*
*Fonti: chat Gemini (analisi architettuale iniziale) + chat Claude (revisione critica e decisioni finali)*
