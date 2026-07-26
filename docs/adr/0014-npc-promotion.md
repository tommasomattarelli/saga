# ADR 0014 — NPC promotion: companions & elites

- **Status**: Proposed (all structural forks closed by owner interview 2026-07-12; provisional
  values tagged Refined/TODO settle at implementation. Flips to Accepted after implementation
  + playtest. Implementation is **gated behind 0010 S1-S4 + 0012 S1** — sheet vocabularies.)
- **Date**: 2026-07-12.
- **Context items**: TODO companion line (vision 2026-07-12: "every NPC is recruitable";
  recruitment = content promotion, never schema migration — 0010-I8); owner interview
  2026-07-12 (this design pass, incl. the mid-interview scope extension to bosses/elites and
  a full backcheck round).

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values at
implementation. **TODO** = consciously open.

## 1. Context

Companions today are a **pre-0009 fossil** (grounded 2026-07-12): a separate
`world_state.companions` dict (seeded empty, no writer), a `companion_loyalty` scalar handler
(pre-0005, redundant with the psychology axes), an unused `AICallType.COMPANION_DIALOGUE`, a
dead `turn.companion_actions` column, and a FE `companion-bar.tsx` reading the empty dict.
Meanwhile the NPC substrate got rich: uniform UUID records with psychology, traits, statblock
and class-pool inventory (0009/0003/0010-I8), a dedicated per-NPC acting call with parallel
machinery (`invoke_npcs_parallel`), and secret agendas routed to the NPC's own brain
(0006-A4).

The owner's vision: **every NPC is recruitable**; recruiting **promotes content, never
migrates schema**. During the interview the scope generalized: a companion and a boss are the
same mechanical object with opposite sign — a **promoted NPC**: a record that gains a
**sheet** (skills, abilities, real equipment) and a **dedicated acting brain**. Allied and in
the party → companion. Adversarial → elite/boss — authored in world files, or minted by the
0006 Director (the rebellion's leader, the dead general's successor, an unauthored dungeon
boss).

## 2. Decisions

### A. Identity & data model

- **A1 — One record for life; the party is a list (Decided).** The
  `world_state.companions` dict is **retired** (rung v9). A companion stays its 0009 NPC
  record (UUID, psychology, traits, statblock, inventory) forever; membership is
  `world_state.party: [npc_uuid]`. Recruit = append, dismiss = remove, death = the existing
  0003 death writer (engine also removes from party; `dead` stays terminal — perma-death).
  Party order is cosmetic (bar display only). Rejected: *enriched separate dict* (double
  identity, 0009 resolver/tools blind, the exact schema migration the vision forbids);
  *flag-only membership* (no ordering/cap, O(npcs) scans).
- **A2 — Lean `npc.sheet` sub-block (Decided).** Optional block, only on promoted NPCs:
  `skills {id: level}` (**no XP machinery**), `abilities {id: {level, cooldown_remaining}}`
  (0012 shapes), `equipped {slot: item_uuid}` applying layers to the statblock (D1). The
  statblock stays the combat base; inventory already lives on the record (0010-I8). Engine-
  owned and mutable, **never writable through `update_npc`** (extends the 0009 B2 partition
  + its exhaustive test). Rejected: *full `character_data` clone* (drags the whole
  progression economy per NPC; growth is B5); *no sheet* (no real equip, no abilities — the
  vision undelivered).
- **A3 — Loyalty IS the 0005 psychology (Decided).** The `companion_loyalty` scalar and its
  handler are **removed**. Trust/affection already move from the player's actions; leaving/
  betrayal is narrative (axes + 0006 agenda), **never an engine gate on an axis** — axes are
  world-defined, the engine cannot assume `trust` exists. Rejected: *dedicated `loyalty`
  axis in the bundled default* (engine coupled to world-defined content); *scalar on the
  sheet* (third affect system, contradictory states).
- **A4 — Role is derived, never stored (Decided).** Sheet + in `party` = companion; sheet +
  not in party = elite. A defeated elite talked around joins via the same `recruit_npc`
  (sheet already there); a dismissed companion remains an elite in the world. Zero states to
  sync.

### B. Recruitment, promotion, growth

- **B1 — DM tools `recruit_npc` / `dismiss_npc` (Decided).** 0009-style: F2
  reject-with-candidates resolution, hard engine gates (present at the player's node, alive,
  not already in party, `party_size_max` not exceeded). The DM calls them **after** narrative
  consent — consent/refusal belongs to the npc_director playing its axes (consistent with
  A3: no engine thresholds). Dismissal leaves the NPC at the current node, record intact;
  an NPC leaving of its own will = the DM narrates and calls `dismiss_npc` (same tool,
  inverse initiative). Rejected: *UI rail action* (recruitment is a narrative negotiation —
  a button skips the refusal); *tool + UI confirm* (double consent friction).
