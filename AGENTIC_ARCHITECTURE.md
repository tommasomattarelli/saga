# Agentic DM Architecture

## Turn Flow

```
Player sends action via WebSocket
         |
         v
+------------------+
|  Semantic         |   budget LLM: resolve entity names,
|  Resolver         |   target NPCs/locations
+------------------+
         |
         v
+------------------+
|  Context          |   Assembles: system prompt (XML) +
|  Builder          |   turn history (8 verbatim + 5 summaries)
+------------------+
         |
         v
+------------------+       +----------------+
|  AI Router        | ----> | Model Selection|  importance 0-3: low
|  (importance      |       | by tier        |  importance 4-6: medium
|   scoring)        |       |                |  importance 7-10: high
+------------------+       +----------------+
         |
         v
+===========================================+
|           AGENTIC LOOP (max 5 steps)      |
|                                           |
|   +----------------------------------+    |
|   | LLM.stream_with_tools()         |    |
|   |   -> TextChunk  (narration)     |    |
|   |   -> ToolCallChunk (tool calls) |    |
|   +----------------------------------+    |
|          |                  |             |
|     narration          tool calls         |
|     streamed           executed           |
|     to client          (see below)        |
|          |                  |             |
|          v                  v             |
|   +----------------------------------+   |
|   | Tool results fed back to LLM     |   |
|   | as messages -> next step         |   |
|   +----------------------------------+   |
|                                          |
|   Break when: no tool calls, or          |
|   2 consecutive empty-text steps,        |
|   or max steps reached                   |
+==========================================+
         |
         v
+------------------+
|  Post-loop        |   advance_game_clock()
|  Cleanup          |   check_player_death()
+------------------+
         |
         v
+------------------+
|  Persist Turn     |   Turn -> DB, world_state -> campaign,
|  + Background     |   fact_extraction (async), compression (async)
+------------------+
         |
         v
    turn_complete -> WebSocket -> Frontend
```

## Dice Roll Flow (click-to-reveal)

```
LLM calls request_dice
    |
    v
Agent: _prepare_dice() -> events + result_str
    |
    v
Agent yields: dice_roll -> await_player
    |
    v
WebSocket: sends dice:roll, await:dice_reveal
    |                                    |
    v                                    v
WebSocket: clear() + blocking loop   Frontend: shows dice "Roll!" button
    |                                    |
    |                              Player clicks
    |                                    |
    |                              sends {type: "dice_revealed"}
    |                                    |
    v  <---------------------------------+
WebSocket: set() event, break loop
    |
    v
Agent: wait() returns (event already set)
    |
    v
Dice result_str fed back to LLM as tool result
LLM narrates outcome in next step
```

## Current Tools

### Visible (frontend events)

| Tool | Args | Effect | Frontend |
|------|------|--------|----------|
| `request_dice` | check, dc, stat, reason | Server-side d20 roll | Dice UI, click-to-reveal |
| `invoke_npc` | name, context | Calls NPC director LLM | NPC dialogue bubble |
| `start_combat` | enemies[] | Init combat state + initiative | CombatTracker overlay |
| `end_combat` | — | Reset combat state | CombatTracker hides |
| `apply_damage` | target, amount, damage_type | Damage to combatant HP | CombatTracker update |
| `update_hp` | change, reason | Player HP +/- | HP bar flash |
| `add_item` | name, description, quantity | Add to inventory | Toast notification |
| `remove_item` | name | Remove from inventory | Toast notification |

### Silent (no frontend event)

| Tool | Args | Effect |
|------|------|--------|
| `move_to` | location | Updates world_state.location |
| `update_quest` | name, status, description | Add/complete quest |
| `change_npc_disposition` | npc, delta, reason | NPC relationship +/- |
| `log_event` | description | Append to narrative event_log |
| `set_scene_mood` | mood | CSS mood transition |
| `advance_time` | minutes | Game clock forward |

## What's Missing — Planned Tools & Hooks

### Template-Aware Hooks (auto-inject, no LLM action needed)

