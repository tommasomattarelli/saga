# ADR 0006 — AI Director layer above the DM

- **Status**: Proposed (direction + all structural decisions fixed via the 2026-07-12 design
  pass — every fork below closed by owner interview; provisional values are tagged and settle
  at implementation. Flips to Accepted after implementation + playtest.)
- **Date**: 2026-06-09; design pass 2026-07-12.
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — item #10; design pass
  2026-07-12 (owner interview). Absorbs the backlog lines: `narrative_arc`,
  `foreshadowing-seeds` lifecycle, `faction_moves`, DM hidden notes / mystery box,
  dawn/dusk clock trigger, and the faction-`disposition` seam deferred by ADR 0005 C4.

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values/wording at
implementation. **TODO** = consciously open.

## 1. Context

SAGA's "Living World" is a core pillar, but today the world only moves as a side-effect of
the DM's tool calls during a player turn — there is no proactive world-mover. Nothing plants
or pays off foreshadowing, advances faction agendas, or moves absent NPCs unless the reactive
turn loop happens to. Grounding (verified 2026-07-12): `world_state.factions` is seeded
`{description, disposition: 0}` at instantiation and **no code writes it**; `narrative` holds
only `event_log`; `node_status`/`edge_overrides` have **no writer** besides instantiation and
expiry; the background fire-and-forget pattern (`asyncio.create_task` + own session +
swallow-and-log) already exists in `app/api/turns.py` (`_background_global_summary`).

The Director is the missing proactive layer: a background agent **above** the DM that owns
the off-screen world — it moves absent NPCs, advances factions, changes distant places,
plants foreshadowing, schedules future events, and feeds discovery back to the player through
rumors. The DM stays the sole authority on the scene in front of the player.

## 2. Decisions

### A. Domain partition — what "off-screen" means (the backbone)

- **A1 — Node-scoped guard, evaluated at apply (Decided).** The forbidden ("on-screen")
  domain is everything anchored to the **player's current node at the moment of apply** —
  not at enqueue time (the player may have moved in between). Deterministic check per
  change: NPC targets with `location == player_position` → discard; `node_status` /
  `edge_overrides` touching the current node → discard; player/`char_data` → always
  forbidden; factions, narrative fields, and any other node → allowed. Rejected: *node +
  adjacent ring* (blocks legitimate nearby movement, needs the route graph in the guard);
  *scene-presence set* (fuzzy, prompt-level concept; lets the Director rewrite the status of
  the place the DM is narrating).
- **A2 — Arrivals are legal (Decided).** The guard checks the target's *current* location,
  not the destination: the Director may move an absent NPC **to** the player's node ("Aldric
  arrives in town"). No contradiction is possible: the apply runs at the start of the turn,
  before the DM node — the DM narrates with the arrival already true.
- **A3 — Write surface: the capability taxonomy (Decided).** Every capability is a typed
  change (C1) and an independent config bool (G):

  | # | Capability | State written |
  |---|-----------|---------------|
  | 1 | move absent NPCs (incl. arrivals) | `npc.location` |
  | 2 | off-screen NPC lifecycle (0009 promise) | `npc.lifecycle` |
  | 3 | evolve absent NPCs | `npc.condition`, `npc.traits` |
  | 4 | secret NPC plotting | `npc.agenda` (new engine field) |
  | 5 | create NPCs (F1) | 0009 creation scaffold |
  | 6 | create factions/cults/rebellions (F2, guardrailed) | `factions` |
  | 7 | advance factions | `factions.{}.agenda` + `.moves` (new) |
  | 8 | change places/routes elsewhere | `node_status`, `edge_overrides` |
  | 9 | plant/ripen foreshadowing | `narrative.seeds` (lifecycle) |
  | 10 | schedule the future | `director_changes` rows with `scheduled_at_minutes` (C4) |
  | 11 | spread rumors (grounded, D2) | `narrative.rumors` |
  | 12 | calibrate tension/arc (advisory) | `narrative.arc` |
  | 13 | keep the mystery box | `narrative.dm_notes` |
  | 14 | world flags | `global_flags` |
  | 15 | promote NPCs to elites (sheet, off-screen) — see ADR 0014 | `npc.sheet` via the 0014 promotion pipeline |

  **Always forbidden**: player/`char_data`, `quests` (a quest is a DM↔player contract — an
  off-screen quest flip would surface un-narrated; the DM reacts to Director *facts* and
  updates quests itself), the clock (turn path only), anything caught by A1.