- **B2 — Promotion pipeline: deterministic base + background refine (Decided).** One engine
  **promotion service**, callable from two entry points (B4). On promote: immediately write
  a **deterministic base sheet** from `npc_class` + tier (class skills at tier level, equip
  = best I8 items already in inventory); then a **fire-and-forget post-turn LLM call**
  (pattern of `_background_global_summary`/0006) reads traits + class and refines — picks
  character-coherent skills and 1-2 rulebook abilities; the engine validates **every id
  against the rulebook** (invalid entries dropped + logged, never the batch). Refined sheet
  lands next turn; LLM failure ⇒ the base stands. NPCs without `npc_class` get the bounded
  0003/0009 scaffold class first. Rejected: *pure deterministic* (every recruited guard
  identical — "well-generated" undelivered); *synchronous LLM in the tool* (LLM nested in
  the tool executor, perceived latency on the recruitment beat).
- **B3 — Party logistics (Decided).** `party_size_max` config (provisional 3). Party
  members' `location` is **derived** = `player_position`, engine-synced on every
  move/travel; they are in `<npcs_present>` by definition. 0006 consequence: a companion is
  always on-screen ⇒ the Director cannot touch it **except `agenda`** (0006-A5 — the
  traitor still plots). On death: inventory + equipped lootable (plain I8); on dismissal:
  keeps everything.
- **B4 — Three promotion origins (Decided).** (1) `recruit_npc` → companion; (2) **authored
  `sheet` block** on the NPC in the world files (0009 tier-3 validated) → elite;
  (3) **Director change type `promote_npc`** (0006 taxonomy extension, own capability bool,
  off-screen guard A1 applies) → elite: the rebellion leader, the general's successor, an
  unauthored dungeon boss gets a real sheet off-screen.
- **B5 — Growth by DM milestone, re-promotion (Decided).** No parallel XP economy: on a
  growth beat the DM calls `promote_npc(npc, reason)` (the on-screen twin of B4-3, analogous
  to `grant_progress`); the B2 pipeline re-runs **on the existing sheet** (+1 skill, one new
  or upgraded ability, statblock tier up). Caps in config: `max_promotions_per_npc`,
  `max_level_gap` vs the player's `char_level`. Rejected: *static sheets* (guaranteed
  obsolescence on long campaigns); *auto-scale with player level* (non-narrative growth, a
  refine call burst per level-up).

### C. The acting brain (the "mega NPC")

- **C1 — Dedicated extended call for sheet-holders, autonomous (Decided).** The
  npc_director contract **extends** for promoted NPCs: their call (which already plays the
  NPC with psychology + secret `agenda`, 0006-A4) returns dialogue **and/or a structured
  action**. Load-bearing argument: the DM narrator never sees agendas — if the DM moved the
  companion in combat, **the traitor could never betray**; the dedicated call can. Runs on
  the existing parallel machinery (`invoke_npcs_parallel`), budget tier.