```
invoke_npc("Marta") called by DM
    |
    v
PRE-HOOK: load_npc_profile("Marta")
    |
    +-> template.content.npcs where name="Marta"
    |     -> personality, motivation, secret, role, location
    |
    +-> world_state.npcs.Marta
    |     -> disposition_toward_player, interaction history
    |
    +-> MERGE both into enriched context
    |
    v
NPC Director receives full profile -> responds in character
```

```
move_to("Thornhaven") called by DM
    |
    v
POST-HOOK: load_location("Thornhaven")
    |
    +-> template.content.locations where name="Thornhaven"
    |     -> description, connections, atmosphere
    |
    v
Tool result includes: "Arrived at Thornhaven: small village...
  Connected to: Forest Path, North Road, Shrine of First Light."
DM can narrate using actual location details.
```

### New Tools to Add

| Tool | Purpose | Priority |
|------|---------|----------|
| `suggest_actions` | Suggest 2-4 player options (replaces old DMResponse field) | HIGH |
| `get_location` | Query location details + connections from template | MEDIUM |
| `update_npc` | Create or enrich NPC in world_state (personality, role, secret) | MEDIUM |
| `search_lore` | Semantic search in template/memory_facts (Phase E, needs pgvector) | LOW |

### System Changes Needed

| Change | Description | Priority |
|--------|-------------|----------|
| Template init | Seed world_state from template at campaign creation (locations, npcs, companions, quests) | HIGH |
| XML system prompt | Rewrite prompt format from markdown+JSON to XML tags | MEDIUM |
| Context slim-down | Pass only relevant fields to system prompt (current location + connections, active NPCs, HP) instead of full JSONB dump | MEDIUM |
| NPC pre-hook | Auto-load NPC profile from template before invoke_npc | HIGH |
| Location post-hook | Enrich move_to result with template location data | MEDIUM |

## Context Passed to LLM

### System Prompt (per-turn)

```
Current structure (markdown + raw JSON):

  BASE_DM_PROMPT (rules, tool guidance, narration style)
  + DEATH_MODE_PROMPT
  + ## Player Character -> full character_data JSON
  + ## Story So Far -> max 5 compressed summaries
  + ## Current World State -> FULL world_state JSON (too much)
  + ## Active Quests -> quests JSON

Target structure (XML, selective):

  <instructions> rules, tool guidance </instructions>
  <character name="Eron" hp="12/20" location="Thornhaven">
    <abilities> STR 16, DEX 12, CON 14 </abilities>
    <inventory> Sword, Health Potion x2 </inventory>
  </character>
  <scene>
    <location name="Thornhaven">
      Small village. Connected to: Forest Path, North Road.
    </location>
    <npcs_present> Marta (friendly), Guard (neutral) </npcs_present>
    <time> Day 3, evening, autumn </time>
    <mood> tense_anticipation </mood>
  </scene>
  <history> compressed summaries </history>
  <quests> active quest list </quests>
```

### Messages (conversation history)

- Last 8 turns verbatim: `[{user: action}, {assistant: narration}]`
- Older turns: up to 5 compressed summaries in system prompt
- Beyond ~30 turns: only reachable via pgvector semantic search (Phase E)

## Data Flow: Template -> World State -> Context

```
template.yaml (authored by user)
    |
    v
seed_templates() -> templates table (JSONB content)
    |
    v
create_campaign() -> campaigns table
    |                  world_state: {} (EMPTY - needs init!)
    |
    v [MISSING: should init from template]
    |
    v
Each turn: tools modify world_state
    |  move_to -> location
    |  change_npc_disposition -> npcs.X.disposition
    |  start_combat -> combat_state
    |  advance_time -> clock
    |  log_event -> narrative.event_log
    |
    v
world_state persisted to campaigns table (JSONB)
    |
    v
build_context() reads world_state -> system prompt
```

## Provider Support

