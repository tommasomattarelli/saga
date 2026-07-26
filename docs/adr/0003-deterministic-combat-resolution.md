# ADR 0003 — Deterministic resolution: unified d20 checks + server-side damage

- **Status**: Proposed (direction + all structural decisions fixed via the 2026-07-12 design
  interview — every fork closed by the project owner; **config default values and the 0010/0012
  integration points remain explicit TODOs**). This design pass supersedes the combat-only
  2026-06-09 draft of this same ADR *in place* (same number, retitled): the resolution frame is
  now **one system for every d20 check in the game**, of which combat is the main consumer.
- **Date**: 2026-06-09; design pass 2026-07-12.
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork B, item #7; design
  interview 2026-07-12 (all calls by the project owner), grounded live in `core/dice.py`,
  `core/dm/dm_tools_executor.py`, `core/combat/combat_graph.py`, `ai/tools/tools_combat.py`,
  `ai/tools/tools_special.py`, `memory/updater.py`, `core/death.py`, `saga.config.yaml`,
  `ai/prompts/dm.yaml`; 0010-E4 coordination asks.
- **Scope note**: this ADR owns **resolution** (any d20 check → outcome tier) and **damage/HP
  arithmetic** (tier → server-computed damage, healing, hazards, player death policy). Out of
  scope: the character sheet / skills / progression / items / armor values (→ **0010**, this ADR
  fixes the seams), active abilities and status-effect durations (→ **0012**), NPC record
  machinery (→ **0009**, this ADR extends its engine contract), world authoring/editor plumbing
  (→ **0008**).

---

## 1. Context

**Grounding (live code, 2026-07-12):**

