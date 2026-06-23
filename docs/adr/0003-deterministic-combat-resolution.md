# ADR 0003 — Deterministic combat resolution (fixed thresholds + server-side damage)

- **Status**: Proposed
- **Date**: 2026-06-09
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork B, item #7

## Context

`app/core/dice.py` already owns dice server-side: `roll_dice`, advantage/
disadvantage, and a **6-level outcome** ladder (`CRITICAL_FAILURE → HARD_FAILURE →
SOFT_FAILURE → PARTIAL_SUCCESS → FULL_SUCCESS → CRITICAL_SUCCESS`) computed from
`d20 + modifier` vs a **DC**. Two non-determinism leaks remain:

1. **The DC is the LLM's call.** If the model picks the difficulty class each
   check, the same action yields different difficulty across turns, and the model
   can implicitly decide success by nudging the DC — not deterministic enough.
2. **Damage/HP is narrated, not computed.** There is no damage module; the DM LLM
   derives HP swings from the outcome in prose, so it can invent unbounded numbers
   (the exact bug class — dead enemies acting, lost HP — that plagues F&F).

The d6 rules-light systems (PbtA `2d6 + stat` vs fixed `6 / 7-9 / 10+`; Blades'
d6 pool with position/effect) solve (1) by **having no DC at all**: thresholds are
fixed, difficulty comes from the character's modifier (the sheet), not an arbiter.

## Decision

1. **Fixed-threshold resolution.** Drop the LLM-set DC. Resolution is `d20 +
   modifier` compared against **fixed outcome bands** (PbtA-style), keeping the
   existing 6-tier ladder. The modifier is deterministic (character stat + an
   optional **bounded** circumstance modifier with a `reason`, advantage/
   disadvantage style). The LLM emits no raw difficulty number — difficulty is
   expressed through the deterministic modifier, not an invented target.
2. **Server-side damage from the outcome tier.** Map `outcome_tier → damage`
   deterministically server-side (e.g. `FULL_SUCCESS` → full weapon damage,
   `PARTIAL_SUCCESS` → half + a consequence, failures → attacker takes the cost).
   The LLM never writes HP; it narrates the server-computed result. This makes
   llm-rpg's `base × LLM-scaling` formula unnecessary — the tier *is* the scaling,
   and the die decides it.
3. **Config-first.** Outcome bands and the `tier → damage` mapping live in
   `saga.config.yaml` (std 14), so the curve is tunable without code changes.
4. **Symmetric resolution — all combatants (item #7).** The resolver is
   entity-agnostic: player and enemy/NPC attacks run through the *same*
   `resolve(attacker, defender, action) → outcome tier → server-side damage` path.
   Only **action selection** differs — the player types theirs; an enemy/NPC's
   intended action comes from the existing NPC behaviour call
   (`AICallType.NPC_BEHAVIOR` / `app/ai/npc_director.py`). This keeps the combat
   math identical and verifiable for every participant and avoids a separate
   enemy-damage codepath. The "agentic" part (deciding *what* an enemy does) stays
   separate from the deterministic "resolution" part (computing the *outcome*).

## Coordination with ADR 0010 / 0012 (Refined 2026-06-23)

The configurable character system (ADR 0010) makes this ADR's "modifier" source concrete,
**without changing the resolution frame above**:

- **Modifier source.** "character stat" (decision 1) generalizes to **the value produced by the
  0010 character sheet** — `w_attr · attr_mod + w_skill · skill_mod(level)` plus the unified
  modifier layers (creation bundles + buffs/status) — still summed with the bounded circumstance
  modifier. **0003 stays agnostic** to how that value is composed; it receives a number.
- **`request_dice` contract.** The `stat: STR|DEX|…` enum (`tools_special.py`) becomes
  `skill | attribute: id` (world-defined ids, validated against the rulebook,
  reject-with-candidates on unknown — 0010-E2). The engine resolves `skill → parent_attribute`
  before producing the modifier.
- **Ability Power (ADR 0012).** Active abilities are player-triggered "special moves"; their
  **outcome is adjudicated through this resolver** (not an auto-effect). Mapping `Power →
  outcome / server-side damage` is owned here — a TODO to settle when 0012 is built.

Implementation order: this ADR (the resolution frame) lands **before** 0010's sheet plugs into it.

## Consequences

- **Positive**: combat math is fully deterministic and auditable; the LLM's role
  shrinks to narration + a bounded ±N modifier; HP can never be hallucinated;
  balance is a config knob.
- **Trade-off**: less granular difficulty than free D&D DCs — a trivial lock and a
  legendary one feel similar unless differentiated by the modifier/circumstance.
  Accepted: determinism is the explicit priority, and the circumstance modifier +
  stat spread give enough spread.
- **Trade-off**: a departure from strict D&D 5e DC math toward a rules-light
  resolution. SAGA stays "D&D-flavoured" (d20, 6 tiers, abilities) without
  inheriting the arbitrary-DC problem.

## Notes

`dice.py`'s `_determine_outcome` already produces the 6 tiers; the change is
swapping the `vs DC` comparison for fixed bands and adding a `tier → damage`
resolver (new, in `app/core/`). Interacts with the Judge/Narrator split, which was
**not** adopted: with deterministic tiers + server damage, a separate scoring call
buys little and adds a per-turn LLM round-trip — revisit only if narration drifts
from the computed numbers.