| Provider | Tool Calling | Streaming | Notes |
|----------|-------------|-----------|-------|
| Google Gemini | Native | Yes | Best free option. Use `maximum_remote_calls=0` (not `disable=True`) |
| OpenAI | Native | Yes | Most reliable tool calling |
| Anthropic | Native | Yes | Best narrative quality |
| Cohere | Via OpenAI compat | Yes | command-r OK, command-a writes tools as text |
| Local/OpenRouter | Via OpenAI SDK | Yes | Depends on model |

---

## Ideas & Future Directions

### Living World — Background Simulation

The world should evolve autonomously between and during player turns.

```
Player ends turn N
    |
    v
Post-turn background jobs (fire-and-forget):
    |
    +-> fact_extraction (already exists)
    +-> compression (already exists)
    +-> NEW: world_tick()
            |
            +-> For each active faction: evaluate agenda progress
            +-> For each NPC with active motivation: advance goal
            +-> Random events table: check if something triggers
            +-> Weather/season progression
            +-> Store changes in world_state + narrative.event_log
            |
            v
        Next turn: DM sees updated world_state,
        can reference events that happened "off-screen"
```

**Example**: Player ignores the mines for 10 turns. `world_tick()` advances The Hollow faction's agenda. By turn 15, bandits appear near Thornhaven. The DM discovers this in the world_state and narrates it naturally — the player didn't cause it.

**Implementation options**:
- **Simple**: Rule-based tick (faction.agenda_progress += 1 per turn, trigger at thresholds)
- **Medium**: Budget LLM decides what happens ("Given these factions and their goals, what changed in 1 day?")
- **Complex**: Each faction has its own agent running in background (expensive but immersive)

### Memory Architecture — Three-Tier Recall

```
Tier 1: ACTIVE WINDOW (8 turns verbatim)
    Full player action + DM narration in messages[]
    The DM "remembers" these perfectly

Tier 2: ROLLING SUMMARY (always in system prompt)
    Every 5 turns: batch summary compressed into 2-3 sentences
    These 5-turn summaries are ALSO used to update a GLOBAL SUMMARY
    Global summary = single paragraph, updated every 5 turns,
    captures the entire story arc so far
    Always injected in <history> section

    Example global summary after 30 turns:
    "Eron awoke at the Shrine with no memory. Lyra guided him to
    Thornhaven where he learned of the mine threat. After gaining
    Marta's trust she revealed the artifact. Eron descended into
    the mines, fought hollow creatures, and discovered Aldric's
    son alive but corrupted. Currently negotiating with The Hollow."

Tier 3: SEMANTIC SEARCH (on-demand via tool)
    pgvector memory_facts table
    DM calls recall_memory("artifact Marta found") -> gets specific facts
    Used for: "wait, what did Marta say about the artifact 20 turns ago?"

DM has a tool to query Tier 3:
    recall_memory(query) -> top-K relevant facts from all turns
```

```
Turn 1-5:   verbatim in window
Turn 6-10:  compressed to batch summary A
Turn 11-15: compressed to batch summary B
            -> summaries A+B used to update global summary
Turn 16-20: compressed to batch summary C
            -> summary C merged into global summary
...
Global summary stays ~200 words, always in system prompt
Batch summaries rotate out, global summary persists
```

### Companion System

```
Current: companions exist in world_state but have no behavior

Target architecture:

Player action arrives
    |
    v
DM narrates + calls tools
    |
    v
Post-narration hook: companion_react()
    |
    +-> For each active companion:
    |     - Load personality from template
    |     - Load loyalty, trust, mood from world_state
    |     - Budget LLM: "Given [personality] and [situation], how does [companion] react?"
    |     - Output: {dialogue, action, mood_change, loyalty_change}
    |
    v
Companion reactions injected as events
    |
    v
Frontend: companion bubbles in narrative stream

Companion state in world_state:
{
  "Lyra": {
    "loyalty": 6,        // 0-10, affects willingness to follow
    "trust": 5,          // 0-10, affects what they share
    "mood": "worried",   // affects tone of dialogue
    "location": "with_player",  // or "Thornhaven", "scouting"
    "relationship_summary": "Lyra trusts Eron but worries about his recklessness.",
    "last_interaction": "Turn 12: argued about entering the mines"
  }
}

Companions can:
    - Refuse actions (loyalty < 3)
    - Leave the party (loyalty = 0)
    - Reveal secrets (trust > 8)
    - Act independently (mood-driven)
    - Die (if in combat and HP reaches 0)
```

