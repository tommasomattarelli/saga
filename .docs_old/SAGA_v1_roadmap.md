# SAGA v1 — Roadmap Dettagliata Next Steps

**Stato attuale:** Alpha giocabile (~65% della v1 completato) — Fase A+B+C+Sprint1+Sprint2 complete
**Obiettivo:** Da chatbot narrativo → gioco RPG completo self-hostabile
**Timeline stimata:** 10-14 settimane full-time (20-28 part-time)

---

## Stato attuale — Cosa c'è già

### ✅ Completato
- Docker Compose full stack (frontend, backend, PostgreSQL + pgvector) — ora con `.dockerignore`, build <25s
- Auth JWT completo (register, login, refresh, bcrypt)
- DB models: User, Campaign, Turn, SavePoint, Template, PlayerStats
- SQLAlchemy 2.0 async + Alembic migrations + World State schema versioning (v0→v4)
- La maggior parte delle API REST
- Sicurezza base: JWT httpOnly, CORS, cascade delete, no tracking
- In-memory `asyncio.Lock()` per campaign ID (race condition prevention — Redis rinviato a v2)
- i18n framework (react-i18next, stringhe esternalizzate, direttiva lingua DM)
- Input sanitizer + prompt injection detection (`ai/sanitizer.py`, `detect_injection()`)
- **WebSocket per streaming narrazione token-by-token** (`NarrationExtractor`, `process_game_turn_streaming()`)
- **Turn persistence via WebSocket** — turni salvati nel DB con summary + embedding + auto-save
- Frontend: Narrative Panel, Character Panel (sidebar), ActionSuggester — **239 unit tests passing**
- **DMResponse Pydantic schema** — 11 `scene_mood`, `invoke_npcs`, `time_passed_minutes`, `character_generation`
- **Healing Parser** — strip fences → `json-repair` → Pydantic validation → fallback
- **Content Policy Handler** — per-provider detection (OpenAI/Anthropic/Google)
- **Dice Engine 6 livelli** — critical_failure → critical_success, advantage/disadvantage, re-prompt
- **GameClock** — Pydantic computed fields, advance ogni turno, migrazione world state v4
- **Scene moods CSS** — 11 mood, CSS custom properties, transizioni 1.5s
- **World State v4** — `combat_state` + `destino_lives`, migration pipeline v0→v4
- **Typed World Updater** — 11 handler (combat_start, combat_damage, combat_end, location + 7 base)
- **Death System** — `core/death.py`, tutti e 3 i modi (Cronista/Destino/Ironman)
- **Combat System** — DM-driven via typed world_updates, `COMBAT_PROMPT`, WebSocket events
- **CombatTracker UI** — overlay fisso, HP bar, ordine iniziativa, round counter, turn advance
- **Death overlays** — Near Death / Fate Intervenes / You Have Fallen
- **Save guard** — blocco manual save durante combattimento attivo
- **Character creation UI** (Sprint 1) — form 3 step: template → nome → classe/stats, no AI call
- **HP nested format** — `{"current": N, "max": N}` ovunque, `getHP()` helper nel frontend
- **Chat history** — idratata da `campaign.turns` al mount (Sprint 2)
- **User message bubbles** — `pendingAction` bubble + `player_action` nei turni storici (Sprint 2)
- **Auto-scroll** — `bottomRef.scrollIntoView` su ogni chunk narrazione (Sprint 2)
- **Dice sotto narrazione** — `DiceRoller` spostato dopo il testo (Sprint 2)
- **WebSocket isMounted guard** — guard su tutti gli handler, cleanup corretto (Sprint 2)
- **Error handler WS** — `ws.on("error")` resetta processing (Sprint 2)
- **Back button** — `←` nell'header, naviga a `/` (Sprint 2)
- **Season nell'header** — `meta.current_season` mostrato (Sprint 2)
- **Location handler** — `_handle_location()` in updater.py con log (Sprint 2)
- **Engine split** — `engine.py` (50), `turn.py` (177), `streaming.py` (294) — tutti <300 righe (Sprint 2)
- **AI request logging** — provider, model, system_prompt_preview, messages_count
- **File logging** — structlog dual output: console + `logs/saga.log` JSON rotante

### ⚠️ Parziale / Da rifinire in playtest
- Il DM a volte non emette combat_damage spontaneamente — monitorare con log
- Contextual Loading guidato dal Semantic Resolver — resolver pronto, loading selettivo in Phase E
- Template System avanzato — templates funzionanti parzialmente, pieno sistema in Phase E

### ❌ Non iniziato
- Hybrid Search semantico (pgvector + tsvector query) — tabella e indici pronti, query in Phase E
- World generation procedurale
- CI/CD
- Toggle suono on/off
- Companion Bar nel frontend (solo icone placeholder)
- Auto-save UI / resume al login
- Save Browser UI nel frontend (Phase E)
- Timeline forking UI nella lista campagne (Phase E)
- Death saving throws Ironman (3 turni, nat1/nat20 rules → v2)
- API Keys UI nel frontend (Phase E)
- Cost Dashboard (Phase E)
- **Phase D: Agentic DM** (tool-calling architecture — prossimo sprint)

---

## FASE A — "Da chatbot a gioco" (2-3 settimane)

> **Obiettivo:** Dopo questa fase, un playtester dice "sto giocando un RPG", non "sto chattando con un AI".

---

### A1. DM Output Strutturato

**Perché prima:** È il prerequisito di tutto. Senza output strutturato, non puoi separare narrazione da meccaniche, non puoi triggerare dadi dal server, non puoi aggiornare il world state automaticamente.

**Task:**

**A1.1 — Definire lo schema JSON di risposta DM**

Crea il file `backend/app/ai/schemas/dm_response.py` con un Pydantic model:

```python
class DiceRequest(BaseModel):
    check: str                    # "persuasion", "stealth", "attack", ecc.
    dc: int                       # difficulty class
    stat: str                     # "CHA", "DEX", "STR", ecc.
    advantage: bool = False
    disadvantage: bool = False
    reason: str                   # "The guard is suspicious"

class CompanionAction(BaseModel):
    name: str
    action: str                   # "whispers", "attacks", "warns", ecc.
    dialogue: Optional[str] = None

class WorldUpdate(BaseModel):
    type: str                     # "npc_disposition", "faction_event", "quest_update", ecc.
    target: str                   # nome NPC, fazione, quest
    change: Any                   # valore numerico, stringa, ecc.
    description: str              # descrizione leggibile dell'update

class DMResponse(BaseModel):
    # ORDINE CAMPI CRITICO per streaming (narration-first, Approccio A)
    narration: str                # 1° — streammato subito al frontend
    invoke_npcs: list[str] = []   # 2° — trigger Actor-Director appena arriva
    dice_required: Optional[DiceRequest] = None
    scene_mood: str = "neutral"   # enum vincolato
    time_passed_minutes: int = 5  # tempo narrativo: 0=dialogo, 5-15=esplora, 60=viaggio, 480=riposo
    companion_actions: list[CompanionAction] = []
    world_updates: list[WorldUpdate] = []  # ultimi, i più pesanti
    suggested_actions: list[str] = []  # max 4 suggerimenti
    ambient_detail: Optional[str] = None
    scene_image_prompt: Optional[str] = None  # per v2
    # NOTA: requires_player_action NON è un campo DM — derivato dal backend
```

**A1.2 — Aggiornare il system prompt del DM**

