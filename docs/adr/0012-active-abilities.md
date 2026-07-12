# ADR 0012 — Active abilities (player-triggered special moves) + the structured input rail

- **Status**: Proposed (spun off from **ADR 0010** on 2026-06-23; trigger/ownership/cooldown
  fixed then; **the 2026-07-12 design pass closed the effect semantics, the point economy, the
  loadout model and the rail shape**. Remaining TODOs: status/duration system design, numeric
  rulebook defaults).
- **Date**: 2026-06-23; design pass 2026-07-12.
- **Context items**: Voyage §3bis (direct observation 2026-06-22); design interviews
  2026-06-23 + 2026-07-12 (all calls by the project owner); ADR 0003 (expanded 2026-07-12 —
  the resolution vocabulary this ADR composes); grounded in `ai/tools/tools_special.py`,
  `api/turns.py` (no structured input exists: free text straight into the graph).
- **Scope note**: owns **active abilities** (invocation, effects, loadout, points) and the
  **design of the structured player-input rail** (UI action → engine, no LLM). 0010 owns the
  rulebook store, `character_data` state, ability points supply, items (`grants_abilities`),
  and implements the **first rail slice** (equip + `use_item`, its S4). Effect *math* is
  0003's resolver — this ADR adds no math of its own.

---

## 1. Context

Voyage exposes active abilities distinct from skills (Power + cooldown + ability points,
themed: Assassinate, Shadow Step…) — special moves, not superpowers. SAGA has no ability
concept and **no structured player input**: `submit_action` takes free text only. The expanded
0003 changed the design space: a bounded resolution vocabulary now exists (difficulty levels,
advantage, damage/heal classes, tiers), and 0003-B7b **binds self-heals to this rail**
(potions/spells resolved engine-only, no LLM in the loop).

---

## 2. Decisions

> Legend: **Decided** / **TODO**.

### A. Ability model

- **A1 — Ability is a rulebook kind (Decided, shape fixed 2026-07-12).** Per-world, in the
  0010 `rulebook` store. **No numeric "Power"** — an ability **composes the 0003 vocabulary**
  (rejected: an authored Power int + conversion table = a second scale parallel to the
  classes):

  ```yaml
  ability assassinate:            # rulebook, tier-3 validated
    check: {skill: sneak}         # what rolls (skill or attribute ref)
    grants: {advantage: true}     # engine-granted on the ability's own roll
    effect: {attack: {damage_class: heavy}}
    cooldown: 10                  # player turns
    cost: {stamina: 3}            # Resource ref (0010-B4)
    levels:                       # optional upgrades (A5)
      2: {effect: {attack: {damage_class: heavy}}, grants: {advantage: true}, cost_points: 2}
  ```

  Effect primitives v1 (closed enum, dropdown-editable, never free text):
  `{attack: damage_class}` · `{heal: heal_class}` · `{grants: advantage}`. A `check` ref is
  validated against the rulebook (reject-with-candidates).
- **A2 — Player-only trigger (Decided, unchanged — the crux).** No DM `use_ability` tool; the
  LLM never deploys special moves. Engine enforces cooldown + cost + loadout at invocation.
- **A3 — Two effect families; the outcome is never a free pass (Decided, sharpened
  2026-07-12).**
  - **Contested** (attack-like): the ability triggers a **normal 0003 roll** (full E3
    modifier, target defense draw, bands) with its engine-granted perks — it **can fail**, and
    damage is the bounded class pipeline. Worked anti-one-shot example: *Assassinate vs a
    boss dragon* = advantage + 1d12, but the `near_impossible`-grade defense draw crushes the
    roll and even a hit is ~5–17 vs an HP pool of 200 — "kill" only ever means HP→0 through
    the death writer, many rolls later. An "execute" auto-effect is exactly what this decision
    forbids; helpless-target executions are fiction (`kill_npc`), not ability mechanics.
  - **Non-contested** (heal / self-buff): no opposition → **succeeds**, but the magnitude is
    the **% range draw of its class** (same as potions, 0003-B7); cooldown + cost are the
    balance. A `grants: advantage` buff applies **only to the ability's own roll** — buffs
    with duration need the status system (§D TODO).
- **A4 — Cooldown in player turns (Decided, unchanged).** Ticks each player turn; engine
  rejects on-cooldown use with a structured error. State in `character_data.abilities`.
