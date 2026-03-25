# SAGA v1 — Specifiche Complete per il Lancio

**Obiettivo:** Friends & Fables self-hostabile, open source, con API keys proprie o modelli locali.

**Architettura target:** React + FastAPI + PostgreSQL (pgvector) + Redis + Docker

---

## 1. INFRASTRUTTURA & SETUP

### 1.1 Docker & Deployment
- [ ] Docker Compose con tutti i servizi (frontend, backend, PostgreSQL, Redis)
- [ ] `docker compose up -d` funzionante da zero
- [ ] File `.env.example` con tutte le variabili documentate
- [ ] PostgreSQL 16+ con estensione pgvector abilitata
- [ ] Redis per session cache e rate limiting
- [ ] Script di primo avvio (creazione admin, migration DB)

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
- [ ] Selezione automatica del modello in base al tipo di modulo (DM, NPC, companion, world sim)
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
- [ ] Context Assembler costruisce il prompt DM
- [ ] Dice Engine tira dadi se necessario pre-prompt
- [ ] AI Engine invia prompt al LLM via Router, streaming risposta
- [ ] Response Parser estrae JSON strutturato dalla risposta DM
- [ ] Se il DM richiede un tiro di dado, il Dice Engine tira e ri-prompta per la narrazione
- [ ] World State Updater applica i world_updates
- [ ] Memory Manager comprime turni vecchi se necessario
- [ ] Auto-save del world state
- [ ] Turno persistito nel DB con delta e costo AI
- [ ] World Simulator esegue eventi off-screen (asincrono)

### 4.2 Dice Engine
- [ ] Meccanica d20 base: d20 + stat modifier + bonus vs DC
- [ ] Risultati graduali: Natural 1 / Hard Fail / Soft Fail / Partial / Full / Nat 20
- [ ] Vantaggio e svantaggio (2d20 take high/low)
- [ ] Il DM decide quando tirare (trivial → auto success, impossible → auto fail)
- [ ] Roll calcolato server-side, animazione client-side
- [ ] Dadi mostrati al player con risultato trasparente

### 4.3 DM Output Strutturato
- [ ] Risposta DM in JSON con campi: `narration`, `dice_required`, `companion_actions`, `world_updates`, `scene_mood`, `suggested_actions`, `ambient_detail`
- [ ] Campo `scene_mood` come enum vincolato (calm_exploration, tense_anticipation, combat_fury, ecc.)
- [ ] Fallback a `neutral` se mood non valido o mancante
- [ ] Retry automatico (max 3) se JSON malformato
- [ ] Consistency checker per contraddizioni con world state

### 4.4 Streaming & WebSocket
- [ ] WebSocket per streaming narrazione DM in tempo reale
- [ ] Eventi: `dm:narration:start`, `dm:narration:chunk`, `dm:narration:end`
- [ ] Evento `dice:roll` per animazione dadi
- [ ] Evento `companion:action` per reazioni companion
- [ ] Evento `save:auto` per notifica auto-save
- [ ] TTFT target: < 500ms (testo che inizia ad apparire)

---

## 5. PERSONAGGIO

### 5.1 Creazione Personaggio
- [ ] Creazione narrativa: il player descrive il concept, il DM genera la scheda
- [ ] DM genera: nome, backstory, attributi, HP, abilità, inventario iniziale
- [ ] Player può richiedere aggiustamenti via conversazione
- [ ] DM integra backstory nel lore del mondo
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

## 6. NPC & COMPANION

### 6.1 NPC Psychology Model
- [ ] Profilo NPC strutturato: nome, ruolo, tratti, valori, paure, segreti
- [ ] Disposition system: valore numerico verso il player con modificatori
- [ ] Goal system: ogni NPC ha obiettivi che possono allinearsi o confliggere col player
- [ ] Schedule system: NPC hanno routine (mattina → forge, sera → taverna)
- [ ] Memory per NPC: ricordano interazioni passate col player
- [ ] Comportamento emergente basato su tutti i fattori sopra