- **C2 — Full action space (Decided).** `{say, attack, ability, use_item, assist, pass}` —
  **`pass` is the expected default** (prompt: "intervene only when you have something to
  say/do"), the anti-scene-hijack valve. Engine validates every action against the sheet
  (cooldown in player turns per 0012-A4, costs, item exists) with structured rejects, then
  resolves through the 0003 pipeline (contested rolls, bounded damage — an ability is never
  an auto-win). **Betrayal is mechanically possible by design**: 0003 `attack` is any-pair;
  a companion can strike the player.
- **C3 — Autonomy cadence: always when present (Decided).** Every turn, every present
  sheet-holder (party and elite) gets its call. Config `party_autonomy: always |
  combat_only` (std 14, default `always`) for cost-cutting deployments. "In combat" is
  engine-derived, no modes (0003 killed `combat_state`): stamp `last_hostile_event_turn`
  when an attack/damage event involves the player's side; in-combat =
  `turn - last_hostile_event_turn <= T` (config, provisional 2). Enters on the first attack,
  decays alone. Rejected: *DM-invoked acting* (a forgetful DM = statue companion);
  *hybrid party-engine/boss-DM* (two code paths; the call pattern itself telegraphs who has
  secrets).
- **C4 — Differentiated context, hard caps (Decided).** **Companion** (long relationship):
  identity (traits/backstory), psychology axes+bands toward the player (the emotional memory
  of the relationship), secret `agenda`, sheet, `recruited_at_turn`; `global_summary` +
  per-turn summaries of the last K turns + current scene; **its own dialogue history**
  (existing per-NPC store). **Elite** (scene-local adversary): identity, sheet, `agenda`,
  **faction block** (0006 `agenda`+`moves` — the boss's motivation), psychology only if
  `met_player`; current scene + last K summaries, **no** `global_summary`, tighter cap.
  Separate token caps in config. Rejected: *full history since recruitment* (context
  blow-up; the relationship already lives compressed in axes + dialogue history +
  summaries).
- **C5 — Bounded exception to 0003-B1 (Decided, explicit).** 0003 de-moded combat precisely
  to remove per-enemy LLM calls; this ADR reopens them **only for sheet-holders** (rare,
  stakes-bearing actors). Mooks stay LLM-free through the DM's symmetric `attack` tool —
  0003 economics intact.

### D. Equipment that counts

- **D1 — Equip layers on the statblock (Decided).** A promoted NPC's `equipped` items apply
  0010 layers: weapon → damage_class/attack path, armor → DR. This **fixes the 0010-I8 known
  limit** ("a disarmed guard still hits medium") *for promoted NPCs*; mooks keep the static
  statblock (accepted there — they are extras).
- **D2 — `transfer_item` + strictly-better auto-equip (Decided).** Narrative transfer: "take
  my sword, Lyra" → DM tool `transfer_item(item, to_npc)` (party members present only;
  record moved atomically player↔companion, never duplicated — friendly looting back is
  allowed). After any inventory change the engine re-runs a **deterministic comparator**:
  weapon = damage_class rank (rulebook order), tiebreak tier, then *prefer the weapon whose
  declared skill is on the sheet*; armor = higher DR. **Swap only if strictly better** on
  the primary key — no churn on ties, never on flavor; the player can force a slot verbally
  (DM passes the explicit slot). Exact rank order Refined (comes from the rulebook). A
  "give to…" UI rail action lands with S4. Rejected: *UI-only transfer* (the natural
  spoken flow would dead-end); *defer transfers* (the first legendary drop could never go to
  Lyra).

### E. Surfaces

- **E1 — FE (Decided).** `companion-bar.tsx` rewired to `party` (real records: HP from
  statblock, condition); full **mini-sheet view** in the character modal (party tab):
  statblock/HP, skills, abilities+cooldowns, inventory, equipped. Two exceptions:
  **`agenda` never** (0006-A4: player ✗ — the UI must not spoil the traitor); psychology as
  **named bands only** ("trusted"), not raw numbers.
- **E2 — Prompts (Refined).** Party members stay in `<npcs_present>`; the DM narrator
  additionally sees a compact sheet summary (equip + ready abilities) — exact shape at
  implementation, under the 0008 scene cap. Dialogue for non-promoted NPCs unchanged
  (`invoke_npc`).
- **E3 — Plumbing (Decided).** Tool-group predicate `companion_active` →
  `bool(ws.get("party"))`; `recruit_npc`/`dismiss_npc`/`promote_npc`/`transfer_item` join
  the `social`/`core` groups. `AICallType.COMPANION_DIALOGUE` (verified unused) is
  retired/replaced by the extended acting call's route (exact name Refined).

### F. Schema & migration

- **Rung v8→v9** (v8 is 0006's): add `party: []`; **drop** the `companions` dict (pre-1.0,
  empty in dev — clean drop); `sheet` optional on `NpcEngineRecord` (B2 partition updated);
  `last_hostile_event_turn` in `meta`. `companion_loyalty` handler removed.
  `turn.companion_actions` column is dead — noted, untouched (surgical).
- Authored `sheet` blocks in world files enter the 0009 tier-3 validation (ids checked
  against the world's rulebook).

### G. Config (std 14)

`party_size_max` (prov. 3), `party_autonomy: always|combat_only` (default `always`),
`combat_window_turns` (T, prov. 2), `promotion:` (refine-call tier routing,
`max_promotions_per_npc`, `max_level_gap`), context token caps (companion/elite separate),
Director bool `promote_npcs` (0006 G list). All numbers provisional (Refined).

### H. Testing (std 1/11)

S1/S2 are deterministic-heavy: integration tests on real Postgres for recruit/dismiss gates
(cap, presence, dead, duplicates), rung v9 (dict retired, party preserved), base-sheet
derivation from `npc_class`, refine validation (invalid ids dropped, batch survives; LLM
failure ⇒ base stands), equip comparator (strictly-better, tie = no churn), `transfer_item`
atomicity, location sync on travel, death-writer party cleanup, in-combat window decay,
promotion caps. Acting-call quality (pass discipline, betrayal coherence) is
playtest-gated like 0005 deltas.

## 3. Decided vs Open — quick index

**Decided**: A1-A4, B1-B5, C1-C5, D1-D2, E1/E3, F, G shape.
**Refined**: comparator rank order, extended-call route name + prompt shapes (E2), context
caps, all G numbers.
**TODO**: scoped pgvector recall for companions ("remember the episode 80 turns ago" — add
only if playtest shows the axes+summaries memory isn't enough; blocked anyway on the
embedding-provider bug in TODO.md); "give to…" UI rail action (S4); ability status/durations
(stays 0012's headline TODO); multi-status `node_status` interplay — none needed here.

## 4. Rejected alternatives (with reasons)

Collected per decision above: enriched separate companions dict / membership flag (A1); full
CharacterRecord / no sheet (A2); dedicated loyalty axis / sheet scalar (A3); UI-rail or
double-consent recruitment (B1); pure-deterministic or synchronous-LLM promotion (B2); static
or auto-scaling sheets (B5); DM-moved companions in combat — **defeated by the 0006-A4 agenda
routing**: the narrator can't play a secret it can't see (C1); DM-invoked or hybrid acting
cadence (C3); full-history companion context (C4); UI-only or deferred item transfer (D2).

## 5. Consequences

- **Positive**: recruitment is a promotion, not a migration — the resolver, psychology,
  Director agenda, death writer all keep working on the same record; companion and boss ship
  as one machine; the traitor-companion story becomes *mechanically possible* (agenda +
  any-pair attack + own brain); equipment finally matters on NPCs that matter; the world can
  mint its own bosses (Director) without an author.
- **Trade-off**: +1 budget-tier call per present sheet-holder per turn (`always` default;
  `combat_only` knob for lean deployments) — a deliberate, bounded exception to 0003-B1
  economics, mooks unaffected.
- **Trade-off**: implementation gated behind 0010 S1-S4 + 0012 S1 (sheet reuses their
  vocabularies) — this ADR stays Proposed until that stack lands.
- **Trade-off**: sheet quality depends on one budget LLM call; mitigated by the
  deterministic base (always usable), per-id validation, and milestone re-promotion as a
  repair path.

## 6. Relationship to other ADRs

- **0003** — symmetric `attack` and the death writer are consumed as-is ("ready for
  companions" honored); C5 is an explicit bounded exception to B1's no-enemy-LLM-calls;
  scaffold classes cover promotion of classless NPCs.
- **0005** — loyalty collapses into the axes; consent/refusal and leaving are played, not
  gated.
- **0006** — `promote_npc` joins the Director capability taxonomy (row added there with a
  pointer here); agenda routing (A4/A5) is what makes the autonomous traitor work; party
  members are permanently on-screen for the guard, agenda excepted.
- **0009** — record contract extended (`sheet`), B2 partition + tests updated; F2 resolution
  and lifecycle rules reused untouched.
- **0010** — sheet reuses skill/item vocabularies; I8's known limit fixed for promoted NPCs;
  `transfer_item` completes the I-tool family.
- **0012** — A2's "revisit only with companions" is resolved here: NPC ability use is
  engine-gated through the acting call; **the player-ability prohibition stands** (pointer
  added in 0012).

## 7. Implementation plan (fixed; after 0010 S4 + 0012 S1)

- **S1 — Core (zero LLM).** `party` + `npc.sheet` schema + rung v9; `recruit_npc`/
  `dismiss_npc` + gates; legacy retirement (dict, loyalty handler, FE bar data source);
  location sync; death-writer party cleanup; in-combat stamp.
- **S2 — Promotion.** Deterministic base derivation; background refine call + rulebook
  validation; `promote_npc` DM tool + Director change type (0006 wiring); growth caps;
  authored-sheet validation.
- **S3 — Acting brain.** Extended npc_director contract + parallel wiring; action space +
  engine gates + 0003 resolution; differentiated context assembly + caps; equip layers (D1)
  + `transfer_item` + comparator (D2).
- **S4 — FE.** Party bar on real records; mini-sheet modal tab; "give to…" rail action;
  config panel; en/it strings.

## 8. Notes / sources

Design stands on first principles + verified code (`npc_director.invoke_npcs_parallel`,
`tool_groups.py` predicate, `updater.py` loyalty handler, `world_instantiation.py` seeds,
FE `companion-bar.tsx`) and the 0003/0005/0006/0009/0010/0012 contracts fixed in prior design
passes — no external validation research needed. Mid-interview scope extension
(companion → promotion incl. elites) and the closing backcheck round were owner-driven.