Nel file dei prompt (`backend/app/ai/prompts/dm.py`), aggiungere le istruzioni di formato output. Il DM DEVE rispondere SOLO con JSON valido seguendo lo schema. Includere:
- Lo schema come esempio nel prompt, con **`narration` come primo campo** (critico per streaming Approccio A)
- L'ordine campi esatto: narration → invoke_npcs → dice_required → scene_mood → time_passed_minutes → companion_actions → world_updates → suggested_actions → ambient_detail
- L'enum completo di `scene_mood`: `calm_exploration`, `tense_anticipation`, `combat_fury`, `stealth_danger`, `social_intrigue`, `melancholic_reflection`, `triumphant_victory`, `dread_horror`, `wonder_discovery`, `mourning_loss`, `neutral`
- Regole su quando popolare `dice_required` vs lasciarlo null
- Regole su quando generare `companion_actions`
- Regole su `invoke_npcs`: il DM decide chi parla in questa scena (trigger per Actor-Director)
- Valori guida per `time_passed_minutes`: dialogo 1-5 min, esplorazione stanza 10-30 min, viaggio locale 30-60 min, viaggio tra zone 120-480 min, riposo breve 60 min, riposo lungo 480 min

**A1.3 — Healing Parser + Response Parser**

`backend/app/ai/parser.py` — deve:
- **Healing pipeline** (prima della validazione): strip markdown fences (` ```json ... ``` `) → `json-repair` library → Pydantic validation → retry solo se ancora invalido. Riduce retry costosi del ~70%.
- Parsare il JSON dalla risposta LLM
- Validare contro il Pydantic model
- Se `scene_mood` non è nell'enum → fallback a `"neutral"`
- Se campi mancanti → default values
- Se JSON malformato dopo healing → retry (max 3)
- Loggare warning per campi inattesi

**A1.3b — Content Policy Handler**

Nel provider layer (`backend/app/ai/providers/`):
- Intercettare specificamente errori `content_policy_violation` (HTTP 400 con flag moderazione)
- Ritornare messaggio leggibile al player: "The DM refuses to narrate this scene as described. Try rephrasing your action."
- Distinguere nel log tra "errore tecnico" e "blocco policy"
- Non trattare come errore generico / crash silenzioso

**A1.4 — Aggiornare il frontend per consumare il nuovo formato**

Il `NarrativeStream` deve:
- Renderizzare `narration` come testo principale
- Mostrare `companion_actions` come bolle di dialogo separate
- Mostrare `suggested_actions` come quick-action buttons
- Mostrare `ambient_detail` come testo in corsivo/secondario
- Applicare `scene_mood` come classe CSS al container (per ora solo colore di sfondo/bordo, i suoni vengono dopo)

**Criteri di completamento A1:**
- [x] Schema Pydantic definito con `invoke_npcs` e `time_passed_minutes`, testato
- [x] System prompt aggiornato con istruzioni formato e ordine campi per streaming
- [x] Healing Parser con `json-repair` integrato e testato
- [x] Content Policy Handler implementato nel provider layer
- [x] Parser aggiornato e testato con 10+ risposte reali
- [x] Frontend renderizza tutti i campi del nuovo formato
- [x] `scene_mood` cambia almeno il colore del bordo/sfondo del narrative panel
- [x] `suggested_actions` appaiono come bottoni cliccabili

---

### A2. Dice Engine Meccanico

**Perché ora:** Trasforma l'esperienza da "leggo una storia" a "gioco un gioco". Il momento in cui il dado rotola e il risultato è incerto è il core del TTRPG.

**Task:**

**A2.1 — Implementare il Dice Engine server-side**

`backend/app/core/dice.py`:

```python
import random

class DiceResult:
    roll: int           # valore grezzo del d20
    modifier: int       # stat modifier + bonus
    total: int          # roll + modifier
    dc: int             # target DC
    outcome: str        # "critical_failure" | "hard_failure" | "soft_failure" | "partial_success" | "full_success" | "critical_success"
    is_critical: bool   # nat 1 o nat 20
    advantage_rolls: Optional[list[int]] = None  # se advantage/disadvantage, entrambi i tiri

def roll_d20(stat_modifier: int, dc: int, advantage: bool = False, disadvantage: bool = False) -> DiceResult:
    # Tira 1d20 (o 2d20 per advantage/disadvantage)
    # Calcola outcome basato sulla tabella:
    #   Natural 1 → critical_failure (indipendentemente dal totale)
    #   Natural 20 → critical_success (indipendentemente dal totale)
    #   Total 2-5 sotto DC → hard_failure
    #   Total 1-4 sotto DC → soft_failure
    #   Total = DC o DC+1-3 → partial_success
    #   Total DC+4 o più → full_success
```

Nota: i range esatti vanno calibrati durante il playtest. La tabella nel GDD usa range assoluti (2-5, 6-9, ecc.), ma è meglio usare range relativi alla DC per rendere il sistema scalabile.

**A2.2 — Integrare il Dice Engine nel Turn Pipeline**

Modificare `backend/app/core/engine.py`:

```
FLUSSO AGGIORNATO:
1. Player invia azione
2. Sanitizer valida
3. Context Assembler costruisce prompt
4. AI Engine chiama LLM → riceve DMResponse
5. SE dice_required != null:
   a. Calcola stat_modifier dal character sheet
   b. Chiama roll_d20(modifier, dc, advantage, disadvantage)
   c. Invia DiceResult al client via WebSocket (evento dice:roll)
   d. Costruisci un follow-up prompt:
      "The player attempted [check]. They rolled [roll] + [modifier] = [total] vs DC [dc].
       Outcome: [outcome]. Narrate the result."
   e. AI Engine chiama LLM di nuovo → riceve narrazione del risultato
   f. Append narrazione risultato alla risposta
6. World State Updater applica world_updates
7. Persisti turno
```

**A2.3 — Animazione dadi nel frontend**

`frontend/src/components/DiceRoller.tsx`:
- Componente che riceve l'evento WebSocket `dice:roll`
- Animazione: dado 3D semplificato (può essere anche 2D con rotazione CSS) che si ferma sul numero
- Color coding: rosso per failure, verde per success, oro per critical
- Suono: un singolo file audio di dado che rotola (trovare un sound effect libero)
- Mostra: "[Persuasion Check] 🎲 14 + 3 = 17 vs DC 15 → Success!"
- L'animazione dura ~1.5 secondi, poi la narrazione del risultato inizia a streamare

**A2.4 — Condizionare il DM su quando chiedere tiri**

Nel system prompt, aggiungere regole chiare:
- Azioni triviali (camminare, parlare, raccogliere oggetti) → `dice_required: null`, successo automatico narrato
- Azioni impossibili (saltare sulla luna) → `dice_required: null`, fallimento narrato con spiegazione
- Azioni con esito incerto E posta in gioco → `dice_required` con check/DC/stat appropriati
- In combattimento: attacchi sempre con tiro, danni con formula
- Interazioni sociali: check Charisma vs disposition NPC

**A2.5 — Time Engine / GameClock**

Aggiungere al World State lo schema `GameClock`:

```python
class GameClock(BaseModel):
    total_minutes: int = 0          # accumulato da ogni turno
    current_hour: int = 8           # derivato: total_minutes // 60 % 24
    current_day: int = 1            # derivato: total_minutes // 1440
    current_season: str = "spring"  # derivato dai giorni
    time_of_day: str = "morning"    # "dawn|morning|afternoon|evening|night|midnight"
```

Il World State Updater legge `time_passed_minutes` dal DMResponse e aggiorna il clock dopo ogni turno. `current_hour`, `time_of_day`, `current_day` vengono ricalcolati automaticamente.

Il clock alimenta: descrizioni ambientali nel prompt, schedule NPC, ciclo giorno/notte nel World Panel, e il World Simulator in v2.

**A2.6 — requires_player_action (backend-derived)**