### 6.2 Companion System
- [ ] Tutto quello di NPC, più:
- [ ] Backstory completa con conflitti irrisolti
- [ ] Personal quest arc che si svela in base a fiducia ed eventi
- [ ] Opinioni su altri companion (alleanze, rivalità)
- [ ] Preferenze di combattimento e personalità tattica
- [ ] Loyalty meter che influenza obbedienza a ordini pericolosi
- [ ] Reazioni emotive alle decisioni del player (approvazione/disapprovazione)
- [ ] Companion possono litigare, condividere storie, reagire all'ambiente
- [ ] Companion possono lasciare il party se loyalty troppo bassa
- [ ] Companion departed diventa NPC nel mondo (alleato, nemico, o neutrale)

---

## 7. COMBATTIMENTO

### 7.1 Combat System
- [ ] Turn-based con ordine di iniziativa (d20 + DEX modifier)
- [ ] Player turn: 1 azione + 1 bonus action + movimento
- [ ] Free-text input accettato ("mi lancio dal lampadario e calcio la guardia")
- [ ] DM adjudica azioni creative con tiri e modificatori appropriati
- [ ] Danno calcolato: arma/spell + stat modifier + roll
- [ ] HP system con soglia 0 HP → death mode rules

### 7.2 Combat AI per Nemici
- [ ] Comportamento AI basato sul tipo di creatura (undead → carica, goblin → hit-and-run)
- [ ] Nemici possono fuggire, arrendersi, chiamare rinforzi, negoziare
- [ ] Companion agiscono nei propri turni con AI tattica

### 7.3 Combat Tracker
- [ ] Ordine iniziativa visuale
- [ ] HP bar per tutti i partecipanti
- [ ] Indicatore di turno corrente

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

## 9. MEMORIA & PERSISTENZA

### 9.1 World State Object
- [ ] JSON strutturato con sezioni: meta, player, companions, world, narrative, npcs
- [ ] Aggiornato dopo ogni turno
- [ ] Schema versioning con migration pipeline (v1→v2→v3)
- [ ] Caricamento selettivo basato su rilevanza (non tutto in ogni prompt)

### 9.2 Memory Compression — 4 Tier
- [ ] **Immediate:** ultimi 5-10 turni, verbatim
- [ ] **Recent:** ultimi 20-50 turni, riassunti
- [ ] **Long-term:** intera campagna, fatti di alto livello
- [ ] **Permanent:** mai compressi (morti, tradimenti, cambiamenti mondo)
- [ ] Compressione eseguita periodicamente (ogni ~10 turni)

### 9.3 Semantic Memory (pgvector)
- [ ] Dopo ogni turno, summary convertito in embedding
- [ ] Embedding salvato con il record strutturato in PostgreSQL
- [ ] Context Assembler fa query parallele: strutturata + semantica
- [ ] Top-K eventi semanticamente rilevanti iniettati nel memory context del prompt
- [ ] Embedding model: Voyage AI API o locale (bge-small)

### 9.4 Context Assembler (`ai/context.py`)
- [ ] Assembla prompt DM con 6 sezioni ordinate per priorità:
  1. System prompt (statico per campagna)
  2. World context (dinamico, per rilevanza)
  3. Character context (sempre caricato)
  4. Scene context (dinamico, alta priorità)
  5. Memory context (tiered loading)
  6. Player action (turno corrente)
- [ ] Token budget management: ~12,500-15,500 token per turno

### 9.5 Recap System
- [ ] Generazione automatica ogni 20-30 turni
- [ ] Recap iniettato nel memory context del prompt DM
- [ ] Recap visibile nel journal come "story so far"
- [ ] Generato con budget model (GPT-4o-mini / Gemini Flash)
- [ ] 500-1000 parole, organizzato per arco narrativo

---

## 10. DEATH SYSTEM

### 10.1 Ironman
- [ ] 0 HP → dying state → death saving throws (3 success = stabilize, 3 fail = morte)
- [ ] Morte = campagna terminata, DM narra epilogo
- [ ] Companion morti permanentemente in combattimento
- [ ] DM non riduce mai danno segretamente, no mercy rolls