- **A4 — `npc.agenda` routing (Decided).** New mutable engine field on `NpcEngineRecord`
  (extends the 0009 B2 partition). Written/advanced by the Director; rendered into the
  **`npc_director` prompt** (the NPC must play its own plot — the traitor acts coherently);
  **never** rendered in the DM narrator's scene block (LLMs leak secrets they hold —
  anti-telegraph by construction). Rejected: *DM sees it marked SECRET* (probabilistic leak
  into prose); *Director-only* (the NPC would play its conspiracy blind).
- **A5 — Agenda exception to A1 (Decided).** `npc.agenda` is writable **even on present
  NPCs**: the disjointness rationale is "never contradict what the DM is narrating", and the
  agenda never enters narration (A4) — contradiction impossible by construction. Without the
  exception a plotting companion (always present) could never advance.

### B. Trigger & cycle input

- **B1 — Hybrid trigger, evaluated at end of turn (Decided).** Fire the Director when
  `turns_since_last_run >= N` **or** `clock_minutes_since_last_run >= M` (both std 14). The
  clock leg makes long travel/rest move the world immediately and covers the dawn/dusk
  backlog line; the turn leg keeps seeds/tension alive in clock-light intrigue play.
  `last_run {turn, clock}` stamped in `world_state.meta`. Game-time only — a closed campaign
  never moves (no wall-clock timers). Rejected: *pure turn counter* (blind to time: 3 travel
  days ≠ 10 tavern lines); *pure clock* (intrigue sessions starve the drama side).
- **B2 — Cycle input: summaries + curated state, whole world visible (Decided).** The
  Director receives: `global_summary` + the **per-turn summaries since its last run**
  (already computed every turn — free), factions in full (agenda+moves), NPCs filtered
  (agenda set, or recently touched), active `node_status` entries (readback of its own past
  writes — *not* player-visited nodes), the narrative block, **its own recent applied and
  discarded rows** (C2 audit doubles as Director memory — it learns from discards), player
  position + quests **read-only** (the world reacts to what the player pursues), and a
  coarse map of the whole world tree. Hard token cap (std 14). **No visited-node filter**:
  the distant village burns even if nobody watches — discovery arrives later via rumors or
  ruins; a world that only moves inside the player's view cone is a film set. Player-relevance
  is a **prompt bias** ("most moves near the player's story, some far"), not a schema filter.
  Rejected: *raw recent prose* (×3-5 token cost for a reader that moves the world, doesn't
  rewrite it); *structured state only* (blind to recent story).

### C. Queue → deterministic apply