### Possible New Tools — Brainstorm

| Tool | Category | Description |
|------|----------|-------------|
| `suggest_actions` | UX | Suggest 2-4 player options as clickable buttons |
| `recall_memory` | Memory | Semantic search in memory_facts via pgvector |
| `get_location` | World Query | Load location details + connections from template |
| `get_npc` | World Query | Load NPC profile from template + world_state |
| `update_npc` | World Mutation | Create or update NPC fields (personality, secret, status) |
| `create_npc` | World Mutation | Invent a new NPC on the fly and add to world_state |
| `companion_command` | Companion | Tell a companion to do something (scout, guard, wait) |
| `companion_dialogue` | Companion | Make a companion speak in character |
| `reveal_secret` | Narrative | Mark a secret as discovered (tracks what player knows) |
| `trigger_event` | World Sim | Fire a world event from the event table (rebellion, storm, ...) |
| `check_faction_status` | World Query | See faction agenda progress, disposition, recent actions |
| `update_faction` | World Mutation | Change faction state (agenda, disposition, active plans) |
| `describe_environment` | Narration | Load atmospheric details for current location + weather + time |
| `flashback` | Narrative | Narrate a memory/vision (loads context from early turns via pgvector) |
| `inner_monologue` | Narration | DM narrates the player's thoughts/feelings (for dramatic moments) |
| `foreshadow` | Narrative | Plant a narrative seed in the event_log for future payoff |
| `time_skip` | World Sim | Advance days/weeks. Triggers multiple world_ticks. Major state changes. |
| `weather_change` | Atmosphere | Set weather (affects mood, travel difficulty, NPC behavior) |
| `lock_area` | World Mutation | Make a location inaccessible until condition is met |
| `unlock_area` | World Mutation | Open a previously locked location |
| `give_xp` | Progression | Award experience points (if leveling system is added) |
| `level_up` | Progression | Trigger level-up flow (stat increases, new abilities) |
| `play_sound` | UX | Trigger a sound effect on the frontend (ambient, combat, dramatic) |
| `show_image` | UX | Display a generated/stored image (location art, NPC portrait) |
| `show_map` | UX | Reveal or update a map view of known locations |
| `reputation_change` | Social | Adjust player standing with a faction (affects NPC behavior, prices, access) |
| `trade` | Economy | Open trade interface with an NPC (buy/sell items) |
| `craft` | Economy | Combine items to create new ones (if crafting system exists) |
| `rest` | Survival | Short/long rest mechanics (HP recovery, spell slots, random encounters) |
| `set_objective_marker` | UX | Highlight a location or NPC on the UI as current objective |
| `journal_entry` | UX | Add a styled entry to the player's journal (different from log_event — player-facing) |

### Possible System Modifications

