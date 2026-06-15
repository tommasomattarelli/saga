# ADR 0009 — NPC enrichment (status, update_npc, removed-NPC archive)

- **Status**: Proposed — **WIP, nothing decided**
- **Date**: 2026-06-15
- **Context items**: Voyage analysis (`scratch/research/voyage.md`); spun off from ADR 0007
- **Scope note**: **Direction only — no mechanics decided.** Requires dedicated deep
  analysis before acceptance.

## Context

SAGA's NPC model is already fairly rich: numeric `disposition` (±100), `personality`,
`motivation`, `secret`, `fear`, `last_interactions`, plus auto-create at three detail
levels (`minimal`/`standard`/`rich`) — see `AGENTIC_ARCHITECTURE.md`.

Comparing against Voyage's NPC handling (per its Narrator Assistant), three concrete
gaps remain that are **not** already owned by another ADR:

- A **physical/behavioural `status`** field (e.g. `alert`, `injured`, `fleeing`).
- A generic **`update_npc` tool** to create/update NPC fields explicitly (already
  listed under "Possible New Tools" in `AGENTIC_ARCHITECTURE.md`).
- A **removed-NPC archive**: soft-delete instead of removal, with a "removed" list an
  NPC can re-enter from (world continuity — a banished NPC can return).

Two Voyage NPC behaviours are **already owned elsewhere** and are explicitly out of
scope here: **NPC↔NPC relationships → ADR 0002** (relationship graph), and **autonomous
routines / NPCs acting while the player is absent → ADR 0006** (AI Director).

## Decision (direction only)

Enrich the NPC model along the three gaps above (`status`, `update_npc`, removed-NPC
archive). **Mechanics, schema, and tool contracts are all open** and to be settled in
the deep analysis.

## Open questions (to resolve in the deep analysis)

1. **`status`**: closed enum vs free-form string; who sets it (DM tool vs derived from
   combat/events); how it surfaces in the `<npcs_present>` prompt block; interaction
   with the existing `is_dead`/`status=dead` pre-hook checks.
2. **`update_npc`**: which fields are mutable; relationship to the existing
   `change_npc_disposition` and the auto-create pre-hook (`npc_prehook.py`) — does
   `update_npc` subsume or complement them; guardrails so the DM cannot rewrite an
   NPC's identity arbitrarily.
3. **Removed-NPC archive**: where the archive lives in `world_state`; re-entry
   mechanics; how it relates to dead NPCs (dead ≠ removed); how the Director (0006)
   and relationship graph (0002) treat archived NPCs.
4. **Auto-create interplay**: how these fields slot into the `minimal/standard/rich`
   detail levels.

## Consequences / risks (preliminary)

- Moderate scope; mostly additive to `world_state.npcs` and the tool set.
- Must stay coherent with ADR 0002 (NPC↔NPC) and ADR 0006 (absent-NPC autonomy) so the
  enriched NPC record is the shared substrate all three operate on.

## Notes

Source: `scratch/research/voyage.md` §3.5. Out of scope (owned elsewhere): NPC↔NPC
(ADR 0002), autonomous off-screen behaviour (ADR 0006).