- **C1 — Typed change records (Decided).** The Director emits changes against a
  **Director-specific handler registry**, mirroring `app/memory/updater.py`'s
  `_register_handler` pattern: one change type per A3 capability, Pydantic schema per type,
  per-type precondition re-check + central A1 guard at apply. Malformed entries are dropped
  and logged individually — never the whole cycle. Rejected: *free-form JSON patch* (guard
  can't know what a patch means; silent corruption, anti-0008-F7); *reusing DM tools*
  (immediate execution, name-based scene-oriented resolution — wrong shape for deferred
  apply).
- **C2 — Dedicated `director_changes` table (Decided, owner override of the
  single-column recommendation).** One row per change: `id, campaign_id, change JSONB,
  status (pending|applied|discarded), scheduled_at_minutes NULL, discard_reason,
  created_at, applied_at`. Why the table won: (a) the queryable audit trail is exactly what
  Director tuning needs (the #1 risk); (b) it doubles as the Director's own **memory** — the
  B2 readback of applied/discarded moves costs nothing extra; (c) the ADR-0001-style race
  disappears by construction (Director INSERTs; the turn path `SELECT … FOR UPDATE`s pending
  rows — never the same row contended). Rows are kept forever (small; audit; retention knob
  only if it ever hurts). Rejected: *JSONB column with atomic append/swap* (no audit, no
  readback); *queue inside `world_state`* (two writers on one JSONB column — the exact race
  this design exists to avoid — plus TOAST write amplification, 0008 C7).
- **C3 — Apply mechanics: exactly-once, before the DM (Decided).** In the turn path, after
  the ADR-0001 claim and **before the DM node**: take due pending rows (`FOR UPDATE`), apply
  them in memory through the handlers, run the DM graph on the already-updated world; at end
  of turn, persist `world_state` and mark rows `applied` **in the same transaction** —
  crash mid-turn leaves rows pending, no double-apply, no lost change.
- **C4 — Scheduled events are rows, not state (Decided).** A change with
  `scheduled_at_minutes` set stays pending until the clock passes it; the take query is
  `status='pending' AND (scheduled_at_minutes IS NULL OR scheduled_at_minutes <= clock)`.
  Same handlers, same A1 guard re-checked at fire time, same audit. **Consequence: campaign
  export/import must carry the pending rows** — the save travels with its future (data
  sovereignty). Rejected: *`world_state.scheduled_events` key* (second fire mechanism to
  test, outside the audit).
- **C5 — Precondition failure = discard, always (Decided).** Target dead/missing, node
  unknown, capability disabled, or A1-blocked → `status=discarded` + `discard_reason`. The
  Director sees its discards in the next cycle's readback and re-plans against fresh state —
  no blind retry, no stale change landing out of context. Rejected: *defer-until-valid with
  TTL* ("the tavern catches fire" decided 15 turns ago fires the moment the player leaves);
  *reconcile at apply* (creative heuristics inside the deterministic path).

### D. Surfaces — how results reach the DM and the player

- **D1 — Facts are ground truth, pressure is advisory (Decided, unchanged).** Hard facts
  flow through world state (scene block, npc blocks — already rendered). A new advisory
  **`<director>` prompt block** for the DM narrator carries: `narrative.arc`
  (tension/beat/pressure — stylistic guidance, never binding plot), seeds worth hinting, and
  `dm_notes` — the mystery box is *for* the narrator (deliberate seeding is its purpose,
  unlike `npc.agenda` where leak is a bug). The DM has no creative veto on facts; the only
  filter is the mechanical consistency check (C5).
- **D2 — Rumors are grounded by construction (Decided).** `add_rumor` **requires a
  `subject_ref`** (real node/npc/faction, typically plus the id of the change that spawned
  it); apply-time precheck: subject exists, else discard. Director workflow: **first
  materialize the fact** (`set_node_status` on the pass: "caravans vanished, raider
  tracks"), **then** point a rumor at it. Verification is free: the player travels there and
  the scene renders the status that really exists. The *why* of the mystery stays in
  `dm_notes`/seeds — later cycles materialize the next layer (the raider den on another
  node). Rejected: *ungrounded seed-rumors* (the player can outrun the Director's cadence —
  guaranteed hole on arrival).
- **D3 — Rumors are spent with `tell_rumor(id)` (Decided).** The DM sees unheard rumors in
  a `<rumors>` block ("if diegetically right, tell one and call the tool"); `tell_rumor`
  flips `heard=true`. No repeats across taverns, and the Director's readback knows what the
  player has heard (it can build on it). Rejected: *TTL only* (repeats; Director blind to
  player knowledge); *heard-on-injection* (injected ≠ narrated; burns rumors never told).
- **D4 — Player surface (Decided).** Sprints 1-3: none — discovery is diegetic (narration)
  only. **S4 introduces it** (owner call): journal integration for heard rumors / discovered
  moves + a Director config panel. Nothing else player-facing.

### E. The Director brain

- **E1 — One structured thinking call per cycle (Decided).** Context (B2) in; a JSON
  document of typed changes + optional arc/notes updates out. Per-entry Pydantic validation
  (drop+log). **Upgrade to an agentic read-tool loop only if playtest proves the single call
  insufficient** — doubted: a cycle makes few moves. Rejected for now: *agentic loop*
  (×2-6 thinking calls per cycle on BYOAK, a whole tool surface to maintain; revisit when
  ADR 0002 offers a queryable graph).
- **E2 — Strictly non-blocking (Decided, binding).** The Director fires **after** the turn
  response is sent (same fire-and-forget pattern as `_background_global_summary`): the
  player must never perceive it. When the API responds, the proposed changes land as pending
  rows; the turn path applies them at the first turn they're available (original ADR timing:
  first turn after the queue is ready, not necessarily N+1). One cycle in flight per
  campaign — if the previous hasn't finished, the trigger skips and re-arms next turn. A
  failed cycle = log + skip (std pattern), never a blocked turn. Rule-15 discipline: read →
  close session → LLM → open session → INSERT rows.
- **E3 — Routing & budget (Decided).** New `AICallType.DIRECTOR`, thinking tier, configured
  in `saga.config.yaml` like every call type (std 8/14). `max_changes_per_cycle` budget —
  oversized output truncated + logged. No loop ⇒ std 19 satisfied trivially.

### F. Creation — the world regenerates

- **F1 — `create_npc` (Decided).** Through the 0009 creation scaffold (standard/rich
  level), `location` required and off-screen (A1 guard). The baron's successor, the
  witch-hunter arriving in the region. Own capability bool.
- **F2 — `create_faction` with guardrails (Decided — owner wanted rebellions and hidden
  cults; all four guardrails adopted).**
  1. **Cap + rate limit**: max K live director-created factions per campaign
     (`max_created_factions`, std 14) + cooldown `faction_creation_cooldown_days` of game
     time between creations; beyond → discard.
  2. **Mandatory grounding**: no faction ex nihilo — the change must reference a parent
     faction (a splinter/rebellion *of* something), a planted seed, or a concrete
     `home_node`; precheck at apply like rumors.
  3. **Born small**: initial `scope` forced to `minor`; growth only through later
     `faction_move`s (`minor → regional → major`) — the cult *becomes* big, playably.
  4. **Provenance mark**: `origin: "director"` + `created_at_turn` on the record —
     distinguishable from authored canon, counted by the cap, filterable/prunable.
  Rejected: *no creation at all* (a killed NPC is a permanent hole; a decreasing-sum world);
  *unguarded faction creation* (minor-cult proliferation dilutes the authored world).

### G. Config (std 14 — hard rule)

Under `director:` in `saga.config.yaml` — `enabled: true` (**on by default**: the living
world is a pillar; off-by-default would make it a hidden feature), `every_turns` (N,
provisional 10), `every_game_minutes` (M, provisional 720), `max_changes_per_cycle`
(provisional 6), `context_token_cap`, `max_created_factions`, `faction_creation_cooldown_days`,
plus **one bool per A3 capability** (`move_npcs`, `evolve_npcs`, `npc_agendas`, `lifecycle`,
`create_npcs`, `create_factions`, `faction_agendas`, `place_status`, `rumors`,
`scheduled_events`, `seeds_arc_notes`, `global_flags`, `promote_npcs` — ADR 0014). A disabled capability is excluded
from the Director prompt **and** rejected at apply (defense in depth, `discard_reason:
"capability disabled"`). All numbers provisional (Refined).

### H. Schema & migration

- **World-state rung v7→v8 (Decided).** `npc.agenda` (new `NpcEngineRecord` engine field,
  mutable, default `null` — updates the 0009 B2 exhaustive partition + its test);
  `factions.{}` gains `agenda: null`, `moves: []`, plus `origin`/`scope`/`created_at_turn`
  on director-created ones; `narrative` gains the `arc`, `seeds`, `rumors`, `dm_notes`
  containers (`event_log` stays). `ALLOWED_WORLD_STATE_KEYS` unchanged — everything lives
  inside existing keys.
- **Alembic**: new `director_changes` table (C2).
- **Export/import**: campaign JSON gains the pending `director_changes` rows (C4).
- **Provisional shapes (Refined)**: `arc = {tension, current_beat, pressure_note}`;
  `seeds = [{id, text, status: planted|advanced|resolved|expired, subject_ref?}]`;
  `rumors = [{id, text, subject_ref, source_change_id?, born_at, heard}]`; `dm_notes` =
  capped list. `node_status` stays single-status per node — known limit, extend to a list
  only if playtest demands it (TODO).

### I. Testing (std 1/11)

The S1 core is fully deterministic (zero LLM): integration tests on real Postgres for the
take/apply/mark transaction (crash mid-turn ⇒ rows stay pending, no double apply), the A1
guard per change type (incl. arrival case A2 and the agenda exception A5), scheduled fire vs
clock, discard reasons, capability-bool rejection, faction guardrails (cap/cooldown/
grounding/scope), rumor grounding precheck, export/import round-trip with pending rows.
Brain-side (S2+): contract tests on output validation (malformed entries dropped
individually); prompt quality is playtest-validated like 0005's axis deltas.

## 3. Decided vs Open — quick index

**Decided**: A1-A5 (node-scoped apply-time guard, arrivals, taxonomy, agenda routing +
exception), B1-B2 (hybrid trigger, curated input, whole-world visibility), C1-C5 (typed
handlers, `director_changes` table, exactly-once apply, scheduled rows, discard-always),
D1-D4 (advisory block, grounded rumors, `tell_rumor`, S4 player surface), E1-E3 (single
non-blocking call, routing, budget), F1-F2 (create_npc, create_faction + 4 guardrails),
G (on by default, capability bools), H (rung v8, table, export).

**Refined (values at implementation)**: N/M/K defaults, token cap, arc/seed/rumor/notes
exact field shapes, prompt wording (incl. the player-relevance bias ratio), NPC filter
freshness window in B2.

**TODO (consciously open)**: `node_status` as list if single-status proves tight;
journal/map presentation details for S4; faction→player `disposition` rework (stays with
ADR 0002 — this ADR only reads/writes `agenda`/`moves`); Director↔graph queries (when 0002
lands).

## 4. Rejected alternatives (with reasons)

- **Inline node in the turn graph** — adds latency to every turn; rejected for background
  fire-and-forget (E2 makes this binding).
- **Direct mutation of live `world_state`** — reopens the ADR-0001 concurrent-write race and
  lets the Director stomp the scene; rejected for table → deterministic apply.
- **All-hard output** (narrative pressure as binding data) — over-constrains the DM's prose;
  facts hard, pressure advisory (D1).
- **On-screen authority** — would contradict the DM mid-scene; node-scoped guard (A1).
- Per-section: adjacent-ring / presence-based domains (A1), DM-visible or Director-only
  agendas (A4), pure-turn / pure-clock triggers (B1), raw-prose / state-only context (B2),
  JSON-patch / DM-tool-reuse queue (C1), JSONB-column / in-world_state queue (C2),
  defer-with-TTL / reconcile-at-apply (C5), ungrounded rumors (D2), TTL-only /
  heard-on-injection (D3), agentic loop now (E1), no-creation / unguarded factions (F2),
  `world_state.scheduled_events` (C4), quests in the write surface (A3).

## 5. Consequences

- **Positive**: the world genuinely moves on its own with zero perceived latency; every
  capability is independently toggleable; "always accepted + disjoint domains" removes
  Director↔DM contention by construction; the table gives exactly-once apply, a tuning
  audit trail, and Director memory in one structure; rumors make off-screen life
  *discoverable and verifiable*; foreshadowing gets an owner with a mechanical payoff path
  (seeds → scheduled events).
- **Trade-off**: a real new agent layer — one thinking call every N turns on BYOAK (owner
  accepted: on by default, kill-switch + per-capability bools); a new table + rung v8 + an
  export-format extension; prompt quality of the single call is the #1 risk and is
  playtest-gated (the audit trail exists precisely to tune it).
- **Trade-off**: consequences surface with up to one cycle of lag — that lag *is* the "world
  moved while you were away" effect.
- **Trade-off**: `npc.agenda` hidden from the narrator means the DM can narrate a traitor
  slightly too innocently; accepted (anti-telegraph wins; the npc_director carries the
  plot).

## 6. Relationship to other ADRs

- **0001** — the apply is a turn-path write inside the claim/session discipline; the
  Director task follows rule 15 (read → close → LLM → open → INSERT).
- **0002** — the graph will be the Director's relational read layer (faction↔faction,
  faction→player `disposition` rework lives there); this ADR only defines the seam
  (agenda/moves are Director-owned narrative state, relations are 0002 state).
- **0005** — psychology axes stay DM/dialogue-owned (on-screen); the Director never writes
  them.
- **0007** — the state-audit pass is the *reactive on-screen* second brain; the Director is
  the *proactive off-screen* one. Separate mechanisms, no shared queue.
- **0008** — the Director is the missing writer for `node_status`/`edge_overrides`; the
  world files author the potential energy, the Director spends it.
- **0009** — off-screen lifecycle writes go through the queue as promised (0009 §"off-screen
  autonomy"); `create_npc` reuses the creation scaffold; `npc.agenda` extends the engine
  record + B2 partition.
- **0003/0010/0012** — orthogonal (resolution/items/abilities are on-screen mechanics); no
  contract shared beyond NPC records.

## 7. Implementation plan (fixed, 0009-§10 style)

Prerequisites: 0008 + 0009 merged (done). Independent of 0003/0010/0012 implementation.

- **S1 — Deterministic core (zero LLM).** `director_changes` table + model + Alembic;
  typed handler registry + A1 guard + preconditions; take/apply/mark transaction in the turn
  path (incl. scheduled take C4); rung v7→v8 (`npc.agenda`, faction fields, narrative
  containers); capability bools enforced at apply; faction guardrails; rumor grounding
  precheck; export/import of pending rows. Integration tests per §I.
- **S2 — Brain.** B2 context assembler (summaries, curated state, readback, token cap);
  Director prompt; `AICallType.DIRECTOR` routing + config block; hybrid trigger + `last_run`
  stamp + in-flight skip; fire-and-forget wiring per E2; output validation + budget.
- **S3 — DM surfaces.** `<director>` advisory block (arc/seeds/dm_notes); `<rumors>` block +
  `tell_rumor` tool (world tool group); `npc.agenda` → `npc_director` prompt routing;
  playtest pass (prompt quality gate, like 0005).
- **S4 — Player surface & polish.** Journal integration (heard rumors, discovered moves);
  Director config panel in the frontend; en/it strings.

## 8. Notes / sources

Original direction: aidm's drama-manager separation (research session 2026-06-09). Design
pass 2026-07-12: all forks closed by owner interview in-session; no external validation
research needed — decisions stand on first principles, the surveyed prior art, and
verified existing code paths (`turns.py` background pattern, `updater.py` handler registry,
0008/0009 world/NPC contracts).