| Change | Description |
|--------|-------------|
| **Template init at campaign creation** | Seed world_state with template data (locations, NPCs, factions, companions) |
| **XML system prompt** | Structured tags instead of markdown + raw JSON |
| **Selective context** | Only pass current location, present NPCs, active combat — not full JSONB |
| **Global story summary** | Single paragraph updated every 5 turns, always in context |
| **World tick engine** | Post-turn background job that advances faction agendas and world events |
| **Companion autonomy** | Companions react to situations, have opinions, can refuse or act independently |
| **NPC memory** | Each NPC remembers past interactions with the player (stored in world_state) |
| **Dynamic difficulty** | Adjust DCs and encounter difficulty based on player performance history |
| **Branching story arcs** | Template defines trigger conditions, system tracks and activates arcs |
| **Multi-language narration** | DM narrates in player's preferred language (already have default_language setting) |
| **Turn analytics** | Track: avg narration length, tool calls per turn, dice outcomes, model usage — dashboard |
| **Player journal** | Auto-generated recap the player can read, separate from DM internal log |
| **Permadeath consequence** | On ironman death: export campaign story as PDF/markdown keepsake |
| **Session summaries** | "Last time on your adventure..." recap when player returns after 24h+ |
| **Parallel NPC actions** | Multiple NPCs act simultaneously in a scene (already supported, needs prompt guidance) |
| **Emotional state tracking** | Track player character's emotional arc for narrative coherence |
| **Economy system** | Gold, prices, shops, supply/demand based on world events |
| **Reputation gates** | Certain areas, quests, or NPC interactions locked behind reputation thresholds |
| **Dream sequences** | DM can trigger dream/vision scenes that use different prompt rules |
| **Unreliable narrator mode** | DM occasionally lies or withholds info (horror campaigns) |

---

## Architectural Findings & Decisions

### Project Constraints
- **Open source on GitHub**, BYOAK (bring your own API key)
- **Self-hosted**: each user runs their own instance locally — no scaling concerns
- **v2 multiplayer**: local instance shared between players (turn flow TBD)
- **Configurable features**: expensive AI patterns (world sim, NPC enrichment, summary LLM) must be opt-in via config so users with cheap budgets can still play

### Key Decisions Locked In

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Global story summary | **Hybrid configurable** — LLM if `enabled: true`, rule-based concatenation fallback | Respects BYOAK budgets, gives quality option to users who can afford it |
| Tool groups | **Config YAML** — `saga.config.yaml` defines which tools activate per scene state | Mod-friendly, self-documenting, no code changes to extend |
| NPC pre-hook | **Template + memory + optional LLM enrichment** — base profile from template, last 3 interactions from world_state, LLM enrichment only if enabled | Layered cost: free baseline, premium quality opt-in |
| Tool max in context | **~12 tools max** | Empirical limit for reliable tool calling on medium models |
| Tool group strategy | **State-driven**: always-on core + combat tools (if combat) + social tools (if NPCs present) + companion tools (if companion active) | Keeps DM context lean, prevents tool selection confusion |
| Multiplayer model | **Deferred** — architecture should be flexible enough not to lock decisions | v2 problem, focus v1 on solid single-player |

### Anti-Patterns to Avoid

- Loading all 30+ tools into every prompt (degrades model accuracy)
- Single LLM doing both narration AND world simulation (bias from player history pollutes world updates)
- Mutating world_state without event log (loses debug-ability and time-travel)
- Hardcoding feature toggles in code (breaks BYOAK promise)
- Stuffing entire template into system prompt (token waste, irrelevant context)
- LLM-generated content with no fallback (breaks for users with no API key)

### Patterns Adopted from Serious AI Game Architectures

| Pattern | Source | SAGA Application |
|---------|--------|------------------|
| **Multi-Agent Hierarchy** | Modern AI agents research | DM agent + World Sim agent (separate LLMs, separate contexts) |
| **Event Sourcing** | Distributed systems | Turn log as immutable event stream, world_state derivable |
| **Tool Group Activation** | LangChain, OpenAI Assistants | State-driven dynamic tool loading |
| **BDI for NPCs** | Game AI / cognitive science | NPC has beliefs/desires/intentions in world_state, drives reactions |
| **Tension Curve** | Left 4 Dead "AI Director" | Rule-based score adjusts DC and pacing |
| **Lazy Loading via Tools** | RAG architectures | DM queries world via tools, doesn't dump everything into context |

---

## Roadmap — v1 / v2 / v3

### v1 — Solid Single Player Foundation

**Goal**: Make the current agentic loop produce coherent, immersive narrative with the existing 14 tools, fixing the "wrapper around LLM" feeling.

**Tasks (in order)**:

1. **Template world initialization**
   - At campaign creation, seed `world_state` from `template.content`
   - Populate: `locations` dict (name → description, connections), `npcs` dict (name → personality, role, location), `factions`, `companions`
   - Existing migrations stay intact, new template-init runs once at create

