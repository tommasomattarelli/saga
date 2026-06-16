# ADR 0005 — Multi-axis NPC psychology

- **Status**: Proposed
- **Date**: 2026-06-09
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork D

## Context

"Living World — NPC psychology" is a SAGA core pillar, but the current model is
thin: NPC dispositions reduce to a **single scalar** (`NPCDialogue.disposition_change:
int` in `app/ai/npc_director.py`, applied to a per-NPC value in `world_state.npcs`).
A scalar collapses distinct relationship dimensions — an NPC can fear the player,
respect them, and dislike them at once, and a scalar cannot represent that. It also
makes narrative inconsistencies easy (a "friendly" score doesn't stop betrayal
driven by low trust).

Two surveyed repos converge on multi-axis relationship models: ai_rpg's
`dispositions.yaml` (6 independent axes — platonic, trust, respect, romantic, lust,
comfort/fear — each ±200 with named thresholds and a `first_impression_multiplier:
3`), and NEQ's 5D emotional vectors (trust, power, intimacy, fear, respect). The
convergence is the signal; the romantic/lust axes are genre-specific and out of
scope for SAGA.

## Decision

Replace the scalar disposition with a **multi-axis NPC psychology** in the NPC
JSONB: 5-6 independent axes (e.g. **trust, respect, affection, fear**, extensible)
each on a bounded range with **named thresholds** (e.g. trust −X = "wary", +Y =
"confides in you"). Add a **first-impression multiplier** (~×3) that amplifies
disposition shifts on the first meeting, then normalises. `npc_director` emits
per-axis deltas instead of a single `disposition_change`. Axis set, ranges,
thresholds, and the first-impression multiplier live in `saga.config.yaml` (std 14).

## Consequences

- **Positive**: relationships become legible and narratively coherent (mixed
  feelings representable; betrayal/loyalty have mechanical grounding); the DM can
  read named thresholds rather than interpret a raw number; config-first keeps it
  tunable.
- **Trade-off**: the NPC JSONB schema changes — needs a `world_state` schema
  migration (the `migrate_world_state` ladder already supports this; current
  version is 4 → add 5) that lifts existing scalar dispositions into a default axis
  (likely `affection` or `trust`).
- **Trade-off**: more state per NPC and a richer prompt contract for `npc_director`.
  Bounded by capping the axis count (5-6) and keeping thresholds textual/cheap.

## Notes

Distinct from ADR 0002: this ADR holds an NPC's *internal dispositions* (how they
feel about the player); the relationship graph holds *inter-entity relations* (who
is loyal to / opposes whom). They compose — the graph can reference an NPC's
disposition axes when resolving scene context. NEQ's gravitational/crystallisation
retrieval is explicitly **not** adopted (too complex); only the multi-axis
disposition idea is taken.
