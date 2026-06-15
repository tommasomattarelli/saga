# ADR 0010 — Player-character customization (skill progression + configurable abilities)

- **Status**: Proposed — **WIP, nothing decided**
- **Date**: 2026-06-15
- **Context items**: Voyage analysis (`scratch/research/voyage.md`); spun off from ADR 0007
- **Scope note**: **Direction only — no mechanics decided.** Requires dedicated deep
  analysis before acceptance.

## Context

SAGA exposes D&D-style **ability scores** (STR/DEX/CON/INT/WIS/CHA) used as the basis
for dice DCs (`request_dice` carries a `stat`). Two limitations:

- There is **no skill progression** — proficiencies do not grow with use. Voyage has an
  `updateSkill` notion where, e.g., lockpicking improves the more you pick locks.
- The **ability-score system is hardcoded** (the six D&D stats, fixed) and **not
  customizable** — a campaign/template cannot define a different attribute set or
  scale.

## Decision (direction only)

Make the player character **customizable and progressable**: add **skill progression**
(skills that increase with use, consulted by dice resolution) and make the
**ability-score system itself configurable** rather than hardcoded. **The attribute
model, the progression curve, and the tool/config contracts are all open** and to be
settled in the deep analysis — this area was explicitly flagged as needing dedicated
study.

## Open questions (to resolve in the deep analysis)

1. **Skill model**: what is a "skill" vs an "ability score"; closed list vs
   campaign-defined; how skills map onto / coexist with the six abilities.
2. **Progression curve**: how proficiency grows (per-use increments, thresholds, caps);
   who triggers it — a new `update_skill` tool the DM calls, or automatic on relevant
   dice rolls; how it feeds back into `request_dice` DCs.
3. **Configurable abilities**: how a template/campaign declares its attribute set,
   scale, and defaults (config-first, std 14, with guardrails) instead of the
   hardcoded six; migration of existing campaigns.
4. **Character sheet & prompt**: how skills/abilities surface in the `<character>`
   prompt block and the frontend character sheet; token budget impact.
5. **Balance**: preventing runaway progression; sane min/max ranges.

## Consequences / risks (preliminary)

- Touches the character data model, dice resolution (`request_dice`/`tools_special`),
  templates, and the system-prompt `<character>` block.
- Upside: mechanical sense of growth ("I train, I improve") and campaign-defined rule
  systems, reinforcing the customizability goal of ADR 0007.

## Notes

Source: `scratch/research/voyage.md` §3.6 and the SAGA vs Voyage comparison (§4).
Pairs with ADR 0007's "maximum configurability" direction (the configurable ability
system is a concrete instance of it).