- **A5 — Points economy (Decided 2026-07-12).** Earn: **+1 ability point per character
  level-up** (0010-G2). Spend: **unlock** (`unlock_cost` + optional `requires: {skill/level,
  bundle}`) and **upgrade** — an ability may declare `levels`, each an **authored effect
  block** (same closed vocabulary) with its `cost_points`; no emergent numbers. Bundles still
  grant starting abilities (`grants_abilities`, 0010).
- **A6 — Loadout cap (Decided 2026-07-12).** The player owns unlimited abilities but only
  **K active slots** (config, default ~6); swapping is a rail action between turns; **an
  ability on cooldown cannot be swapped out** (kills the "use it, rotate it, dodge the
  cooldown" exploit). Engine-enforced; the FE bar greys out — backend is the authority.

### B. The structured input rail (design owned here; first slice in 0010 S4)

- **B1 — One endpoint, typed actions (Decided).**
  `POST /campaigns/{id}/action/structured` with
  `{type: use_ability | use_item | equip | swap_ability, ref, target?}`. Engine order: gates
  (ownership, cooldown, cost, loadout, rate limits) → deterministic effects (consume item,
  heal draw, equip layers) → for adjudicated abilities, inject the activation into the DM turn
  context; the roll goes through the 0003 resolver with the granted perks and the DM narrates
  the resolved outcome. **Every** rail action (item use included) injects its fact into the DM
  context — the DM must know you drank the potion.
- **B2 — Turn economy (Decided 2026-07-12 — closes the free-chain hole).** `use_ability`
  **consumes the player's turn** (it *is* the action; no free-text action that round).
  `use_item` / `swap_ability` / `equip` are free actions but **rate-limited per turn**
  (config, default 1 each). Rejected: everything-consumes-a-turn (equipping costing a turn is
  punitive).
- **B3 — Targeting (Decided).** An ability declares `target: self | npc | none`; NPC targets
  resolve via the 0009 F2 resolver and must be **present in scene**. Fiction-level
  applicability stays with the DM + the roll (A3) — the engine checks only mechanical gates.
- **B4 — Self-heal migration (binding, from 0003-B7b).** When this rail lands, potion/spell
  self-heals run engine-only here; the DM `heal` tool shrinks to other-actor heals and its
  `dm_heal_cap` stays as the jailbreak wall.

### C. Consequences (FE/API)

Ability bar (K slots, cooldown/cost display, grey-out), unlock/upgrade spend UI, swap UI;
`character_data.abilities` state (0010-F1); prompt projection lists **ready** abilities only
(0010-F2).

### D. Open TODOs

**Status/duration system** (absorbed from 0003-C2: lingering poisons/buffs, durations in
player turns — design at implementation, one system for statuses AND anything 0012 needs
beyond same-roll buffs) · magnitude XP/point numeric defaults (rulebook) · ability-bar UX
details.

---

## 3. Rejected alternatives

DM-invokable `use_ability` (breaks player agency); guaranteed deterministic effects (auto-kill
/ plot bypass); game-time or per-ability cooldown units; **numeric authored Power + conversion
table** (second scale parallel to the 0003 classes — the composition vocabulary already says
everything); free-text effect definitions (unvalidatable); unbounded rail actions per turn
(free 6-ability chains); swapping out on-cooldown abilities.

---

## 4. Relationship to other ADRs

- **0010** — parent: rulebook store, `character_data` state, ability points (G2),
  `grants_abilities` items/bundles; implements the **first rail slice** (equip + use_item,
  S4) per this design.
- **0003** — supplies the whole effect vocabulary (rolls, advantage, damage/heal classes,
  tiers, clamp); B7b binds self-heals to this rail; its C2 defers durations here (§D).
- **0009** — F2 target resolution; NPC abilities explicitly rejected (statblock is the NPC
  sheet; revisit only with companions).
- **0007** — grand-parent direction.

## 5. Implementation plan (fixed; prerequisite: 0010 S1–S4 landed, incl. the rail slice)

- **S1 — Backend core:** Ability kind (levels/costs/composition) + engine gates
  (cooldown/cost/loadout/rate limits) + resolver integration (granted perks) + per-turn tick.
- **S2 — Rail completion + FE:** `use_ability` + `swap_ability` on the rail; ability bar
  (K slots, grey-out); turn-economy enforcement; self-heal migration (B4).
- **S3 — Economy:** earn/unlock/upgrade + spend UI + playtest → PR → Accepted.

## 6. Notes / sources

`scratch/research/voyage.md` §3bis. Interviews 2026-06-23 + 2026-07-12 (owner calls throughout;
headline reversal: Power number dropped for 0003-vocabulary composition). Verified live:
`api/turns.py::submit_action` takes free text only — the rail is greenfield.