### 10.2 Destino
- [ ] Come Ironman, ma 3 fate interventions disponibili
- [ ] Ogni intervento ha un costo escalante:
  - 1° (Minor): perdita oggetto / -1 attributo / debito narrativo
  - 2° (Major): companion si sacrifica / -2 attributo / fazione distrutta
  - 3° (Severe): due costi Major combinati
- [ ] Costi permanenti e meccanicamente misurabili
- [ ] A 0 interventi rimasti → morte permanente (come Ironman)
- [ ] Conteggio in `world_state.player.destino_lives_remaining`

### 10.3 Cronista
- [ ] Player non può morire: a 0 HP → ridotto a 1 HP
- [ ] DM narra momento drammatico di quasi-morte
- [ ] Sconfitta = cattura, ritirata, perdita equipaggiamento — mai morte
- [ ] Companion non muoiono: a 0 HP → unconscious, recuperano dopo combattimento
- [ ] Companion possono comunque lasciare il party per loyalty bassa

---

## 11. SAVE SYSTEM

### 11.1 Auto-Save
- [ ] Dopo ogni turno, sovrascrive un singolo slot auto-save
- [ ] Trasparente: il player non lo vede/gestisce
- [ ] Al login, la campagna riprende dall'auto-save

### 11.2 Manual Save
- [ ] Player può creare save nominati in qualsiasi momento (fuori dal combattimento)
- [ ] Save browser con: label, turno, data in-game, scene summary, timestamp
- [ ] Preview di un save: summary + stats chiave senza caricarlo
- [ ] Illimitati nel self-hosted

### 11.3 Timeline Forking
- [ ] Caricare un save crea una nuova campagna (fork), non sovrascrive
- [ ] Campagna originale resta intatta
- [ ] Fork tracciato via `parent_save_id` nel Campaign model
- [ ] Entrambe le timeline visibili nella lista campagne, collegate visivamente

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
- [ ] **NarrativeStream:** typewriter effect, rich text, dadi embedded, dialoghi companion
- [ ] **DiceRoller:** animazione d20 spin, color-coded (rosso fail, verde success, oro crit), suono
- [ ] **CharacterSheet:** attributi, abilità, inventario, quest log, relazioni
- [ ] **CompanionPanel:** ritratto, personalità, loyalty bar, storia conversazioni, quest personale
- [ ] **CombatTracker:** ordine iniziativa, HP bar, indicatore turno
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
- [ ] Suono tiro dadi
- [ ] Suoni ambientali legati a `scene_mood` (taverna, foresta, combattimento, pioggia)
- [ ] Suoni UI feedback (turno inviato, save completato)

---

## 13. DATABASE

### 13.1 Modelli Core
- [ ] **User:** id, email, name, password_hash, role, api_keys_encrypted, preferences, language
- [ ] **Campaign:** id, user_id, template_id, name, world_state (JSONB), turn_count, death_mode, maturity_level, status, parent_save_id
- [ ] **Turn:** id, campaign_id, turn_number, player_input, dice_rolls, dm_response (JSON), world_delta, summary, embedding (pgvector), ai_cost, timestamp
- [ ] **SavePoint:** id, campaign_id, user_id, world_state (JSON snapshot), turn_number, label, scene_summary, is_auto
- [ ] **Template:** id, slug, name, genre, description, skeleton (JSON), dm_style, author, is_official, version
- [ ] **Achievement:** id, user_id, achievement_key, unlocked_at, campaign_id
- [ ] **PlayerStats:** user_id, total_turns, total_campaigns, total_play_time_minutes, total_dice_rolled, total_critical_successes, total_critical_failures, total_companions_recruited, total_companion_deaths, total_player_deaths

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
- [ ] Rate limiting (Redis)
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

- [ ] Unit test: dice engine, world state, sanitizer, parser, combat, progression, encryption, save
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

**Target v1:** Un'esperienza single-player text-first completa, self-hostabile con Docker, che rivaleggia con NeverEndingQuest in profondità meccanica e supera Friends & Fables in apertura e trasparenza.