Non è un campo DM. Booleano calcolato dal backend:
- `True` se `world_state.combat_state.active` o `dm_response.dice_required is not None`
- `False` altrimenti → pulsante "Continua" abilitato, azione implicita `"wait"` se premuto senza input

**Criteri di completamento A2:**
- [x] Dice Engine implementato con tutti i 6 livelli di outcome
- [x] Vantaggio/svantaggio funzionante
- [x] Turn pipeline aggiornato con flusso dice → re-prompt
- [x] Evento WebSocket `dice:roll` inviato e ricevuto
- [x] Animazione dadi funzionante nel frontend con suono
- [ ] Il DM chiede tiri solo quando appropriato (testare 20+ turni) — da verificare in playtest
- [x] Unit test per distribuzione probabilistica dei risultati
- [x] GameClock implementato e aggiornato da `time_passed_minutes` dopo ogni turno
- [x] `requires_player_action` derivato dal backend, pulsante Continua funzionante

---

### A3. Character Sheet Base

**Perché ora:** Senza stats, i dadi non hanno significato. Un tiro di dado senza modifier è solo random — con gli attributi diventa *il mio personaggio è bravo in questo*.

**Task:**

**A3.1 — Definire lo schema Character Sheet**

Nel World State Object, sezione `player.character_sheet`:

```json
{
  "name": "Kael Shadowmend",
  "backstory": "A scarred elven alchemist...",
  "attributes": {
    "STR": 10, "DEX": 14, "CON": 12,
    "INT": 16, "WIS": 13, "CHA": 8
  },
  "modifiers": {
    "STR": 0, "DEX": 2, "CON": 1,
    "INT": 3, "WIS": 1, "CHA": -1
  },
  "hp": { "current": 24, "max": 24 },
  "level": 1,
  "xp": 0,
  "skills": [],
  "inventory": [
    { "name": "Alchemist's Kit", "quantity": 1, "description": "..." },
    { "name": "Health Potion", "quantity": 2, "effect": "Restore 2d4+2 HP" }
  ],
  "equipped": {
    "weapon": "Dagger",
    "armor": "Leather Armor"
  },
  "active_quests": [],
  "reputation": {}
}
```

Formula modifier: `floor((attribute - 10) / 2)` (standard D&D).

**A3.2 — Flusso di creazione narrativa**

Quando il player crea una campagna, i primi turni sono dedicati alla creazione del personaggio:

1. DM chiede: "Describe your character concept — who are they, where do they come from, what drives them?"
2. Player risponde con descrizione libera
3. DM genera il character sheet completo (JSON nel campo `character_generation` della risposta)
4. Backend parseggia e salva nel world state
5. DM presenta la scheda al player in modo narrativo: "You are Kael Shadowmend, an elven alchemist with a keen mind (INT 16) but awkward manner (CHA 8)..."
6. Player può chiedere aggiustamenti: "Can I be stronger?" → DM ribilancia
7. Player conferma → creazione completata, avventura inizia

Per la v1, questo flusso può essere semi-guidato: il DM fa domande specifiche se il player dà risposte vaghe.

**A3.3 — Aggiornare il Context Assembler**

Il character sheet deve essere SEMPRE incluso nel prompt DM, nella sezione "Character Context". Il DM deve sapere gli stats per assegnare DC appropriati e scegliere quale stat usare per i check.

**A3.4 — Aggiornare il CharacterSheet nel frontend**

Il pannello sinistro che già esiste deve mostrare:
- Nome e backstory (collapsibile)
- 6 attributi con modifier (es. "STR 10 (+0)")
- HP bar con current/max
- Inventario come lista
- Quest attive (per ora vuote, verranno dopo)
- Aggiornamento in tempo reale quando il world state cambia

**A3.5 — Collegare Character Sheet al Dice Engine**

Quando il DM richiede `dice_required: {check: "persuasion", stat: "CHA", dc: 15}`:
- Il backend legge `world_state.player.character_sheet.modifiers.CHA` = -1
- Chiama `roll_d20(stat_modifier=-1, dc=15)`
- Il player vede: "🎲 Persuasion Check: 12 + (-1) = 11 vs DC 15 → Soft Failure"

**Criteri di completamento A3:**
- [x] Schema character sheet definito nel world state
- [x] Flusso creazione personaggio funzionante (almeno 2 turni di dialogo)
- [x] DM genera stats dal concept del player
- [x] Character sheet nel frontend con tutti i campi
- [x] Stats collegati ai dice rolls
- [ ] HP visibile e aggiornabile — da rifinire in playtest
- [ ] Inventario base funzionante — da rifinire in playtest

---

### A4. Scene Mood + Feedback Visivo

**Perché ora:** Costa poco, impatto percettivo enorme. Trasforma un'interfaccia monotona in un'esperienza atmosferica.

**Task:**

**A4.1 — Mappare scene_mood a stili CSS**

```css
/* Variabili CSS per mood */
[data-mood="calm_exploration"]    { --mood-bg: #1a2f1a; --mood-accent: #4a7c59; }
[data-mood="tense_anticipation"]  { --mood-bg: #2a1f1f; --mood-accent: #8b6914; }
[data-mood="combat_fury"]         { --mood-bg: #3a1010; --mood-accent: #cc3333; }
[data-mood="stealth_danger"]      { --mood-bg: #0f0f1a; --mood-accent: #4a4a6a; }
[data-mood="social_intrigue"]     { --mood-bg: #2a1f10; --mood-accent: #c4943a; }
[data-mood="melancholic_reflection"] { --mood-bg: #15182a; --mood-accent: #5a6a8a; }
[data-mood="triumphant_victory"]  { --mood-bg: #2a2a10; --mood-accent: #d4a030; }
[data-mood="dread_horror"]        { --mood-bg: #0a0a10; --mood-accent: #6a3a6a; }
[data-mood="wonder_discovery"]    { --mood-bg: #10202a; --mood-accent: #40a0c0; }
[data-mood="mourning_loss"]       { --mood-bg: #151515; --mood-accent: #606060; }
[data-mood="neutral"]             { --mood-bg: #1a1a2e; --mood-accent: #4a4a7a; }
```

Applicare come attributo `data-mood` sul narrative panel container. La transizione tra mood deve essere smooth (CSS transition 1-2 secondi).

**A4.2 — Suono dadi**

Un singolo file `public/sounds/dice-roll.mp3`. Triggerato dall'evento `dice:roll`. Volume controllabile dall'utente (toggle on/off nel settings per ora, slider nella v2).

**Criteri di completamento A4:**
- [x] 11 mood mappati a stili CSS
- [x] Transizione smooth tra mood
- [x] Suono dadi funzionante
- [ ] Toggle suono on/off — non implementato

---

## FASE B — "World che vive" (3-4 settimane)

> **Obiettivo:** Il mondo ha persistenza, NPC ricordano, la memoria non esplode dopo 50 turni.

---

### B0. Semantic Resolver

**Perché prima di B1:** Il Context Assembler e l'Actor-Director dipendono da questo componente per risolvere riferimenti impliciti ("lei", "la città di fianco") e caricare il contesto corretto.

**Task:**

**B0.1 — Implementare il Semantic Resolver**

`backend/app/ai/semantic_resolver.py`:
- Mini-call a budget model (~200ms, trascurabile) prima del Context Assembler
- Riceve: testo del player + contesto sessione (companion attivi, location recenti, NPC recenti)
- Output:
  ```python
  class ResolverOutput(BaseModel):
      target_locations: list[str] = []    # location esplicite e risolte
      target_npcs: list[str] = []         # NPC espliciti e pronominali risolti
      time_estimate_minutes: int = 5      # stima tempo narrativo
  ```
- Risolve: "vado con lei" → `target_npcs: ["Grenda"]` (unica companion femminile attiva)
- Risolve: "la città di fianco" → `target_locations: ["Neverwinter"]` (con contesto geografico)