2. **Tool groups dynamic loading (config YAML)**
   - New file: `saga.config.yaml` at project root
   - Defines `tool_groups` (e.g. `core`, `combat`, `social`, `companion`)
   - Each group lists tool names and activation conditions
   - `build_context()` filters tools based on world_state (combat_state.active, npcs_present, companion_active)
   - DM context never sees more than ~12 tools

3. **NPC pre-hook in `_run_npc`**
   - Before calling NPC director, load profile from template + world_state
   - Pass enriched context: personality, motivation, secret, last 3 interactions, current disposition
   - Optional LLM enrichment if `features.npc_enrichment.enabled`

4. **Location post-hook in `move_to`**
   - After move_to executes, enrich tool result with location description + connections from template
   - DM next step has narrative context to describe arrival

5. **Selective context in system prompt**
   - Drop full world_state JSONB dump
   - Pass only: current location (description + connections), NPCs present, character vitals, active combat (if any), active quests
   - Reduces token cost, improves model focus

6. **System prompt rewrite to XML**
   - Replace markdown headers + JSON blocks with XML tags
   - `<character>`, `<scene>`, `<history>`, `<quests>`, `<instructions>`
   - Cleaner, more selective field inclusion

7. **Global story summary (hybrid)**
   - Every 5 turns: update global summary
   - LLM mode if `features.global_summary.llm: true`, else rule-based concatenation of batch summaries
   - Always injected in system prompt `<history>` section

8. **`suggest_actions` tool**
   - DM calls it to give 2-4 player options as clickable buttons
   - Recovers the lost feature from old DMResponse

9. **Sprint Phase B playtest bug fixes**
   - 5 frontend bugs from earlier playtest

**v1 acceptance**: Player can play 30+ turns with command-r or Gemini Flash, narrative is coherent, NPCs feel distinct, locations feel real, no tool hallucination, no soft locks.

### v1.5 — Companion + Tension

**Goal**: Add the missing systems that make the world feel populated and dynamic, without yet introducing background simulation.

**Tasks**:

1. **Companion system base**
   - `world_state.companions` extended with: loyalty, trust, mood, location, last_interaction, relationship_summary
   - New tools: `companion_dialogue(name, context)`, `companion_command(name, action)`
   - Companions can refuse actions if loyalty too low
   - Auto-load companion profile from template (same pattern as NPC pre-hook)

