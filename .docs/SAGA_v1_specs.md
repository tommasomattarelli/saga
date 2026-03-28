# SAGA v1 — Specifiche Complete per il Lancio

**Obiettivo:** Friends & Fables self-hostabile, open source, con API keys proprie o modelli locali.

**Architettura target:** React + FastAPI + PostgreSQL (pgvector) + Redis + Docker

---

## 1. INFRASTRUTTURA & SETUP

### 1.1 Docker & Deployment
- [x] Docker Compose con tutti i servizi (frontend, backend, PostgreSQL + pgvector)
- [x] `docker compose up -d` funzionante da zero
- [ ] File `.env.example` con tutte le variabili documentate
- [ ] PostgreSQL 16+ con estensione pgvector abilitata
- [ ] In-memory `asyncio.Lock()` per campaign ID (race condition prevention — Redis rinviato a v2 SaaS)
- [ ] Script di primo avvio (creazione admin, migration DB)
- [ ] Porte non standard nel docker-compose (es. `54320:5432`) per evitare conflitti con PostgreSQL locale

### 1.2 CI/CD
- [ ] GitHub Actions: lint, test, build
- [ ] Semantic versioning + changelog automatico
- [ ] Build Docker automatica su push a main

---

## 2. AUTENTICAZIONE & UTENTI

### 2.1 Auth
- [ ] Registrazione utente (email + password)
- [ ] Login con JWT (access token 30min + refresh token 30 giorni)
- [ ] Refresh token endpoint
- [ ] Password hashing con bcrypt
- [ ] RBAC: ruoli user / admin

### 2.2 Gestione API Keys
- [ ] UI per inserire API keys (OpenAI, Anthropic, Google)
- [ ] Crittografia AES-256 delle chiavi nel DB
- [ ] Pulsante "test connection" per ogni provider
- [ ] Le chiavi non vengono mai mostrate in chiaro dopo l'inserimento

### 2.3 Preferenze Utente
- [ ] Lingua preferita (default: en)
- [ ] Maturity level preferito (Standard / Mature / Unrestricted)
- [ ] Provider AI preferito

---

## 3. SISTEMA AI MULTI-PROVIDER

### 3.1 Provider Supportati
- [ ] OpenAI (GPT-4o, GPT-4o-mini, GPT-5.2 se disponibile)
- [ ] Anthropic (Claude Sonnet, Claude Opus)
- [ ] Google (Gemini 2.0 Flash, Gemini 2.5 Pro, Gemini 3 Flash/Pro)
- [ ] Provider locale via API OpenAI-compatible (Ollama, KoboldCpp, vLLM)