**B0.2 — Integrare nel Turn Pipeline**

Pipeline aggiornato:
```
Sanitizer → [Semantic Resolver] → Context Assembler → DM call
```

Il Context Assembler usa l'output come guida primaria:
```
Carica = NPC(location corrente) + NPC(risolti da Resolver) + Companion(attivi)
```

Le regole fisse (location corrente, companion) sono il minimum guaranteed. Il Resolver aggiunge tutto il resto.

**Criteri di completamento B0:**
- [x] Semantic Resolver implementato e testato con 10+ frasi ambigue
- [x] Integrato nel turn pipeline prima del Context Assembler
- [ ] Context Assembler usa output del Resolver per il contextual loading — implementato il resolver ma il context assembler non fa ancora loading selettivo (Phase D)
- [x] Latenza < 300ms per la call

---

### B1. World State Object Completo

**Task:**

**B1.1 — Implementare lo schema World State completo**

`backend/app/memory/world_state.py`:

```python
class WorldState(BaseModel):
    meta: Meta                    # schema_version, campaign_id, template, turn_count, in_game_date
    player: PlayerState           # character_sheet, reputation, active_quests, completed_quests, relationships, death_mode, destino_lives
    companions: list[Companion]   # name, sheet, loyalty, personal_quest_stage, opinions, memory
    world: WorldInfo              # factions, regions, global_events, time
    narrative: NarrativeState     # event_log, active_threads, foreshadowing
    npcs: NPCRegistry            # active_npcs, npc_full_profiles
```

Ogni sezione è un Pydantic model separato.

**B1.1b — GameClock e WorldSimulatorState nel World State**

Aggiungere al World State schema:

```python
class GameClock(BaseModel):
    total_minutes: int = 0
    current_hour: int = 8           # derivato
    current_day: int = 1            # derivato
    current_season: str = "spring"  # derivato
    time_of_day: str = "morning"    # "dawn|morning|afternoon|evening|night|midnight"

class WorldSimulatorState(BaseModel):
    enabled: bool = False                    # toggle utente, logica in v2
    last_simulated_turn: int = 0
    pending_world_events: list[dict] = []
    scheduled_npc_actions: list[dict] = []
```

Il `GameClock` è alimentato da `time_passed_minutes` del DMResponse (vedere A2.5).
Il `WorldSimulatorState` è solo schema — la logica viene in v2.

**B1.2 — World State Updater**

`backend/app/memory/updater.py`:

Dopo ogni turno, prende i `world_updates` dalla DMResponse e li applica al world state:
- `npc_disposition` → aggiorna `npcs.active_npcs[name].disposition`
- `faction_event` → aggiorna `world.factions[name]`
- `quest_update` → aggiorna `player.active_quests`
- `hp_change` → aggiorna `player.character_sheet.hp.current`
- `inventory_change` → aggiorna `player.character_sheet.inventory`
- `reputation_change` → aggiorna `player.reputation`
- `companion_loyalty` → aggiorna `companions[name].loyalty`
- `time_advance` → aggiorna `world.clock` via `time_passed_minutes` (GameClock)
- `event_log_entry` → append a `narrative.event_log`

Ogni update è atomico e validato. Se un update è invalido (NPC non esiste, HP sotto 0), viene loggato e skippato.

**B1.3 — Contextual Loading nel Context Assembler**

Non tutto il world state va nel prompt. Il Context Assembler seleziona:
- Player in una location → carica region data + NPC locali
- Player parla con NPC → carica profilo completo NPC + storia interazioni
- Combattimento → carica stats nemici + companion combat preferences
- Decisione politica → carica fazioni rilevanti

Implementare come un set di funzioni `load_context_for_scene(world_state, scene_type) -> dict` che ritorna solo le sezioni rilevanti.

**Criteri di completamento B1:**
- [x] World State schema con sotto-modelli Pydantic per NPC e Companion (`memory/schemas.py`: `NPCProfile`, `CompanionProfile`, `NPCPersonality`). GameClock già in v2. WorldSimulatorState schema-only (logica in v2).
- [x] World State Updater applica tutti i tipi di update — 7 handler tipizzati in `memory/updater.py` + fallback generico (`time_advance` gestito da `advance_game_clock` nel pipeline)
- [ ] Contextual loading funzionante, guidato dal Semantic Resolver (B0) — rinviato a Phase D
- [x] World state persiste correttamente tra turni nel DB (schema v3 con migration v0→v3)
- [x] Test: 18 test updater + 9 test schemas, tutti passing

---

### B2. NPC Base + Companion Base

**Task:**

**B2.1 — NPC Profile Schema**

```json
{
  "name": "Grenda Ironveil",
  "role": "Blacksmith",
  "location": "Ironforge Market",
  "personality": {
    "traits": ["cautious", "loyal", "sardonic"],
    "values": ["family", "craftsmanship"],
    "fears": ["the guard captain"],
    "secrets": ["smuggles weapons to the resistance"]
  },
  "disposition_toward_player": 0,
  "goals": ["keep forge running", "protect resistance"],
  "memory": []
}
```

**B2.2 — NPC nel prompt DM + Actor-Director Pattern**

Quando il player interagisce con un NPC:
- Il Context Assembler carica il profilo completo (guidato dal Semantic Resolver)
- Il DM riceve istruzioni: "This NPC has disposition [X] toward the player. They are [traits]. They want [goals]. They fear [fears]. List NPCs who should speak in `invoke_npcs`."
- Dopo l'interazione, il DM genera un `world_update` con disposition change e memory entry

**Pattern Actor-Director:**
Il DM è il Regista, gli NPC sono Attori indipendenti.

Flusso:
1. DM risponde con `invoke_npcs: ["Grenda", "Re Aldric"]`
2. Backend lancia chiamate NPC in parallelo (`asyncio.gather`, budget model)
3. Frontend inizia a streammare la `narration` del DM
4. Mentre il player legge (~2-3 sec), gli NPC generano
5. Dialoghi NPC arrivano via WebSocket (`npc:dialogue:start/chunk/end`)
6. I dialoghi NPC NON tornano mai al DM — vanno a schermo direttamente
7. Il turno finisce dopo i dialoghi NPC

Prompt per ogni NPC (budget model): nome, ruolo, tratti, disposition, ultima interazione (da `memory_facts`), azione del player. Istruzione: "Rispondi in 1-2 frasi, in character."

File da modificare: `backend/app/api/websocket.py`, `backend/app/services/turn_service.py`, `backend/app/ai/prompts/npc.py`

**B2.3 — Companion Schema (estensione di NPC)**

```json
{
  "...tutto di NPC, più:",
  "loyalty": 60,
  "personal_quest_stage": "dormant",
  "opinions": { "other_companion_name": "respect" },
  "combat_style": "aggressive",
  "backstory_hooks": ["lost brother in war", "owes debt to thieves guild"]
}
```

**B2.4 — Companion nel prompt DM**

I companion sempre presenti nel character context del prompt:
- Il DM sa che i companion sono lì e li fa reagire
- Le reazioni appaiono come `companion_actions` nella DMResponse
- Il frontend le mostra come bolle di dialogo separate

Per la v1, iniziare con **1 companion** per template che funziona bene, piuttosto che 3 mediocri.

**B2.5 — Companion Bar nel frontend**