2. **NPC memory (BDI lite)**
   - Each NPC in world_state gets: `beliefs`, `last_interactions[]` (max 5), `current_intention`
   - Updated automatically when player interacts (tool calls modify the NPC's beliefs)
   - Pre-hook includes BDI in NPC director context

3. **Narrative tension score (rule-based, free)**
   - Calculated post-turn: combat = +20, dice critical_failure = +15, NPC death = +30, rest = -25, victory = -10, dialogue = -5
   - Stored in `world_state.meta.tension_score` (0-100)
   - Injected in DM context as a hint for pacing
   - Optional: rule-based DC adjustment based on score

4. **Player journal (auto-generated)**
   - Separate from DM internal logs
   - Player-facing recap, regenerated each turn from event_log
   - Frontend: dedicated journal panel

5. **Event sourcing (partial)**
   - All world_state mutations also append to `world_state.narrative.event_log`
   - Each event is structured: `{turn, type, payload}`
   - Not yet "rebuild from events" — just append-only audit trail
   - Sets foundation for v2 event sourcing

**v1.5 acceptance**: Companions feel alive (have opinions, can refuse), NPCs remember the player, scenes have natural pacing, players can read their own story.

### v2 — Living World + Multiplayer

**Goal**: World evolves autonomously between turns. Multiple players can share an instance.

**Tasks**:

1. **World Sim Agent (separate LLM)**
   - New file: `app/core/world_simulator.py`
   - Triggered every N turns (configurable in `saga.config.yaml`)
   - Receives: `world_state` (no player history!), days passed
   - Has restricted tool set: `update_faction`, `trigger_event`, `weather_change`, `update_npc_location`
   - Output: world delta + narrative log of "what happened in your absence"
   - DM next turn sees new world state, narrates discoveries naturally

2. **Macro tool `request_world_update()` from DM**
   - DM can also trigger world sim explicitly (e.g. on time_skip)
   - Same world simulator, on-demand

3. **Procedural quest generation (rule-based)**
   - Combine: faction goals + NPC motivations + active conflicts
   - Output: quest hooks added to world_state
   - No LLM needed — combinatorial logic
   - Optional: LLM polish if budget allows

4. **Full event sourcing**
   - World_state derivable from event log
   - Time travel to any turn
   - Replay system for testing/debugging

5. **Multiplayer infrastructure**
   - WebSocket multi-client per campaign
   - Turn ordering: TBD (sequential vs real-time decided based on playtests)
   - Event sourcing makes state sync trivial (broadcast events, not full state)
   - Per-player view of `character_data`, shared `world_state`

6. **pgvector active**
   - `recall_memory(query)` tool wired to semantic search
   - Hybrid search (vector + tsvector)
   - DM can query "what did Marta say about the artifact?" and get relevant facts

7. **Saved campaign export/import as JSON**
   - With full event log
   - Enables sharing campaigns between players

**v2 acceptance**: World feels alive — factions evolve without player input, NPCs have agendas, multiple players can share a campaign, memories from 100+ turns ago can be recalled.

### v3 — Multi-Agent Hierarchy

**Goal**: Move from "DM does everything" to a coordinated multi-agent system.

**Tasks**:

1. **Director Agent**
   - High-level coordinator, runs every 5-10 turns
   - Decides: pacing, when to invoke world sim, when to escalate to premium model
   - Uses tension score and player engagement metrics

2. **Per-NPC Agents**
   - Major NPCs get dedicated agent threads
   - Each NPC maintains its own conversation memory with the player
   - Agent persists between turns

3. **Companion Agents**
   - Each companion is an independent agent
   - Acts on its own goals, can leave the party autonomously

4. **Procedural content via LLM**
   - Generate side quests, NPCs, locations on demand
   - Bounded by template constraints

5. **Visual generation hooks**
   - Optional tools: `generate_image(scene_description)` via Stable Diffusion API
   - `generate_npc_portrait(npc_name)` cached per NPC

**v3 acceptance**: SAGA is a serious multi-agent AI game framework, comparable to research projects like SIMA or Voyager-style architectures.

---

## Configuration Strategy (BYOAK)

All AI-cost features must be opt-in via `saga.config.yaml`:

```yaml
features:
  global_summary:
    enabled: true
    mode: "rule_based"      # or "llm"
    llm_provider: "gemini"
    llm_model: "gemini-flash"
    interval_turns: 5

  npc_enrichment:
    enabled: false          # off by default
    llm_provider: "gemini"
    llm_model: "gemini-flash"

  world_sim:
    enabled: false          # off by default
    interval_turns: 5
    llm_provider: "gemini"
    llm_model: "gemini-flash"

  companion_agent:
    enabled: true
    use_llm_dialogue: true  # if false, rule-based snippets

tool_groups:
  core:
    always_active: true
    tools: [move_to, advance_time, set_scene_mood, log_event, suggest_actions]
  combat:
    activate_when: "world_state.combat_state.active"
    tools: [request_dice, apply_damage, end_combat, update_hp]
  social:
    activate_when: "len(world_state.npcs_present) > 0"
    tools: [invoke_npc, change_npc_disposition]
  companion:
    activate_when: "len(world_state.companions) > 0"
    tools: [companion_dialogue, companion_command]
```

This keeps SAGA accessible to everyone:
- Free tier: rule-based everywhere, only DM agent uses LLM
- Medium tier: enable global_summary LLM and one or two enrichment features
- Premium tier: all features on, world sim active, NPC enrichment running