### 3.2 AI Router (`ai/router.py`)
- [x] Selezione automatica del modello in base al tipo di modulo (DM, NPC, companion, world sim) — `AICallType` enum + `route_ai_call()` + `GameplayConfig`
- [ ] Sistema di punteggio importanza scena (base + modificatori narrativi)
- [ ] Score 0-2 → budget model, 3-5 → mid-tier, 6+ → premium
- [ ] Fallback chain se provider non disponibile
- [ ] Configurazione modelli via `model_config.yaml` (overridabile dall'utente)
- [ ] Tracking costi per ogni chiamata API

### 3.3 Prompt Caching
- [ ] System prompt cachato tra i turni (immutabile per sessione)
- [ ] World lore summary cachato per sessione
- [ ] Character sheet cachato fino a modifica

### 3.4 Input Sanitizer (`ai/sanitizer.py`)
- [ ] Rilevamento prompt injection (pattern matching + euristiche)
- [ ] Filtro profanità basato su maturity level della campagna
- [ ] Limite lunghezza input (default: 2000 caratteri)
- [ ] Escape di caratteri che rompono il formato JSON

---

## 4. CORE GAMEPLAY — TURNO

### 4.1 Turn Pipeline (`core/engine.py`)
- [ ] Player invia azione (testo libero)
- [ ] Sanitizer valida l'input
- [x] **Semantic Resolver** (`ai/semantic_resolver.py`) — mini-call a budget model (~200ms) che estrae dal testo del player:
  - Location esplicite e implicite ("la città di fianco" → risolta con contesto sessione)
  - NPC espliciti e pronominali ("lei" → "Grenda" perché unica companion femminile attiva)
  - Stima tempo narrativo dell'azione (in minuti)
  - Output: `{ target_locations: [], target_npcs: [], time_estimate_minutes: int }`
  - Riceve il contesto sessione (companion attivi, location recenti) per risolvere riferimenti impliciti
- [ ] Context Assembler costruisce il prompt DM (usa output Semantic Resolver come guida primaria + regole fisse come fallback) — resolver pronto, loading selettivo in Phase D
- [ ] Dice Engine tira dadi se necessario pre-prompt
- [ ] AI Engine invia prompt al LLM via Router, streaming risposta
- [x] **Healing Parser**: strip markdown fences → `json-repair` → Pydantic validation → retry solo se ancora invalido (riduce retry del ~70%)
- [ ] Response Parser estrae JSON strutturato dalla risposta DM
- [x] **Content Policy Handler**: intercetta `content_policy_violation` (HTTP 400) nel provider layer e ritorna messaggio leggibile al player ("The DM refuses to narrate this scene as described. Try rephrasing your action.") con distinzione nel log tra errore tecnico e blocco policy
- [x] Se il DM richiede un tiro di dado, il Dice Engine tira e ri-prompta per la narrazione
- [x] **`requires_player_action`** — booleano derivato dal backend (non dal DM): `True` se combat attivo o dice_required presente, `False` altrimenti (pulsante "Continua" abilitato, azione implicita `"wait"`)
- [x] Se `invoke_npcs` presente → lancia chiamate NPC in parallelo (Actor-Director, vedere sez. 6)
- [x] World State Updater applica i world_updates + aggiorna GameClock con `time_passed_minutes`
- [x] **Fact Extractor** (asincrono, non bloccante) estrae 1-5 fatti atomici dal turno → INSERT in `memory_facts`
- [x] Memory Manager comprime turni vecchi se necessario (`ensure_compression` in `memory/compressor.py`)
- [ ] Auto-save del world state
- [ ] Turno persistito nel DB con delta e costo AI
- [ ] World Simulator esegue eventi off-screen (asincrono, logica in v2, schema in v1)

### 4.2 Dice Engine
- [x] Meccanica d20 base: d20 + stat modifier + bonus vs DC
- [x] Risultati graduali: Natural 1 / Hard Fail / Soft Fail / Partial / Full / Nat 20
- [x] Vantaggio e svantaggio (2d20 take high/low)
- [x] Il DM decide quando tirare (trivial → auto success, impossible → auto fail)
- [x] Roll calcolato server-side, animazione client-side
- [x] Dadi mostrati al player con risultato trasparente

### 4.3 DM Output Strutturato
- [x] Risposta DM in JSON con campi (in quest'ordine per streaming, vedere sez. 4.4):
  1. `narration: str` — primo, streammato subito
  2. `invoke_npcs: list[str] = []` — secondo, così le call NPC Actor-Director partono appena arriva
  3. `dice_required: Optional[DiceRequest]`
  4. `scene_mood: str = "neutral"`
  5. `time_passed_minutes: int = 5` — tempo narrativo trascorso (0 = puro dialogo, 5-15 = esplorazione, 60 = viaggio breve, 480 = riposo lungo)
  6. `companion_actions: list[CompanionAction]`
  7. `world_updates: list[WorldUpdate]` — ultimi, sono i più pesanti
  8. `suggested_actions: list[str]`
  9. `ambient_detail: Optional[str]`
  10. `scene_image_prompt: Optional[str]` — per v2
- [x] Campo `scene_mood` come enum vincolato (calm_exploration, tense_anticipation, combat_fury, ecc.)
- [x] Fallback a `neutral` se mood non valido o mancante
- [x] **Nota:** `requires_player_action` NON è un campo DM — è derivato deterministicamente dal backend (combat attivo o dice_required presente)
- [x] Healing Parser (`json-repair`) prima della validazione Pydantic per ridurre retry
- [x] Retry automatico (max 3) se JSON ancora malformato dopo healing
- [ ] Consistency checker per contraddizioni con world state

### 4.4 Streaming & WebSocket — Approccio A (Narration-First)
- [x] **Approccio A:** `NarrationExtractor` state machine estrae token-by-token il campo `narration` dallo stream raw, senza aspettare il JSON completo. Gli altri campi vengono parsati dopo lo stream con `json-repair` + Pydantic. Implementato in `app/ai/stream_extractor.py`.
- [x] WebSocket per streaming narrazione DM in tempo reale
- [x] Eventi DM: `dm:narration:start`, `dm:narration:chunk`, `dm:narration:end`
- [x] Eventi NPC (Actor-Director): `npc:dialogue` (singolo evento per NPC, non chunked — NPC producono 1-2 frasi)
- [x] Evento `dice:roll` per animazione dadi
- [x] Evento `companion:action` per reazioni companion
- [ ] Evento `save:auto` per notifica auto-save
- [x] TTFT target: < 500ms (testo che inizia ad apparire) — il proxy Vite con `ws: true` forward WebSocket upgrade correttamente
- [x] Zero costo extra streaming (una sola call LLM), provider agnostico (non dipende da Tool Calling nativo)

---

## 5. PERSONAGGIO

### 5.1 Creazione Personaggio
- [x] Creazione narrativa: il player descrive il concept, il DM genera la scheda
- [x] DM genera: nome, backstory, attributi, HP, abilità, inventario iniziale
- [x] Player può richiedere aggiustamenti via conversazione
- [x] DM integra backstory nel lore del mondo
- [ ] Selezione death mode: Ironman / Destino / Cronista

### 5.2 Attributi Core
- [ ] 6 attributi: STR, DEX, CON, INT, WIS, CHA
- [ ] Ogni attributo governa azioni specifiche
- [ ] Modificatori calcolati dagli attributi
- [ ] Adattamento al setting (fantasy → sci-fi → post-apo)

### 5.3 Progressione Classless
- [ ] Sistema proficiency-by-use: azioni ripetute accumulano XP per categoria
- [ ] Soglie che sbloccano nuove abilità / tecniche / bonus passivi
- [ ] Il DM offre scelte milestone ("vuoi specializzarti in X o Y?")
- [ ] Build ibride possibili (sword-mage, diplomatic assassin, ecc.)

---

## 6. NPC & COMPANION — Pattern Actor-Director

### 6.0 Actor-Director Pattern
Il DM è il **Regista** (Director). Gli NPC sono **Attori** indipendenti con la propria call LLM.

**Flusso:**
1. DM risponde con `invoke_npcs: ["Grenda", "Re Aldric"]`
2. Backend lancia le chiamate NPC in parallelo (`asyncio.gather`, budget model)
3. Frontend inizia a streammare la `narration` del DM
4. Mentre il player legge la narrazione (~2-3 sec), gli NPC generano
5. I dialoghi NPC arrivano direttamente alla UI via WebSocket (`npc:dialogue:*`)
6. I dialoghi NPC NON tornano mai al DM — vanno a schermo direttamente
7. Il turno finisce dopo i dialoghi NPC. Il DM riprende solo al turno successivo.

**Prompt per ogni NPC (budget model):**
- Nome, ruolo, professione, carattere e tratti di personalità
- Disposition attuale verso il player (valore numerico)
- Ultima interazione con il player (da `memory_facts`)
- Azione del player che ha innescato la risposta
- Istruzione: "Rispondi in 1-2 frasi, in character, con questa personalità."

**Vantaggi:** Ogni NPC ha voce distinta e imprevedibile. Il DM si sorprende delle risposte NPC → gameplay emergente autentico. Latenza percepita zero. Costo minimo (budget model, 1-2 frasi output).

### 6.1 NPC Psychology Model
- [x] Profilo NPC strutturato: nome, ruolo, tratti, valori, paure, segreti (`NPCProfile` Pydantic in `memory/schemas.py`)
- [x] Disposition system: valore numerico verso il player con modificatori (clamped -100 to +100, aggiornato via `npc_disposition` handler)
- [x] Goal system: ogni NPC ha obiettivi che possono allinearsi o confliggere col player (`goals: list[str]` in NPCProfile)
- [ ] Schedule system: NPC hanno routine (mattina → forge, sera → taverna) — alimentato dal GameClock (sez. 9.1)
- [ ] Memory per NPC: ricordano interazioni passate col player (via `memory_facts` filtrate per `entity_name`)
- [ ] Comportamento emergente basato su tutti i fattori sopra
- [x] NPC invocati dal DM via `invoke_npcs` → chiamata LLM indipendente (Actor-Director, `npc_director.py`)

### 6.2 Companion System
- [x] Tutto quello di NPC, più (`CompanionProfile` extends `NPCProfile`):
- [ ] Backstory completa con conflitti irrisolti
- [ ] Personal quest arc che si svela in base a fiducia ed eventi
- [x] Opinioni su altri companion (alleanze, rivalità) — `opinions: dict[str, str]` in CompanionProfile
- [x] Preferenze di combattimento e personalità tattica — `combat_style` in CompanionProfile
- [x] Loyalty meter che influenza obbedienza a ordini pericolosi — `loyalty` (0-100) in CompanionProfile, updated via `companion_loyalty` handler
- [ ] Reazioni emotive alle decisioni del player (approvazione/disapprovazione)
- [ ] Companion possono litigare, condividere storie, reagire all'ambiente
- [ ] Companion possono lasciare il party se loyalty troppo bassa
- [ ] Companion departed diventa NPC nel mondo (alleato, nemico, o neutrale)

---

## 7. COMBATTIMENTO

### 7.1 Combat System
- [x] Turn-based con ordine di iniziativa (d20 + DEX modifier) — calcolato server-side al `combat_start`
- [x] Free-text input accettato — DM adjudica via narrazione + typed world_updates
- [x] Danno applicato via `combat_damage` world_update (numero negativo = danno, positivo = cura)
- [x] HP system con soglia 0 HP → death mode rules (`check_player_death` in `core/death.py`)
- [ ] Player turn: 1 azione + 1 bonus action + movimento — non enforced meccanicamente (DM gestisce)

### 7.2 Combat AI per Nemici
- [ ] Comportamento AI basato sul tipo di creatura — delegato al DM via narrazione libera (v1)
- [ ] Nemici possono fuggire, arrendersi, chiamare rinforzi, negoziare — supportato via narrazione DM
- [ ] Companion agiscono con AI tattica — narrati dal DM, call separata in v2

### 7.3 Combat Tracker
- [x] Ordine iniziativa visuale — lista verticale con numero iniziativa
- [x] HP bar per tutti i partecipanti — color-coded (verde/giallo/rosso per soglie 50%/25%)
- [x] Indicatore di turno corrente — bordo rosso + sfondo evidenziato
- [x] Morti mostrati a opacità ridotta con strikethrough
- [x] Round counter nell'intestazione

---

## 8. MONDO & GENERAZIONE

### 8.1 World Generation — 3 Layer
- [ ] **Layer 1 — Template strutturale:** regioni, conflitto core, fazioni, NPC chiave, progressione
- [ ] **Layer 2 — Procedurale (AI):** nomi, lore, culture, NPC specifici, quest seed, economia, religione/magia
- [ ] **Layer 3 — Emergente (player-driven):** conseguenze in real-time, alleanze, distruzioni, reputazione

### 8.2 Campaign Templates
- [ ] Schema YAML validato (`templates/schema.json`)
- [ ] Almeno 3 template ufficiali:
  - [ ] **The Awakening** (tutorial, 30-45 min)
  - [ ] **The Shattered Crowns** (political fantasy)
  - [ ] **The Last Light** (dark fantasy survival)
- [ ] Template include: metadata, skeleton, DM style, lore seed, condizioni iniziali, parametri difficoltà
- [ ] Validazione a load-time, errori descrittivi se invalido
- [ ] Sanitizzazione campi testo template (anti-prompt-injection)
- [ ] Template condivisibili come directory (self-hosted)

### 8.3 DM Personality
- [ ] Almeno 3 stili DM implementati: Classic, Dramatic, Gritty
- [ ] Stile iniettato nel system prompt, influenza tono e narrazione

---

## 9. MEMORIA & PERSISTENZA — Architettura a 3 Pilastri

### 9.1 World State Object
- [x] JSON strutturato con sezioni: meta, player, companions, world, narrative, npcs, combat_state, destino_lives (schema v4, migration v0→v4)
- [x] Aggiornato dopo ogni turno
- [x] Schema versioning con migration pipeline (v1→v2→v3→v4)
- [ ] Caricamento selettivo basato su rilevanza (Contextual Loading guidato dal Semantic Resolver)
- [x] **GameClock** nel world state:
  ```
  GameClock: total_minutes, current_hour, current_day, current_season, time_of_day
  ```
  Alimentato da `time_passed_minutes` del DMResponse. Deriva ora/giorno/stagione automaticamente.
  Valori guida per il DM: dialogo 1-5 min, esplorazione 10-30 min, viaggio locale 30-60 min, viaggio tra zone 120-480 min, riposo breve 60 min, riposo lungo 480 min.
- [ ] **WorldSimulatorState** (schema in v1, logica in v2):
  ```
  WorldSimulatorState: enabled, last_simulated_turn, pending_world_events, scheduled_npc_actions
  ```
  Toggle utente nelle preferenze campagna. La logica v2 usa chiamate background a budget model per generare eventi off-screen.

### 9.2 Architettura Memoria a 3 Pilastri

**Pilastro 1 — Core State (sempre presente, ~1500 token fissi)**
- [ ] World State JSON caricato selettivamente per location/scena (Contextual Loading)
- [ ] Recap narrativo cumulativo (generato ogni 25 turni, 500-800 parole)
- [ ] Il Recap va SEMPRE nel system prompt come "bussola permanente" — non solo nel JournalView
- [ ] È il quadro generale: chi siamo, cosa stiamo facendo, dove siamo arrivati

**Pilastro 2 — Active Window (conversazione recente, ~2000 token)**
- [ ] Ultimi 5-8 turni verbatim (testo esatto input player + narrazione DM)
- [ ] Dà al DM il flow immediato della conversazione
- [x] Turni che escono dalla finestra vengono compressi (summary 2-3 frasi via budget model, batch di 5)

**Pilastro 3 — Fatti Atomici / RAG (dettagli puntuali dal passato, ~500 token)**
- [ ] Recupera dettagli specifici persi 20+ sessioni fa (nomi, segreti, promesse)
- [x] Granularità: singolo fatto atomico strutturato (tabella `memory_facts`, vedere sez. 13)
- [ ] Top 3-5 fatti iniettati nel prompt per turno via Hybrid Search
- [ ] Embedding model: Voyage AI API o locale (bge-small)

### 9.3 Fact Extractor (Background, Post-Turno)
- [x] Dopo ogni turno, `asyncio.create_task` (non bloccante, player non aspetta)
- [x] Budget model estrae 1-5 fatti atomici strutturati dal testo del turno
- [x] Formato: `"NomeEntità:tipo:stato — dettaglio con riferimento turno"`
- [x] Ogni fatto = una riga in `memory_facts` = un embedding
- [x] File: `backend/app/memory/fact_extractor.py`

### 9.4 Semantic Memory — Hybrid Search (pgvector + tsvector)
- [ ] Query ibrida: 70% similarità semantica (embedding `<=>`) + 30% keyword match (tsvector `ts_rank`)
- [ ] Filtri metadata: `entity_name` (NPC attivi in scena), `entity_type` (location corrente, quest sempre)
- [ ] Il Semantic Resolver (sez. 4.1) produce gli input per le query (target_npcs, target_locations)
- [ ] Top-5 fatti iniettati nella sezione Memory Context del prompt

### 9.5 Context Assembler (`ai/context.py`)
- [ ] Usa output del Semantic Resolver come guida primaria + regole fisse come fallback
- [ ] Carica = NPC(location corrente) + NPC(risolti da Semantic Resolver) + Companion(attivi)
- [ ] Assembla prompt DM con sezioni ordinate per priorità:
  1. System prompt (statico per campagna) + **Recap cumulativo** (bussola permanente)
  2. World context (dinamico, Contextual Loading guidato da Semantic Resolver)
  3. Character context (sempre caricato)
  4. Scene context (dinamico, alta priorità)
  5. Memory context (Pilastro 3: fatti atomici da hybrid search)
  6. Active Window (Pilastro 2: ultimi 5-8 turni verbatim)
  7. Player action (turno corrente)
- [ ] Token budget management: ~12,500-15,500 token per turno

### 9.6 Recap System — Ruolo Duale
- [ ] **Ruolo 1 — System Prompt (critico):** Il recap più recente viene iniettato nel system prompt del DM come bussola permanente a ogni turno. Non è opzionale — è il modo in cui il DM mantiene il quadro generale. Token budget: ~600-700 token, non va mai rimosso per fare spazio.
- [ ] **Ruolo 2 — JournalView (UI):** Il recap è visibile al player come sommario narrativo dell'avventura.
- [ ] Trigger: ogni 25 turni, budget model legge ultimi 25 turni + recap precedente → nuovo recap cumulativo 500-800 parole
- [ ] Recap vecchio archiviato (per JournalView), nuovo sostituisce quello nel system prompt

---

## 10. DEATH SYSTEM

### 10.1 Ironman
- [x] Morte permanente a 0 HP — `check_player_death()` ritorna `action="dead"`
- [x] Morte = campagna terminata (`campaign.status = COMPLETED`), DM narra epilogo
- [x] DM riceve istruzione "no mercy" via `DEATH_MODE_PROMPTS["ironman"]`
- [ ] Death saving throws (3 turni, nat1/nat20 rules) — semplificato a morte diretta per v1, rinviato a v2

### 10.2 Destino
- [x] 3 fate interventions disponibili (`destino_lives` top-level nel world_state v4)
- [x] Costi escalanti per intervento:
  - 1° (Minor): perdita oggetto / scar / debito
  - 2° (Major): companion in pericolo / stat reduction / memoria persa
  - 3° (Severe): companion morto / anima compromessa / mondo cambia irreversibilmente
- [x] `destino_lives` decrementato nel world state dopo ogni intervento
- [x] A 0 interventi rimasti → morte permanente (come Ironman)
- [x] DM riceve `cost_hint` specifico per numero intervento nella `narrative_instruction`
- [x] Frontend mostra overlay "Fate Intervenes!" viola con cost_hint

### 10.3 Cronista
- [x] Player non può morire: a 0 HP → `hp.current = 1` (modificato direttamente in `check_player_death`)
- [x] DM narra momento drammatico di quasi-morte con conseguenze narrative
- [x] Sconfitta = cattura, ritirata, perdita equipaggiamento — mai morte
- [x] Frontend mostra overlay "Near Death!" giallo con pulsante Continue
- [ ] Companion non muoiono: a 0 HP → unconscious — non enforced meccanicamente per v1

---

## 11. SAVE SYSTEM

### 11.1 Auto-Save
- [ ] Dopo ogni turno, sovrascrive un singolo slot auto-save — trigger post-turno mancante (Phase D)
- [ ] Trasparente: il player non lo vede/gestisce
- [ ] Al login, la campagna riprende dall'auto-save — Phase D

### 11.2 Manual Save
- [x] Endpoint `POST /api/campaigns/:id/saves` funzionante
- [x] Blocco durante combattimento attivo (`combat_state.active` check in `saves.py`, HTTP 400)
- [ ] Save browser nel frontend — Phase D
- [ ] Preview di un save — Phase D

### 11.3 Timeline Forking
- [x] Endpoint `POST /api/campaigns/:id/saves/:save_id/load` funzionante (crea fork)
- [x] Fork tracciato via `parent_save_id` nel Campaign model
- [ ] UI forking nella lista campagne — Phase D

---

## 12. FRONTEND

### 12.1 Layout Principale
- [ ] **Narrative Panel (centro):** streaming narrazione DM, dadi, dialoghi companion
- [ ] **Character Panel (sidebar sinistra, collapsibile):** scheda personaggio, inventario, quest attive
- [ ] **World Panel (sidebar destra, collapsibile):** mini-mappa, posizione, ora, meteo
- [ ] **Input Bar (bottom):** free-text + bottone invio
- [ ] **Quick Actions (sopra input):** bottoni contestuali (Attack, Persuade, Search, Rest)
- [ ] **Companion Bar (sopra input):** portrait companion con indicatore mood

### 12.2 Componenti UI Chiave
- [x] **NarrativeStream:** typewriter effect, rich text, dadi embedded, dialoghi companion
- [x] **DiceRoller:** animazione d20 spin, color-coded (rosso fail, verde success, oro crit), suono
- [x] **CharacterSheet:** attributi, abilità, inventario, quest log, relazioni
- [ ] **CompanionPanel:** ritratto, personalità, loyalty bar, storia conversazioni, quest personale
- [x] **CombatTracker:** ordine iniziativa, HP bar color-coded, indicatore turno corrente, round counter, morti con strikethrough (`combat-tracker.tsx`)
- [ ] **ActionSuggester:** bottoni contestuali basati sulla scena
- [ ] **JournalView:** log avventura cercabile, organizzato per sessione, con recap
- [ ] **APIKeyConfig:** pannello gestione chiavi API + test connection
- [ ] **MaturitySettings:** Standard / Mature / Unrestricted per campagna
- [ ] **CostDashboard:** costo per turno, sessione, mese, breakdown per provider

### 12.3 Responsive & PWA
- [ ] Desktop: tutti e 3 i pannelli visibili simultaneamente
- [ ] Tablet: sidebar overlay
- [ ] Mobile: navigazione a tab (narrative / character / world)
- [ ] Input bar sempre visibile e accessibile
- [ ] PWA installabile

### 12.4 Suoni
- [x] Suono tiro dadi
- [ ] Suoni ambientali legati a `scene_mood` (taverna, foresta, combattimento, pioggia)
- [ ] Suoni UI feedback (turno inviato, save completato)

---

## 13. DATABASE

### 13.1 Modelli Core
- [ ] **User:** id, email, name, password_hash, role, api_keys_encrypted, preferences, language
- [ ] **Campaign:** id, user_id, template_id, name, world_state (JSONB), turn_count, death_mode, maturity_level, status, parent_save_id
- [ ] **Turn:** id, campaign_id, turn_number, player_input, dice_rolls, dm_response (JSON), world_delta, summary, embedding (pgvector), ai_cost, timestamp
- [ ] **MemoryFact:** id (uuid), campaign_id (FK → campaigns), turn_number, entity_name (es. "Grenda"), entity_type ("npc" | "location" | "quest" | "item" | "event" | "secret"), content (fatto atomico in linguaggio naturale), embedding (vector 1536, pgvector), search_vector (tsvector per full-text search ibrido), created_at
- [ ] **SavePoint:** id, campaign_id, user_id, world_state (JSON snapshot), turn_number, label, scene_summary, is_auto
- [ ] **Template:** id, slug, name, genre, description, skeleton (JSON), dm_style, author, is_official, version
- [ ] **Achievement:** id, user_id, achievement_key, unlocked_at, campaign_id
- [ ] **PlayerStats:** user_id, total_turns, total_campaigns, total_play_time_minutes, total_dice_rolled, total_critical_successes, total_critical_failures, total_companions_recruited, total_companion_deaths, total_player_deaths

### 13.3 World State — Schemi Aggiuntivi (JSONB)
- [x] **GameClock:** total_minutes, current_hour (derivato), current_day (derivato), current_season (derivato), time_of_day ("dawn" | "morning" | "afternoon" | "evening" | "night" | "midnight")
- [ ] **WorldSimulatorState:** enabled (default false), last_simulated_turn, pending_world_events (list[dict]), scheduled_npc_actions (list[dict]) — schema in v1, logica in v2

### 13.2 Migrazioni
- [ ] SQLAlchemy 2.0 async + Alembic
- [ ] World State schema versioning + migration pipeline per contenuto JSONB

---

## 14. API REST

### 14.1 Endpoints
- [ ] `POST /api/auth/register` — Registra utente
- [ ] `POST /api/auth/login` — Login, ritorna JWT
- [ ] `POST /api/auth/refresh` — Refresh token
- [ ] `GET /api/campaigns` — Lista campagne utente
- [ ] `POST /api/campaigns` — Crea campagna (seleziona template, genera mondo)
- [ ] `GET /api/campaigns/:id` — Carica stato campagna
- [ ] `POST /api/campaigns/:id/turn` — Invia azione, ricevi risposta DM
- [ ] `GET /api/campaigns/:id/character` — Scheda personaggio
- [ ] `PUT /api/campaigns/:id/character` — Aggiorna personaggio (level-up)
- [ ] `GET /api/campaigns/:id/journal` — Journal / event log
- [ ] `GET /api/campaigns/:id/map` — Dati mappa mondo conosciuto
- [ ] `GET /api/campaigns/:id/saves` — Lista save point
- [ ] `POST /api/campaigns/:id/saves` — Crea manual save
- [ ] `POST /api/campaigns/:id/saves/:save_id/load` — Carica save (fork)
- [ ] `DELETE /api/campaigns/:id` — Cancella campagna
- [ ] `GET /api/templates` — Lista template disponibili
- [ ] `GET /api/settings` — Preferenze utente + config provider
- [ ] `PUT /api/settings` — Aggiorna preferenze
- [ ] `PUT /api/settings/api-keys` — Salva chiavi API criptate
- [ ] `POST /api/export` — Esporta dati utente (GDPR)
- [ ] `POST /api/import` — Importa dati esportati

---

## 15. SICUREZZA & PRIVACY

- [ ] JWT httpOnly cookies, no cookie terze parti
- [ ] CORS configurato
- [ ] Rate limiting in-memory (`asyncio.Lock` per campaign ID) — Redis in v2 SaaS
- [x] **Content Policy Handler:** intercetta `content_policy_violation` nel provider layer, distingue errore tecnico da blocco policy nel log, ritorna messaggio leggibile al player
- [ ] Configurazione MaturityLevel nel system prompt DM:
  - **Standard:** Violenza fantasy OK, romanticismo implicito, atti sessuali → fade to black
  - **Mature:** Violenza più esplicita, romanticismo diretto non pornografico (provider-dependent)
  - **Unrestricted:** Solo con provider locale (Ollama) — backend blocca se provider è cloud
- [ ] Data export/import per GDPR
- [ ] Right to deletion (cascade delete)
- [ ] Telemetry disabled by default (opt-in)
- [ ] No tracking pixel, no analytics terze parti

---

## 16. INTERNAZIONALIZZAZIONE

- [ ] react-i18next con file JSON locale
- [ ] Tutte le stringhe UI esternalizzate (no hardcoded)
- [ ] Direttiva lingua nel system prompt DM
- [ ] Lingua utente salvata nel profilo
- [ ] Default: English
- [ ] Struttura pronta per future lingue (it, de, fr, es)

---

## 17. TESTING

- [x] Unit test: dice engine, world state (v4), sanitizer, parser, combat handlers, death system — **230 unit tests passing**
- [ ] Unit test: progression, encryption (Phase D)
- [ ] Integration test: turn pipeline (con AI mockato), memory, auth, campaign CRUD, export
- [ ] Playtest bot: gioca autonomamente per regression testing
- [ ] Consistency checker: verifica integrità world state post-turno
- [ ] Quality scorer: valuta ripetitività, coerenza, engagement della narrazione AI
- [ ] Frontend: Vitest per store/hooks, React Testing Library per componenti, Playwright per E2E

---

## 18. DOCUMENTAZIONE

- [ ] README.md con quick start
- [ ] INSTALL.md con guida Docker dettagliata
- [ ] ARCHITECTURE.md con overview tecnica
- [ ] CONTRIBUTING.md con guida per contributori
- [ ] TEMPLATE_SDK.md con guida creazione template
- [ ] API.md con documentazione endpoint
- [ ] TROUBLESHOOTING.md con problemi comuni

---

## NOTE

**Cosa NON è nella v1 (rimandato a v2+):**
- Image generation (scene illustrations)
- Multiplayer / co-op
- Battle maps visive con token (à la Friends & Fables)
- Enterprise features (SSO, LDAP, white-labeling)
- Template marketplace
- Mobile app nativa
- Suoni ambientali avanzati (v1 ha suoni base)
- Custom scenarios da descrizione libera
- Redis (rate limiting e session cache — sostituito da asyncio.Lock in v1)
- World Simulator logica (schema in v1, logica completa in v2)

**Target v1:** Un'esperienza single-player text-first completa, self-hostabile con Docker, che rivaleggia con NeverEndingQuest in profondità meccanica e supera Friends & Fables in apertura e trasparenza.