Sopra l'input bar:
- Portrait del companion (placeholder image per ora, un'icona)
- Nome
- Indicatore loyalty (barra colorata: verde > 60, giallo 30-60, rosso < 30)
- Click → apre pannello con dettagli

**Criteri di completamento B2:**
- [x] NPC profile schema implementato (`NPCProfile` + `CompanionProfile` Pydantic models in `memory/schemas.py`)
- [ ] Almeno 3 NPC generati con il primo template — da verificare in playtest
- [x] NPC disposition cambia in base alle azioni del player (via `npc_disposition` handler in updater)
- [x] Actor-Director: NPC invocati via `invoke_npcs` rispondono con call LLM indipendente (`npc_director.py`, `asyncio.gather`)
- [x] Eventi WebSocket `npc:dialogue` funzionanti (scelta: dialogo completo in un singolo evento, non chunked — NPC producono 1-2 frasi)
- [ ] Ogni NPC ha voce distinta (verificare con 3+ NPC diversi nella stessa scena) — da verificare in playtest
- [x] CompanionProfile schema con loyalty e dialogo
- [x] Companion reazioni appaiono nella narrazione (NPC dialogues appended to turn narration)
- [ ] Companion bar nel frontend — non implementato (Phase C/D)

---

### B3. Memoria — Architettura a 3 Pilastri

**Task:**

**B3.1 — Pilastro 2: Active Window (compressione)**

`backend/app/memory/compression.py`:

- **Active Window:** Ultimi 5-8 turni salvati verbatim (~2000 token). Caricati integralmente nel prompt.
- **Turni oltre la finestra:** compressi. Ogni 5-8 turni, un budget model genera un riassunto di 2-3 frasi.
- Trigger: dopo ogni turno, se turni non compressi > 8, comprimi il batch più vecchio.

**B3.2 — Pilastro 3: Tabella `memory_facts` + Fact Extractor**

Creare modello SQLAlchemy `backend/app/models/memory_fact.py`:

```python
class MemoryFact(Base):
    __tablename__ = "memory_facts"
    id: uuid
    campaign_id: uuid              # FK → campaigns
    turn_number: int
    entity_name: str               # "Grenda", "Neverwinter", "DragonHunt"
    entity_type: str               # "npc", "location", "quest", "item", "event", "secret"
    content: str                   # fatto atomico in linguaggio naturale
    embedding: vector(1536)        # pgvector
    search_vector: tsvector        # per full-text search ibrido
    created_at: timestamp
```

Creare Alembic migration per la nuova tabella.

**Fact Extractor** (`backend/app/memory/fact_extractor.py`):
- Dopo ogni turno: `asyncio.create_task(extract_facts(turn))` — non bloccante
- Budget model estrae 1-5 fatti atomici strutturati
- Formato: `"NomeEntità:tipo:stato — dettaglio con turno"`
- Ogni fatto = una riga nel DB = un embedding

Esempi di fatti atomici:
```
"Grenda:relazione:ostile — ha scoperto il furto della borsa al turno 23"
"Neverwinter:luogo:visitato — prima visita turno 3, torre bruciata scoperta"
"DragonHunt:quest:accettata — ricompensa 500 oro promessa dal Re al turno 15"
```

**B3.3 — Token Budget Check**

Prima di inviare il prompt al LLM:
- Token budget totale: ~12,500-15,500 token input
  - Pilastro 1 (Core State + Recap): ~1500 token fissi
  - Pilastro 2 (Active Window): ~2000 token
  - Pilastro 3 (Fatti Atomici): ~500 token
  - Resto: system prompt, character context, scene context, player action
- Se supera il budget, comprimi più aggressivamente i turni recenti
- Log warning se il prompt è troppo grande anche dopo compressione

**Criteri di completamento B3:**
- [x] Active Window (configurabile, default 8 turni verbatim) + compressione turni vecchi funzionante (LLM budget model, batch di 5)
- [x] Tabella `memory_facts` creata con migration Alembic (`001_add_memory_facts.py`)
- [x] Fact Extractor estrae fatti atomici dopo ogni turno (asincrono, `asyncio.create_task`)
- [ ] Token budget check prima di ogni prompt — non implementato (budget costante ~4000 token per design)
- [ ] Test: campagna di 50 turni senza context overflow — da verificare in playtest
- [ ] Fatti atomici leggibili e accurati (verificare manualmente 10+ fatti) — da verificare in playtest

---

### B4. Template System Base

**Task:**

**B4.1 — Definire formato template**

`templates/the-awakening/template.json`:

```json
{
  "metadata": {
    "name": "The Awakening",
    "slug": "the-awakening",
    "genre": "fantasy",
    "description": "A guided introductory adventure...",
    "author": "SAGA Team",
    "version": "1.0.0",
    "estimated_duration": "30-45 minutes",
    "difficulty": "beginner"
  },
  "dm_style": "classic",
  "world_skeleton": {
    "regions": [...],
    "factions": [...],
    "core_conflict": "...",
    "npc_archetypes": [...],
    "starting_location": "...",
    "opening_scene": "..."
  },
  "lore_seeds": {
    "creation_myth": "...",
    "historical_events": [...],
    "cultural_notes": [...]
  },
  "starting_conditions": {
    "player_location": "...",
    "initial_npcs": [...],
    "initial_companion": {...},
    "opening_narration": "..."
  }
}
```

**B4.2 — Template Loader**

`backend/app/templates/loader.py`:
- Carica template da directory `templates/`
- Valida struttura base (campi obbligatori presenti)
- Sanitizza tutti i campi testo (anti-prompt-injection)
- Ritorna template pronto per la generazione del mondo

**B4.3 — World Generation dal Template**

Quando il player crea una campagna:
1. Seleziona template
2. Il backend carica il template
3. Chiama il LLM con il world_skeleton + lore_seeds: "Generate a unique world based on this template. Create specific names, NPCs, locations, and details."
4. Il LLM ritorna un world state iniziale popolato
5. Il world state viene salvato nel DB
6. La campagna inizia con `opening_narration`

**B4.4 — Creare "The Awakening" template**

Il tutorial template deve insegnare al player:
- Come descrivere azioni (turno 1-3)
- Come funzionano i tiri di dado (turno 4-6)
- Come funziona il combattimento base (turno 7-10)
- Come interagire con un NPC (turno 11-13)
- Come reclutare un companion (turno 14-16)
- Un mini-boss finale (turno 17-20)

Completabile in 20-25 turni.

**Criteri di completamento B4:**
- [ ] Formato template definito e documentato
- [ ] Template loader con validazione e sanitizzazione
- [ ] World generation dal template funzionante
- [ ] "The Awakening" template completo e playtestato
- [ ] Un player può completare il tutorial in 30-45 minuti

---

## FASE C — "Differenziatori" (3-4 settimane)

> **Obiettivo:** Le feature che rendono SAGA unico rispetto a ogni competitor.

---

### C1. Death System

**Task:**

**C1.1 — Selezione death mode alla creazione**

Dopo la creazione del personaggio, il DM chiede: "How do you want to face death in this world?"
- Ironman: "Every breath is precious. Death is real and final."
- Destino: "Fate watches over you... but at a price. Three chances, each costlier than the last."
- Cronista: "You are the storyteller. You cannot die, but you can still lose."

La scelta viene salvata in `world_state.player.death_mode`.

**C1.2 — Implementare Ironman**

Nel turn pipeline, dopo il combat resolution:
- Se `hp.current <= 0`:
  - Inizia death saving throws (3 turni speciali)
  - 3 successi (d20 ≥ 10) → stabilizzato, 1 HP
  - 3 fallimenti → morto
  - Nat 20 → stabilizzato immediatamente con 1 HP
  - Nat 1 → conta come 2 fallimenti
- Se morto: DM narra scena di morte + epilogo, campaign status → COMPLETED con tag "death"

**C1.3 — Implementare Destino**

Come Ironman, ma quando il player muore e ha `destino_lives_remaining > 0`:
- Decrementa il contatore
- Il DM riceve istruzione: "The player just died but has a fate intervention. Narrate a miraculous survival with a [TIER] cost."
- Tier determinato dal numero di intervento (1°=Minor, 2°=Major, 3°=Severe)
- Il DM sceglie il costo specifico dalla lista del tier appropriato
- Il costo viene applicato al world state (perdita oggetto, -attributo, companion morte, ecc.)
- Il DM narra l'intervento come momento narrativo, non meccanico

**C1.4 — Implementare Cronista**

Nel turn pipeline:
- Se `hp.current <= 0`: impostare `hp.current = 1`
- Il DM riceve istruzione: "The player would have died but is in Cronista mode. Narrate a dramatic near-death moment, then describe the consequences (capture, retreat, equipment loss) — never death."
- Companion a 0 HP → unconscious, non morti. Recuperano dopo combattimento.

**C1.5 — Iniettare death mode nel system prompt**

Il DM deve sempre sapere il death mode attivo. Le regole cambiano il suo comportamento:
- Ironman: "Never pull punches. Minimal warnings. No behind-the-scenes mercy."
- Destino: "Subtle warnings allowed. Track remaining interventions ([X] left). Increase tension as interventions diminish."
- Cronista: "Focus on narrative consequences. Combat is challenging but defeat means setback, not termination."

**Criteri di completamento C1:**
- [x] Selezione death mode funzionante (dropdown nella create campaign form, già presente da Fase B)
- [x] Ironman: morte permanente a 0 HP, DM narra epilogo, campaign status → COMPLETED (death saving throws → v2)
- [x] Destino: fate intervention con costi escalanti (Minor/Major/Severe), contatore `destino_lives` decrementato
- [x] Cronista: near-death narrative + HP reset a 1, no morte effettiva
- [x] DM si comporta diversamente in base al death mode (`DEATH_MODE_PROMPTS` + `COMBAT_PROMPT` iniettati)
- [x] Test: 16 unit test in `test_death_system.py`, tutti i modi coperti

---

### C2. Save System

**Task:**

**C2.1 — Auto-Save**

Dopo ogni turno (post world-state-update):
- Cerca SavePoint con `campaign_id` e `is_auto=True`
- Se esiste: aggiorna `world_state`, `turn_number`, `scene_summary`
- Se non esiste: creane uno nuovo
- Solo 1 auto-save per campagna alla volta

**C2.2 — Manual Save**

Endpoint `POST /api/campaigns/:id/saves`:
- Accetta `label` dal player
- Genera `scene_summary` automaticamente (ultimi 2-3 turni riassunti, o ultimo `narration`)
- Crea SavePoint con snapshot completo del world_state
- Non permesso durante il combattimento (check `world_state.narrative.in_combat`)

**C2.3 — Save Browser nel frontend**

Componente `SaveBrowser.tsx`:
- Lista tutti i manual saves + indicazione auto-save
- Per ogni save: label, turno #, data in-game, scene summary, timestamp reale
- Click su save → mostra preview (summary + HP + quest attive + companion presenti)
- Bottone "Load" → conferma "This will create a new timeline fork. Continue?"

**C2.4 — Timeline Forking**

Endpoint `POST /api/campaigns/:id/saves/:save_id/load`:
1. Carica il SavePoint
2. Crea nuova Campaign con:
   - `world_state` copiato dal save
   - `parent_save_id` = save_id
   - `name` = original name + " (Fork from turn X)"
   - `turn_count` = save's turn_number
3. Ritorna la nuova campagna
4. Il frontend naviga alla nuova campagna

**C2.5 — Visualizzazione fork nel frontend**

Nella lista campagne, mostrare:
- Campagne root (senza parent_save_id) come nodi principali
- Campagne forked come sotto-nodi con indicazione "Forked at turn X"
- Icona o linea che collega fork al punto di branch

**Criteri di completamento C2:**
- [ ] Auto-save dopo ogni turno — trigger non implementato (Phase D)
- [ ] Resume da auto-save al login — Phase D
- [x] Manual save bloccato durante il combattimento (guard in `saves.py`)
- [ ] Save browser nel frontend — Phase D
- [ ] Timeline forking UI — Phase D (endpoint `POST /saves/:id/load` già esistente)

---

### C3. Combat System

**Task:**

**C3.1 — Iniziativa**

Quando il DM dichiara inizio combattimento:
- Il DM include `combat_start: true` nella risposta (aggiungere campo allo schema)
- Il backend tira iniziativa per tutti: d20 + DEX modifier per il player, d20 + DEX per ogni nemico e companion
- Ordina dal più alto al più basso
- Salva ordine in `world_state.narrative.combat_state`
- Invia l'ordine al frontend

**C3.2 — Combat State nel World State**

```json
"combat_state": {
  "active": true,
  "round": 1,
  "initiative_order": [
    { "name": "Player", "initiative": 18, "type": "player" },
    { "name": "Kira", "initiative": 15, "type": "companion" },
    { "name": "Goblin Scout", "initiative": 12, "type": "enemy", "hp": 15, "max_hp": 15 },
    { "name": "Goblin Warrior", "initiative": 8, "type": "enemy", "hp": 22, "max_hp": 22 }
  ],
  "current_turn_index": 0
}
```

**C3.3 — Player Combat Turn**

Quando è il turno del player:
- Il player scrive l'azione (free text)
- Il DM riceve il combat state + azione
- Il DM risponde con: narrazione + dice_required (attacco/abilità) + world_updates (danni)
- Il turno avanza al prossimo nell'ordine di iniziativa

**C3.4 — NPC/Companion Combat Turns**

Quando è il turno di un NPC o companion:
- Il DM genera autonomamente l'azione basata sulla personalità/tipo
- Tiri di dado calcolati server-side
- Narrazione + risultati inviati al player
- Il turno avanza automaticamente

Per la v1, tutti i turni nemici + companion possono essere batched in una singola chiamata LLM per ridurre latenza:
"It's the enemies' turn. Goblin Scout (HP 15) attacks the player. Goblin Warrior (HP 22) attacks Kira. Narrate their actions and specify dice rolls needed."

**C3.5 — Combat Tracker nel frontend**

`frontend/src/components/CombatTracker.tsx`:
- Overlay che appare quando `combat_state.active = true`
- Mostra ordine iniziativa come lista verticale
- Evidenzia chi sta agendo ora
- HP bar per ogni partecipante
- Si aggiorna in tempo reale via WebSocket

**C3.6 — Fine combattimento**

Quando tutti i nemici sono a 0 HP (o fuggiti/arresi):
- Il DM imposta `combat_end: true` nella risposta
- Il backend resetta `combat_state.active = false`
- Il Combat Tracker scompare
- Il DM narra il aftermath (loot, conseguenze, companion reazioni)

**Criteri di completamento C3:**
- [x] Iniziativa funzionante per player + nemici (d20 + DEX modifier), ordine decrescente
- [x] Combat state nel world state v4 (`combat_state` con active/round/initiative_order/current_turn_index)
- [x] Player combat turn: DM riceve combat state, usa `combat_damage` world_update per i danni
- [ ] Enemy AI comportamenti distinti — delegato al DM via narrazione libera per v1
- [ ] Companion agisce autonomamente — turno companion narrato dal DM, non call LLM separata
- [x] Combat Tracker nel frontend (`combat-tracker.tsx`, overlay fisso, HP bar color-coded)
- [x] Fine combattimento: DM emette `combat_end` world_update, tracker scompare
- [x] Test: 17 unit test in `test_combat_handlers.py`, tutti i handler coperti

---

### C4. AI Router Multi-Provider

**Task:**

**C4.1 — Configurazione provider**

`backend/app/ai/model_config.yaml`:

```yaml
providers:
  openai:
    api_key_env: OPENAI_API_KEY
    models:
      budget: gpt-4o-mini
      mid: gpt-4o
      premium: gpt-5.2
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    models:
      budget: null  # non ha budget model
      mid: claude-sonnet-4-6
      premium: claude-opus-4-6
  google:
    api_key_env: GOOGLE_API_KEY
    models:
      budget: gemini-2.0-flash
      mid: gemini-2.5-pro
      premium: gemini-3.1-pro
  local:
    base_url_env: LOCAL_AI_URL  # http://localhost:11434/v1 per Ollama
    models:
      budget: local-default
      mid: local-default
      premium: local-default

module_defaults:
  dm_narration: mid
  companion_dialogue: mid
  npc_interaction: budget
  world_simulation: budget
  memory_compression: budget
  recap_generation: budget
  combat_adjudication: mid
  embedding: voyage-3-lite  # o locale

importance_scoring:
  base:
    dm_narration: 3
    companion_dialogue: 2
    npc_interaction: 1
    world_simulation: 0
    memory_compression: 0
    combat_adjudication: 3
  modifiers:
    active_combat: +2
    companion_personal_quest: +2
    plot_critical_npc: +1
    boss_encounter: +3
    first_session: +1
```

**C4.2 — Router Logic**

`backend/app/ai/router.py`:

```python
def select_model(module: str, scene_context: dict, user_config: dict) -> tuple[str, str]:
    """Returns (provider, model_name)"""
    # 1. Calcola importance score
    base = config.importance_scoring.base[module]
    modifiers = sum(v for k, v in config.importance_scoring.modifiers.items() if scene_context.get(k))
    score = base + modifiers

    # 2. Mappa score a tier
    tier = "budget" if score <= 2 else "mid" if score <= 5 else "premium"

    # 3. Seleziona provider disponibile
    # Ordine preferenza: provider preferito dell'utente → fallback chain
    # Se l'utente ha configurato solo OpenAI, usa sempre OpenAI

    # 4. Override: se l'utente ha solo un provider locale, tutto va lì

    return (provider, model_name)
```

**C4.3 — Fallback chain**

Se una chiamata API fallisce:
1. Retry 1 volta con lo stesso provider
2. Se fallisce ancora: prova il prossimo provider disponibile nello stesso tier
3. Se nessun provider nello stesso tier: downgrade al tier sotto
4. Se tutto fallisce: ritorna errore al player con messaggio chiaro

**C4.4 — Cost Tracking**

Dopo ogni chiamata API:
- Calcola costo approssimato: `(input_tokens * input_price + output_tokens * output_price)`
- Salva nel campo `ai_cost` del Turn model
- Aggiorna running total nella sessione

**Criteri di completamento C4:**
- [ ] model_config.yaml con almeno 3 provider configurati
- [ ] Router seleziona modello basato su score
- [ ] Fallback funzionante (testare con provider finto che fallisce)
- [ ] Cost tracking per ogni chiamata
- [ ] L'utente può configurare provider diversi via env

---

## FASE D — "Agentic DM" (3-4 settimane)

> **Obiettivo:** Sostituire il mega-prompt monolitico con un DM che chiama tool tipizzati. Elimina strutturalmente il 90% dei bug di formato JSON, rende ogni meccanica estensibile, e disaccoppia trasporto da logica (WebSocket → SSE).

---

### D0. Motivazione e principi

**Problema attuale:** il DM deve emettere un blob JSON complesso in un'unica risposta. Ogni meccanica (combat, damage, location, inventory) richiede una regola nel prompt per spiegargli il formato esatto. I bug di Sprint 1 erano tutti causati da questo.

**Soluzione:** il DM ragiona liberamente in narrazione, poi chiama tool con schema rigido. Il formato è garantito dall'SDK — non dal prompt.

**Principi:**
- Il DM rimane il punto unico di narrazione. I tool sono le sue "mani" sul mondo.
- Ogni handler in `updater.py` corrisponde a un tool (1:1 mapping già verificato in Sprint 1/2).
- Le regole narrative nel system prompt rimangono identiche — solo le regole di formato JSON spariscono.
- SSE sostituisce WebSocket: il client POSTa l'azione, riceve uno stream di eventi server-sent.

---

### D1. Tool Schema — definire i tool del DM

**File:** `backend/app/ai/tools/dm_tools.py`

Definire come Pydantic models + OpenAI-compatible tool schema:

```python
# Ogni tool corrisponde a un handler esistente in updater.py
tools = [
    start_combat(enemies: list[EnemyDef]),          # → _handle_combat_start
    apply_damage(target: str, amount: int),          # → _handle_combat_damage
    end_combat(),                                    # → _handle_combat_end
    move_to(location: str),                          # → _handle_location
    update_hp(change: int),                          # → _handle_hp_change
    add_item(name: str, description: str),           # → _handle_inventory (add)
    remove_item(name: str),                          # → _handle_inventory (remove)
    update_quest(name: str, status: str, desc: str), # → _handle_quest
    change_npc_disposition(npc: str, delta: int),    # → _handle_npc_disposition
    log_event(description: str),                     # → _handle_event_log
    invoke_npc(name: str),                           # → existing invoke_npcs
    request_dice(check: str, dc: int, stat: str),    # → existing dice_required
]
```

**Note:**
- I tool rimpiazzano `world_updates`, `invoke_npcs`, `dice_required` nel JSON monolitico.
- `narration` rimane come output testuale normale (non tool) — streammato direttamente.

---

### D2. Agentic Loop — orchestratore

**File:** `backend/app/core/agent.py`

```python
async def run_dm_agent(campaign, player_action, db) -> AsyncIterator[StreamEvent]:
    """
    Loop:
    1. Call LLM with tools available
    2. Stream narration tokens as they arrive
    3. For each tool_call in response: execute immediately, feed result back
    4. Repeat until LLM emits stop (no more tool calls)
    5. Yield turn_result with accumulated state
    """
```

**Considerazioni latenza:**
- Gemini Flash: ~200ms per tool call — con 3-4 tool calls, latenza totale ~1s extra.
- Tool calls avvengono in background mentre la narrazione streamma già al client.
- Il client vede narrazione immediata, i tool vengono eseguiti mentre il player legge.

---

### D3. Migrazione trasporto: WebSocket → SSE

**Motivazione:** il WebSocket è bidirezionale ma SAGA usa solo server→client per il bulk dei dati. Il client manda un singolo messaggio per turno (l'azione). SSE è più semplice, nessun handshake, auth via HTTP header normale.

**Backend:** `backend/app/api/turns.py`
```
POST /api/campaigns/:id/turn   { "action": "..." }
→ StreamingResponse con events:
   data: {"type": "narration_chunk", "chunk": "..."}
   data: {"type": "tool_called", "tool": "apply_damage", "args": {...}}
   data: {"type": "turn_complete", ...}
```

**Frontend:** `frontend/src/services/turn-stream.ts`
```typescript
// Sostituisce GameWebSocket
const response = await fetch(`/api/campaigns/${id}/turn`, { method: "POST", body, ... });
const reader = response.body.getReader();
// parse SSE events...
```

**Cosa si semplifica:**
- Niente reconnect logic, niente race condition isMounted (già fixata ma diventa moot)
- Auth via header Authorization normale
- Backend: `game_ws()` in `websocket.py` diventa endpoint FastAPI standard con `StreamingResponse`

---

### D4. System prompt update

Rimuovere dal DM prompt tutte le regole di formato JSON (`world_updates`, `dice_required`, ecc.) — diventano irrilevanti con i tool. Mantenere:
- Regole narrative (don't speak for player, no code fences, prompt injection defense)
- Regole di gameplay (combat_start una volta, tiri solo su azioni incerte)
- Context sections (character, world state, storia)

Il prompt si riduce di ~40% in token.

---

### D5. Test e validazione

- Unit test per ogni tool (schema validation, handler integration)
- Playtest: verifica che in 20+ turni il DM chiami i tool correttamente senza fallback su JSON manuale
- Regression: tutti i 239 test esistenti devono passare (i handler in `updater.py` non cambiano)
- Confronto latenza: turno medio con tool call vs turno monolitico attuale

---

### Criteri di completamento Fase D
- [ ] Tool schema definito, ogni tool mappa a un handler esistente
- [ ] Agentic loop implementato e testato
- [ ] SSE endpoint funzionante, frontend migrato
- [ ] DM non emette più `world_updates` JSON manuale — usa tool calls
- [ ] Tutti i 239 test esistenti passano (handler invariati)
- [ ] 20+ turni di playtest senza errori di formato
- [ ] System prompt ridotto del 40%+ (regole formato rimosse)

---

## FASE E — "Polish per il lancio" (2-3 settimane)

> **Obiettivo:** Il progetto è pronto per essere pubblicato su GitHub e usato da early adopters.

---

### E1. pgvector Hybrid Search — Pilastro 3

*(ex D1)*

- Implementare embedding per ogni fatto atomico in `memory_facts`
- **Hybrid Search** nel Context Assembler: 70% similarità semantica (`embedding <=>`) + 30% keyword match (`tsvector ts_rank`)
- Filtri metadata: `entity_name`, `entity_type`
- Top-5 fatti atomici iniettati nella sezione Memory Context (~500 token)
- File: `backend/app/memory/semantic.py`

### E2. Recap System — Ruolo Duale

*(ex D2)*

- **Ruolo 1 — System Prompt (critico):** recap iniettato come bussola permanente ogni turno. ~600-700 token fissi.
- **Ruolo 2 — JournalView (UI):** sommario narrativo visibile al player.
- Trigger: ogni 25 turni, budget model → nuovo recap cumulativo 500-800 parole.

### E3. API Keys UI + Cost Dashboard

*(ex D3)*

- Settings panel con form per API keys (3 provider + local URL)
- Crittografia AES-256 al salvataggio
- Test connection per ogni provider
- Dashboard costi: costo per turno, sessione, mese, breakdown per modulo

### E4. Secondo e terzo template

*(ex D4)*

- **The Shattered Crowns:** Political fantasy, 5 NPC chiave, 2 fazioni
- **The Last Light:** Dark fantasy survival, risorse scarse
- Playtestare entrambi per 30+ turni

### E5. Documentazione

*(ex D5)*

- `INSTALL.md`, `CONTRIBUTING.md`, `TEMPLATE_SDK.md`, `API.md`, `TROUBLESHOOTING.md`

### E6. CI/CD

*(ex D6)*

- GitHub Actions: lint, test, build Docker
- Pre-commit hooks, automatic changelog

### E7. Responsive & Mobile

*(ex D7)*

- Tablet: sidebar overlay. Mobile: navigazione a tab. PWA manifest.

### E8. Achievement System

*(ex D8)*

- Trigger da model esistente. Achievements base. UI nel profilo.

---

---

### D1. pgvector Hybrid Search — Pilastro 3

- Implementare embedding per ogni fatto atomico in `memory_facts` (non per turno — granularità fine)
- Usare Voyage AI API o bge-small locale
- **Hybrid Search** nel Context Assembler: 70% similarità semantica (`embedding <=>`) + 30% keyword match (`tsvector ts_rank`)
- Filtri metadata per restringere il perimetro: `entity_name` (NPC attivi in scena), `entity_type` (location corrente, quest sempre rilevanti)
- Il Semantic Resolver (B0) produce gli input per le query (`target_npcs`, `target_locations`)
- Top-5 fatti atomici iniettati nella sezione Memory Context del prompt (~500 token)
- File: `backend/app/memory/semantic.py` (aggiornare con hybrid search)

### D2. Recap System — Ruolo Duale

- **Ruolo 1 — System Prompt (critico):** Il recap più recente viene iniettato nel system prompt del DM come "bussola permanente" a ogni turno. Non opzionale — è il modo in cui il DM mantiene il quadro generale. Token budget: ~600-700 token, non va mai rimosso per fare spazio.
- **Ruolo 2 — JournalView (UI):** Il recap è visibile al player come sommario narrativo dell'avventura.
- Trigger: ogni 25 turni, budget model legge ultimi 25 turni + recap precedente → nuovo recap cumulativo 500-800 parole
- Recap vecchio archiviato (per JournalView), nuovo sostituisce quello nel system prompt
- È il secondo elemento più importante del prompt dopo le rules del DM

### D3. API Keys UI + Cost Dashboard

- Settings panel con form per API keys (3 provider + local URL)
- Crittografia AES-256 al salvataggio
- Test connection per ogni provider
- Dashboard costi: costo per turno, sessione, mese, breakdown per modulo

### D4. Secondo e terzo template

- **The Shattered Crowns:** Political fantasy, almeno 5 NPC chiave, 2 fazioni
- **The Last Light:** Dark fantasy survival, risorse scarse, tono cupo
- Playtestare entrambi per 30+ turni

### D5. Documentazione

- `INSTALL.md`: guida passo-passo Docker, requisiti, troubleshooting comuni
- `ARCHITECTURE.md`: diagrammi, flusso dati, decisioni architetturali
- `CONTRIBUTING.md`: come contribuire (code, template, traduzioni), PR guidelines
- `TEMPLATE_SDK.md`: come creare un template custom, schema reference
- `API.md`: tutti gli endpoint, request/response examples
- `TROUBLESHOOTING.md`: problemi comuni con soluzioni

### D6. CI/CD

- GitHub Actions workflow: lint (ruff/eslint), test (pytest/vitest), build Docker
- Pre-commit hooks per formatting
- Automatic changelog da conventional commits

### D7. Responsive & Mobile

- Tablet: sidebar come overlay
- Mobile: navigazione a tab
- Input bar fixed in bottom
- PWA manifest + service worker base

### D8. Achievement System

- Model già nel DB, implementare trigger
- Achievements base: primo crit, primo companion, prima morte, 100 turni, campagna completata
- UI nel profilo player

---

## Priorità se hai poco tempo

Se devi tagliare, questa è la v1 **minima giocabile** (MVP):

| Must Have | Nice to Have | Can Wait |
|-----------|-------------|----------|
| DM Output strutturato (con `invoke_npcs`, `time_passed_minutes`) | pgvector hybrid search (Pilastro 3) | Achievements |
| Healing Parser (`json-repair`) | Recap system (ruolo duale) | Responsive mobile |
| Content Policy Handler | AI Router multi-provider (1 provider ok) | Cost dashboard |
| Dice Engine meccanico | Timeline forking | Terzo template |
| Character Sheet base | Manual save browser | CI/CD pipeline |
| Scene Mood CSS | Combat tracker UI | GDPR export/import |
| GameClock / Time Engine | Second template | PWA |
| Semantic Resolver | Companion bar UI | World Simulator logica (v2) |
| World State Updater | Documentazione completa | |
| NPC base (disposition) | Ironman death saves | |
| Actor-Director pattern | Destino fate interventions | |
| 1 Companion funzionante | | |
| Memory: Active Window + Fact Extractor + `memory_facts` | | |
| Death mode selection + Cronista | | |
| Auto-save | | |
| 1 Template (tutorial) | | |
| Combat base | | |

Con il MVP tagliato, puoi lanciare in **6-8 settimane** e iterare con feedback della community.

---

*Ultimo aggiornamento: 2026-03-31 — Phase A+B+C+Sprint1+Sprint2 complete, 239 test passano.*