- `core/dice.py` owns dice server-side: `roll_dice`, advantage/disadvantage (implemented but
  **never wired** — `request_dice` doesn't expose them), and the 6-tier outcome ladder
  (`CRITICAL_FAILURE → … → CRITICAL_SUCCESS`) computed **relative to a DC** the LLM picks
  (`request_dice.dc`, guide "10 easy … 25 very hard" in `dm.yaml`).
- `request_dice` is only active **inside combat** (`saga.config.yaml` `tool_groups.combat`,
  gated on `combat_active`) — out-of-combat checks don't exist as a mechanic, contradicting the
  prompt's general DC guide.
- `apply_damage.amount` is a **free LLM-chosen integer** (unbounded); `update_hp.change`
  likewise for out-of-combat HP. The exact hallucinated-HP bug class that plagues F&F.
- Enemies have **no stats**: `start_combat` takes `{name, hp, max_hp}` (+optional `dex_mod`).
  No attack modifier, no damage die — an enemy attack rolls **nothing**; the DM decides hits
  and damage in prose.
- **No weapon/item data anywhere** (inventory is `{name, description, quantity}` free-form;
  FE class presets carry only abilities + hp).
- Two **drifted duplicate** initiative implementations (`combat_graph.init_combat_node` with
  the B-L5 tiebreak vs `updater._handle_combat_start` plain sort); `current_turn_index`
  advances as a side-effect of every `combat_damage` and **nothing enforces turn order** —
  dead bookkeeping. The prompt must shout ("you MUST call start_combat / NEVER narrate a
  fight") to hold the mode together: the mechanic is fragile by design.
- A death system **exists**: `core/death.py` + `Campaign.death_mode`
  (cronista / destino / ironman), checked every turn (`dm_nodes.py:180`), plus a static
  `DEATH_MODE_PROMPTS` block injected into **every** DM prompt.
- NPCs are typed records with UUID identity, lifecycle, condition, traits (ADR 0009) — but
  **no HP**; the 0-HP death writer works on `initiative_order` entries only.

**The two non-determinism leaks** (from the original draft, both confirmed live): the LLM picks
the DC (it can decide success by nudging difficulty), and the LLM writes HP (it can invent
unbounded numbers).

---

## 2. Decisions

> Legend: **Decided** (settled in the 2026-07-12 interview) / **TODO** (consciously deferred,
> with owner noted).

### A. Unified resolution frame — the generic die

- **A1 — One resolver, every d20 check (Decided).** Fixed absolute bands replace the LLM-set
  DC for **all** checks — combat, stealth, persuasion, lockpicking, everything. `request_dice`
  moves out of the combat-gated tool group and is **always available**. Rejected: combat-only
  scope (two parallel resolution systems, the determinism leak survives out of combat).
- **A2 — Difficulty = LLM-classified level, engine-converted via RNG draw (Decided).** The LLM
  never emits a difficulty number. It classifies the task into one of **6 literal levels** —
  `trivial / easy / normal / hard / very_hard / near_impossible` — with a `reason` shown to the
  player. The engine converts the level to a roll modifier by **drawing uniformly from a
  config range per level** (e.g. `very_hard: [-4, -8]`). Rationale: classification is what an
  LLM does stably ("fortress gate = very hard" holds across turns; "DC 22 vs 24" doesn't); the
  bounded coarse scale removes fine-grained success control; the random draw is the owner's
  deliberate midpoint between deterministic and stochastic. `near_impossible` exists
  explicitly to kill lucky level-1 dragon slaying. The outer gate stays prompt-side: trivial
  actions don't roll, impossible actions auto-fail narratively — the roll covers the uncertain
  middle. Rejected: fixed value per level (owner preference for the draw, accepting that the
  same obstacle re-rolls its weight across attempts); 7+ levels (creeps back toward DC
  granularity, adjacent-level classification gets noisy); Blades-style position shifting bands
  (new concept to teach, same effect as the draw).
- **A3 — Absolute outcome bands 5/10/15 (Decided, values config).** On
  `total = d20 + character modifier + difficulty draw`:
  `≤5 hard_failure · 6–9 soft_failure · 10–14 partial_success · ≥15 full_success`.
  Verified spreads: lvl-1 (+2) vs `normal` → 15/20/25/40%; vs `very_hard` → 45/20/25/10%; vs
  `near_impossible` → full success only on nat 20; endgame (+11) vs `near_impossible` → ~30%
  full. Rejected: harsher bands (≤7/8–11/12–16/17+ — grindy at low level); collapsed
  PbtA 3-band (loses the hard/soft failure distinction the DM already narrates).
- **A4 — Criticals stay natural-only (Decided).** Nat 1 = `critical_failure`, nat 20 =
  `critical_success`, always (current `dice.py` behavior kept). Fixed 5%, build-independent,
  not farmable. A nat 20 on `near_impossible` is a miracle *hit*, never a miracle *kill* —
  bounded damage + HP pools are the real anti-fluke (B5). Rejected: total-based crit
  thresholds (≥25 → endgame crits ~35% of rolls, devalued); confirm-the-20 (extra rule, UI
  friction).
- **A5 — Situational circumstances = advantage/disadvantage, binary with reason (Decided).**
  Task difficulty is the level (A2); *situation* (drunk guard, darkness, ally's help) is
  declared by the LLM as `advantage` / `disadvantage` + reason: roll 2d20 keep best/worst
  (already implemented in `dice.py`, currently dead code — gets wired). No number exists
  anywhere: not config-tunable, not stackable, adv+dis cancel (D&D rule). Future hook: 0012
  abilities/statuses may grant advantage **engine-side** through the same mechanism. **Supersedes the
  original draft's "bounded ±N circumstance modifier"** (and the backlog item `{amount:
  -10..+10}`): a numeric side-channel would reopen the door A2 closed. Rejected: dual channel
  (adv/dis + ±2 — three LLM levers on one roll); folding circumstances into the difficulty
  level (conflates task with situation, unreadable UI).
- **A6 — Character modifier clamp `[-5, +11]` (Decided, values config).** The total
  sheet-produced modifier entering the resolver is clamped D&D-envelope-style (attribute up to
  +5, future skills up to +6). Whatever progression 0010 invents (owner direction noted:
  **use-based skill growth à la Voyage, additive** — percentage multipliers rejected: ×1.10 on
  a +3 modifier rounds away on a d20 scale), the bands stay calibrated: growth is felt
  (+2 → +11 over a career) but `near_impossible` never becomes routine. Today's modifier is
  `(score-10)//2` from creation presets (−1..+3) and there is **no progression system**, so
  the clamp binds nothing yet — it is the contract 0010 must compose into (0010-E1/E3/E4).

### B. Combat — statblocks, one symmetric attack, server-side damage

- **B1 — No combat mode (Decided).** `start_combat` / `end_combat` / initiative / rounds /
  `combat_state`: **removed**. Combat is not a state machine; an attack is *a check with
  damage attached*, available any time. No load-turn, no mode to forget open or closed, no
  shouted prompt rules. Supersedes the original draft's decision 4 (symmetric resolution via
  `NPC_BEHAVIOR` enemy-action calls): enemy actions no longer need an LLM call at all — the
  per-round BYOAK cost disappears. Rejected: implicit engine-managed encounter (keeps a state
  machine + rounds that A1/B4 make unnecessary); keeping explicit tools (status quo fragility).
- **B2 — Everyone hittable is an NPC record; HP always visible (Decided).** HP lives on the
  0009 NPC record — no ephemeral combatant store. Mooks ("three goblins") are **auto-created
  ad hoc** through the existing 0009 creation scaffold (the `invoke_npc`/`update_npc` hook
  pattern), minimal level, statblock from config defaults. One store, one damage path, the
  0009 death writer serves everyone; corpses persist in the world (living-world coherence),
  with a config knob pruning **dead unnamed** records after N game days. Voyage-style: every
  NPC present in the scene shows a **life bar** always — not only "in combat"; scene presence
  already derives from location (0008/0009 scene roster), the player's bar already exists
  (hero badge). Rejected: hybrid record+ephemeral stores (two damage paths — the bug class
  0009 just closed); named-only HP (narrated mook damage = leak #2 back through the window).
- **B3 — Statblock on every combatant, player included (Decided).** New engine fields on the
  0009 record (B2-partition update: all engine-owned/mutable):
  `hp / max_hp` · `defense` (one of the **6 A2 levels** — reuses the enum, no second scale) ·
  `attack_mod` (small int, authored by hand where the world says so; generated/absent →
  default `0`, always clamped by config) · `damage_class` (see B5 — a *stat*, not an item: the
  enemy's bite/greatsword is flavor in narration, no item system needed) · `npc_class` (see
  B3b). Authored world NPCs may declare a statblock (optional, tier-3 validated, editor
  inputs); absent fields fall to `statblock_defaults`. **The player is an NPC to the engine**:
  same shape, `defense` from `player_defense_default` **shifted by DEX at config thresholds**
  (±1 level max, e.g. mod ≥ +4 → one step harder to hit, ≤ −2 → one easier — decided with
  0010-E6, the dex-vs-str balance rationale lives there; armor never shifts defense, it is DR —
  B6) — with one deliberate exception: the player has **no `attack_mod` field**. The player's
  to-hit is always the **sheet-produced modifier** (attribute via `weapon_class_to_stat`, or
  the equipped weapon's declared **skill** through the full 0010-E5 formula once 0010 lands —
  clamped by A6), never a static statblock number; `attack_mod` exists only for NPCs.
- **B3b — `npc_class` anchors statblock coherence (Decided).** The world taxonomy declares
  **`npc_classes`** (generic archetypes: commoner, guard, soldier, commander, royale, beast…
  — world-defined, few and coarse) each carrying a **statblock template**
  (`hp_class` / `defense` / `damage_class` defaults; 0010-I8 later adds each class's item
  pool). Every NPC record carries `npc_class` (authored, or classified by the LLM into the
  enum — reject-with-candidates on unknown); the free-text `role` trait ("imperatore",
  "panettiere") stays descriptive, the class carries the mechanics — a butcher can never have
  general-grade numbers because his class template forbids it. On-the-fly creation (an attack
  on a brand-new name, `update_npc`) accepts **bounded creation classes** — `npc_class`,
  `hp_class` (`weak/standard/tough/boss` → **hp drawn from a config range**), `defense`,
  `damage_class` — LLM emits classes, the engine draws every number; absent → the class
  template, then `statblock_defaults`. The UI shows a **derived threat rating** computed from
  the statblock (rejected: an authored numeric NPC level — a second scaling scale duplicating
  the classes). Fix folded in: the 0009 creation scaffold currently leaves `location = None` —
  auto-created NPCs get **`location = current node`** (the presence guards and the death
  writer rely on it).
- **B4 — One symmetric tool: `attack(attacker, target)` (Decided).** Any pair: player→NPC,
  NPC→player, **NPC→NPC** (companions-ready — the mercenary ally attacking a goblin is
  inexpressible in a player-always-rolls model, which is why that model lost). D&D model: the
  attacker's die. Math: `d20 + attack_mod(attacker) + draw(defense(target))` vs the A3 bands →
  tier → server damage to target. Names resolve through the 0009 F2 resolver
  (reject-with-candidates, B4 typo guard; genuinely new name → mook auto-create per B2).
  Rejected after initially deciding it: player-always-rolls defense (single-die drama, but two
  tool schemas, a second code path, and no NPC-vs-NPC).
- **B5 — Damage = class die × tier scale + attribute mod (Decided, values config).** The LLM
  never emits a damage number. Attack damage classes `unarmed / light / medium / heavy` map to
  config dice (e.g. 1d2/1d4/1d8/1d12). For a statblock attacker the class comes **from the
  statblock**; for the player (no items yet) the LLM **classifies the described weapon** into
  a class — bounded, same pattern as A2 — until 0010 items declare their class themselves.
  The rolling attribute (STR melee / DEX ranged …) derives from `weapon_class_to_stat` config
  mapping, not an LLM choice. Tier scale: `critical ×2 dice · full ×1 · partial ×0.5 (min 1) ·
  failures 0`. At 0 HP: player → death policy (B8); NPC → the 0009 death writer
  (lifecycle=dead), rewired from `initiative_order` matching to the record itself. Rejected:
  flat per-tier damage (weapons indistinguishable); universal single die (dagger = greatsword).
- **B6 — Armor = percentage damage reduction, hook here, values in 0010 (Decided).** Owner
  call, reversing the interviewer's AC-style recommendation with a sound degeneracy argument:
  defense-level shifts stack toward "hit only on nat 20" (legendary armor = immunity), while
  **DR degrades gracefully** (you still get hit; you soak). Armor/wards/rings (0010 items)
  reduce computed damage by a **% drawn from a config range per armor class** (consistent with
  the A2/B7 range-draw pattern), under a **total reduction cap** (config, e.g. 75%) that
  applies the same anti-degeneracy logic to stacking. 0003 fixes the hook: damage application
  is **one engine function** (single write path) with a reducer slot where 0010 plugs in.
  Rejected: AC-style defense shift (degeneracy above); deciding armor values here (items don't
  exist — 0010's).
- **B7 — Hazards & healing = literal classes as % of max HP (Decided, values config).**
  Environmental danger (trap, fall, poison burst) is an enemy without legs: the DM requests a
  **reaction roll** (`request_dice` + `hazard_class`), difficulty classified as usual; the
  tier doses the damage — full = dodged, partial = half, failure = full draw. Hazard classes
  (`minor / serious / deadly`) and heal classes (`minor / strong / full`) are **percentage
  ranges of the target's max HP**, drawn from config — owner's call, deliberately asymmetric
  with dice-based weapons: weapons scale with the wielder (attribute + class), hazards/cures
  are ownerless and the percentage keeps them **relevant at every level** (a 2d8 potion dies
  at 80 HP; a 25–50% one never does). `update_hp` (free LLM integer) is **removed**; healing
  goes through a `heal` tool (class + reason). Rejected: dice-based hazards/heals
  (obsolescence); keeping `update_hp` bounded (a benign-direction free number is still a free
  number).
- **B7b — Healing paths and the jailbreak bound (Decided).** Two rails, split by who acts:
  1. **Self-heal (player uses a potion / casts a healing spell)** — target architecture:
     a **structured UI action** resolved by the engine in a turn pre-hook, **no DM/LLM in the
     loop at all** (the strongest anti-jailbreak: heals only come from consuming owned
     resources). This rail does not exist yet (`submit_action` takes free text only) and is
     exactly 0012's "structured input path"; item→`heal_class` semantics are 0010's. **Fixed
     here as a binding direction**: when 0010+0012 land, self-heal migrates off the DM path
     onto that rail. Interim bridge: free-text "I drink the potion" → DM calls `heal` +
     `remove_item` (imperfect, transitional).
  2. **Other-actor heals (ally healer → player, NPC → NPC)** — stays a DM tool call, bounded
     mechanically, not by prompt: engine guard **healer present in scene** (roster/resolver
     check) + config knob `healing.dm_heal_cap` capping DM-initiated heals per game-day
     (generous default). A jailbroken "the innkeeper fully heals me ×10" hits a server-side
     wall. Rejected: prompt-only guard (no mechanical backstop until 0010/0012).
- **B8 — Player death folds into campaign difficulty (Decided).** The three `DeathMode`
  behaviors survive, renamed and generalized: campaign creation offers
  **facile / medio / difficile**, mapping to the existing `check_player_death` behaviors
  (facile ≈ cronista: never death, narrated consequences; medio ≈ destino: 3 fate
  interventions at rising cost; difficile ≈ ironman: permadeath). The always-injected static
  `DEATH_MODE_PROMPTS` block is **removed** from the DM prompt: death instructions reach the
  DM **only when the player actually hits 0** — which is exactly the dynamic
  `narrative_instruction` the existing per-turn check already produces. Campaign difficulty
  governs **death policy only**: roll and damage math are identical everywhere (bands stay
  calibrated once; roll hardness comes from the fiction). **Documented as a future proposal,
  not implemented**: native difficulty multipliers on the math (facile ×0.75 / medio ×1 /
  difficile ×1.25 on enemy damage), config keys reserved neutral, to re-evaluate after
  playtest.

### C. Flow consequences & scope cuts

- **C1 — Removals and rewires (Decided, consequences of A/B).** Deleted: `combat_state`
  (schema), both duplicate initiative implementations, `current_turn_index`,
  `tools_combat.py`'s `start_combat`/`end_combat`/`apply_damage`/`update_hp`, the
  `combat`/`combat_entry` tool groups, the `_pending_combat_enemies` handoff, the shouted
  COMBAT block in `dm.yaml` (rewritten as short rules for `attack`), the `DC guide` prompt
  line, the static death-mode prompt injection. Rewired: `score_importance`'s
  `+2 if combat_active` becomes a "hostiles recently engaged" signal (derivation from recent
  attack events — implementation detail); the FE combat tracker converts into the **scene
  life bars** (B2); the FE dice payload replaces `dc` with `difficulty level + draw` (tier-arc
  reveal touch-up). The `dm.yaml` rewrite MUST fix the **exchange convention** explicitly:
  when hostiles are engaged, they act every turn (the DM calls `attack` for them in the same
  step) — without rounds this rule is what prevents free-hit combat, so it is a requirement,
  not prompt flavor.
- **C2 — Persistent timed effects: out of scope → 0012 (Decided).** 0003 ships instantaneous
  damage/heal only. Lingering poison/bleed/buffs need a duration system, and 0012 must invent
  one anyway (cooldowns measured in actions): **one future duration system, not two**.
  Meanwhile "the poison weakens you" = narration + the 0009 `condition` field (exists today).
  The old backlog line "tick per round on combat_state" is void (no rounds). Rejected:
  per-player-action ticks here (a subsystem too many); game-clock ticks (a 4-hour travel
  detonates the whole poison — pacing tied to `advance_time` calls).

### D. Tool contracts (the LLM-facing surface)

The LLM emits **classes, levels, booleans, names, reasons — never numbers**.

```
attack(attacker, target,            # any pair; names via F2 resolver
       weapon_class?,               # only read when attacker has no statblock (= player, pre-0010)
       advantage?, disadvantage?,   # A5, with reason
       reason)
  → d20 + attack_mod(attacker) + draw(defense(target)) → tier
  → dice(damage_class) × tier_scale + attr_mod(weapon_class_to_stat) → reducers (B6) → apply

request_dice(check, stat,           # stat: 3-letter enum until 0010-E2 swaps in skill|attribute ids
             difficulty,            # one of the 6 A2 levels — replaces dc, REMOVED
             advantage?, disadvantage?,
             hazard_class?,         # physical-risk checks: failure tiers apply % damage (B7)
             reason)

heal(target, heal_class, reason)    # % draw of target max HP, same single apply function;
                                    # healer must be present in scene, capped by
                                    # healing.dm_heal_cap (B7b)
```

Removed: `start_combat`, `end_combat`, `apply_damage`, `update_hp`. Unchanged: `kill_npc` /
`remove_npc` / `restore_npc` (0009 narrative lifecycle — `attack` is for contested violence,
`kill_npc` for uncontested on-screen death), `invoke_npc`, and the rest. All three resolution
tools live in the always-on `core` group.

### E. Config (std 14 — hard rule)

**Every value in this ADR lives in `saga.config.yaml`; the code hardcodes nothing.** New keys
(defaults fixed at S1): `resolution.outcome_bands`, `resolution.difficulty_levels` (6 × range),
`resolution.char_mod_clamp`; `combat.damage_classes`, `combat.weapon_class_to_stat`,
`combat.tier_damage_scale`, `combat.attack_mod_clamp`, `combat.statblock_defaults`,
`combat.hp_classes` (weak/standard/tough/boss → hp ranges, B3b),
`combat.player_defense_default` + `combat.defense_dex_shift` (thresholds, B3),
`combat.damage_reduction_cap`, `combat.dead_unnamed_prune`;
`hazards.classes` + `hazards.tier_scale`; `healing.classes` + `healing.dm_heal_cap` (B7b);
`campaign_difficulty.death_policy`
(+ reserved neutral `multipliers`). Advantage has no keys (it is not a number). The
`npc_classes` statblock templates are **world taxonomy**, not config (world-defined
vocabulary, 0008 P0 pattern). Tool groups: `combat`/`combat_entry` removed,
`attack`/`request_dice`/`heal` join `core`.

### F. Migration / compatibility

- **World-state rung v7→v8**: drop `combat_state`; add statblock fields to every NPC record,
  backfilled from `statblock_defaults` (the rodato 0009 v6→v7 pattern). A save frozen
  mid-combat loses its in-flight fight (non-record `initiative_order` combatants vanish) —
  accepted pre-1.0, same posture as 0008-J2.
- **Alembic**: `Campaign.death_mode` → `difficulty` with mapping (cronista→facile,
  destino→medio, ironman→difficile); `DeathMode` enum removed, `check_player_death` kept and
  reparameterized.
- **World authoring (0008/0009 touch)**: optional authored statblock on `NpcRecord` (tier-3
  validation, editor inputs, export/import round-trip); 0009 B2 mutable/immutable partition
  test extended with the four new engine fields.
- **Frontend**: wizard death-mode step → difficulty (i18n en/it); dice payload + tier-arc;
  combat tracker → scene life bars; presets/sheet untouched.

### G. Testing (std 1/11)

Unit (seeded RNG): band edges, level draws within range, clamps (char mod, attack_mod,
reduction cap), tier damage scale, nat-crit precedence. Integration (real DB): full attack
pipeline for the three pair directions; mook auto-create + typo-guard reject; 0-HP paths
(death writer on record; all three death policies); hazard/heal % draws; reducer slot with
cap; rung v8 on a real v7 save; `request_dice` out of combat. Regression: no tool can write a
free HP number anymore (the removed-tools set stays removed).

---

## 3. Decided vs Open — quick index

**Decided**: A1–A6, B1–B8 (incl. B3b npc_class + B7b healing paths), C1–C2, D, E (keys), F, G,
sprint plan (§7); player DEX defense shift (B3, with 0010-E6); weapon-skill to-hit seam
(B3/0010-E5).
**Open (TODO)**: config default *values* (bands 5/10/15 and clamp [−5,+11] fixed; level
ranges, damage dice, % ranges, caps proposed at S1 and tuned in playtest) · `Power → effect`
mapping for 0012 abilities (owned here, settled when 0012 lands — 0010-E4c) · 0010
integrations: `skill|attribute` ids in `request_dice` (0010-E2), armor DR classes + item-declared
weapon classes (DEX-defense: settled, B3/0010-E6) · prune policy
details · the "hostiles engaged" importance signal derivation · prompt wording pass (backlog:
post-implementation tuning session).

## 4. Rejected alternatives (with reasons)

LLM-set DC (root cause — fine-grained success control, unstable across turns) · combat-only
scope (two systems, leak survives) · fixed per-level values (owner prefers the draw; midpoint
deterministic/random) · 7 levels (DC granularity creep) · Blades position mechanic (new
concept, same effect) · total-based crits (endgame ~35% crit, devalued) · confirm-the-20
(friction) · numeric circumstance ±N — original draft + backlog item (numeric side-channel
reopens A2) · percentage skill multipliers (round away on d20 scale) · implicit
engine-managed combat mode (needless state machine) · explicit start/end tools (fragile,
shouted prompts) · player-always-rolls defense (no NPC-vs-NPC → companions dead end) ·
ephemeral/hybrid combatant stores (two damage paths) · named-only HP (narrated mook damage) ·
flat tier damage / universal die (weapons indistinguishable) · AC-style armor shift
(stacks to nat-20-only immunity — owner's degeneracy argument) · dice-based hazards/heals
(level obsolescence) · bounded-but-free heal numbers (still a free number) · math-affecting
campaign difficulty (triple balancing surface; multipliers parked as proposal) · timed effects
in scope, both variants (subsystem creep; duration system belongs with 0012) ·
Judge/Narrator split (unchanged from draft: deterministic tiers make a scoring call
redundant) · llm-rpg `base × LLM-scaling` damage (the tier is the scaling).

## 5. Consequences

- **Positive**: every roll in the game is auditable (level + reason + draw + bands shown);
  HP can never be hallucinated (no tool accepts a number); combat needs zero extra LLM calls
  (enemy actions are engine math — BYOAK per-turn cost drops); one resolution path serves
  player, enemies, companions and hazards; balance is config; the fragile combat state machine
  and its shouted prompts disappear; life bars give the scene persistent stakes (Voyage).
- **Trade-offs**: difficulty granularity is 6 coarse classes + a draw — accepted (determinism
  is the priority; the draw and adv/dis give spread). The same obstacle re-draws its weight
  across attempts — accepted knowingly by the owner (A2). Rules drift further from strict
  D&D 5e (no DC, no initiative, no AC) while keeping d20/tiers/abilities flavor — accepted,
  "D&D-flavoured, not D&D". Mook records accumulate in `world_state.npcs` — mitigated by the
  prune knob.
- **Risks**: LLM difficulty-classification quality is the load-bearing assumption (mitigation:
  6 well-separated classes, reason surfaced to the player, prompt-tuning pass in backlog);
  removing `update_hp` means *every* HP change must fit attack/hazard/heal semantics — if
  playtest finds a legitimate case that doesn't, extend classes, don't reopen free numbers.
  Healing has no resource economy until 0010/0012 (free DM heals) — bounded meanwhile by the
  scene-presence guard + `dm_heal_cap` (B7b), retired when the self-heal rail lands.

## 6. Relationship to other ADRs

- **0009 (NPC enrichment)** — extends its engine contract (statblock fields in the B2
  partition), reuses its F2 resolver + typo guard + creation scaffold + death writer; the
  writer moves off `initiative_order` onto the record.
- **0010 (character customization)** — answers its E4 asks: (a) the modifier is the
  sheet-produced value **clamped by A6** (the "±N circumstance" wording in E4a is superseded
  by A5); (b) `skill|attribute` ids swap into `request_dice` when 0010 lands (E2); (c) armor =
  DR% classes + item-declared weapon classes + the single-apply reducer hook (B6); (d) items
  carry `heal_class` semantics for the self-heal rail (B7b); (e) weapon items declare a skill
  ref feeding the full to-hit formula (0010-E5) and DEX shifts player defense (0010-E6, math
  in B3); (f) `npc_classes` item pools complete the B3b templates (0010-I8). 0003 lands
  first; 0010 plugs in.
- **0012 (active abilities)** — ability effects resolve through this resolver; `Power →
  outcome/damage` mapping owned here, settled with 0012. The **duration system** (statuses,
  cooldowns) is 0012's, absorbing this ADR's C2 cut. Its **structured input path** (UI-selected
  player actions resolved in a turn pre-hook) is the binding rail for self-heals — potions and
  healing spells/mana move onto it, off the DM path (B7b) — and may grant advantage
  engine-side (A5).
- **0008 (world model)** — authored statblocks ride the world loader/tier-3
  validation/editor; the game clock is untouched (C2 rejected clock ticks).
- **0004 (dm_core/game_system)** — its `game_system` contract note ("dice convention + health
  model" aligned with 0003) now points at this unified frame.
- **0005 / 0006 / 0013** — untouched (psychology, off-screen world, UI identity); the life
  bars and dice reveal restyle under 0013's tokens.

## 7. Implementation plan (fixed, 0009-§10 style)

Four sprints on one `adr/0003-deterministic-resolution` branch, each leaving the suite green
and the game playable; small commits per logical unit (repo standard).

- **S1 — Unified resolver (backend, self-contained, playable alone).** `dice.py` absolute
  bands + level draws + clamp + adv/dis wiring; `request_dice` new contract (drop `dc`, add
  `difficulty`/`advantage`/`disadvantage`/`hazard_class`); tool always-on; `resolution.*` +
  `hazards.*` + `healing.*` config; `heal` tool; prompt minimal edit (drop DC guide, teach
  levels); unit + integration for the generic path.
- **S2 — Combat engine.** Statblock fields on records + rung v7→v8; `npc_classes` taxonomy
  templates + `hp_class` draws + creation classes (B3b) + the scaffold `location = current
  node` fix; `attack` tool + damage pipeline + single apply function with reducer slot; mook
  auto-create hook; death-writer rewire; removal of the 4 tools + `combat_state` + both
  initiative paths + tool groups; `combat.*` config; `dm.yaml` combat rewrite; importance
  signal swap; integration suite.
- **S3 — Campaign difficulty + death.** Alembic `death_mode`→`difficulty` + mapping;
  `check_player_death` reparameterized; static prompt block removed; wizard step + i18n;
  reserved-neutral multiplier keys; tests on the three policies.
- **S4 — Surfaces.** FE scene life bars (tracker conversion); dice payload + tier-arc
  (level + draw display); editor statblock inputs + tier-3 validation + export/import
  round-trip; owner playtest in a clean chat (fixes land on this branch); then a single PR →
  main → flip to Accepted.

## 8. Notes / sources

Design interview 2026-07-12 (every fork closed by the project owner; two interviewer
recommendations reversed by owner arguments that won on merit: the level→number draw and the
armor DR-vs-AC call). No external validation research: decisions stand on well-known tabletop
mechanics (PbtA fixed bands, D&D advantage/AC/proficiency envelopes), the live code verified
above, and explicit owner taste. Prior draft content is preserved where still true (leak
analysis, Judge/Narrator rejection) and superseded where the interview overturned it
(decision 4 symmetric-via-NPC_BEHAVIOR, the ±N circumstance modifier, combat-only title).
