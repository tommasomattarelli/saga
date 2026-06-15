# ADR 0008 — World model refactor to multi-layer YAML

- **Status**: Proposed — **WIP, nothing decided**
- **Date**: 2026-06-15
- **Context items**: Voyage analysis (`scratch/research/voyage.md`); spun off from ADR 0007
- **Scope note**: **This ADR only fixes the *direction*. No mechanics are decided.** It
  requires a dedicated deep analysis before it can be accepted. The sections below
  record the problem, the chosen direction, and the open questions — not a design.

## Context

Today SAGA's world is a **flat dict** in `world_state.locations` — each location is a
node with a `description` and a `connections[]` list, plus a single
`meta.current_location` string. There is no spatial hierarchy, no coordinates, and no
notion of travel distance/time.

Voyage uses a **4-level hierarchy** (Realm → Region → Location → Area) with canonical
**map coordinates** and **travel times measured in turns**, and — per its
`creator_agent` description — represents a world as a **multi-file artifact** edited
like a codebase ("multi-file world edits").

**Direction decided**: refactor the world model into a **multi-layer, file-based
(YAML) representation** with an explicit hierarchy. This matches both the desired
authoring experience (detailed, layered, hand-editable worlds) and Voyage's
independently-arrived-at multi-file approach.

## Decision (direction only)

Refactor the world from a flat in-`world_state` dict to a **layered YAML world
definition** (Realm → Region → Location → Area, exact levels TBD), authored as files
and loaded into runtime state on demand. **Everything below is open.**

## Open questions (to resolve in the deep analysis)

1. **File organization — the central open sub-decision:**
   - *Option A — one YAML per layer-type*: one file for the world, one for **all**
     regions, one for **all** cities, etc. → few files, each grows large.
   - *Option B — one YAML per entity*: one file for the world, one **per** region, one
     **per** location, etc., in a directory tree → many small files.
   - **Recommendation on record (Claude): Option B**, in a directory tree, with
     lazy-loading. Rationale: load only in-scope entities (token discipline); clean
     diffs and single-entity overrides (data sovereignty); matches `creator_agent`
     surgical multi-file edits; "too many files" is a non-issue with directories,
     whereas Option A's monolith files are exactly what breaks on large worlds.
   - **Convergence (2026-06-15): leaning Option B.** The user's original concern
     (file-sprawl for large worlds) is resolved by the **in-game editor/creator layer**
     (see *In-game world editor* below): users never hand-edit files, so file count is
     a non-issue and per-entity gains (lazy-load, clean diffs, single-entity overrides)
     win. Final confirmation pending the deep analysis.
   - Possible middle path: per-entity with inline nesting until a size threshold, then
     promote to its own file.
2. **Hierarchy depth**: are all four Voyage levels needed, or fewer? Where do "Areas"
   (rooms/zones generated on the fly) live vs pre-authored layers?
3. **Coordinates & travel time**: adopt canonical coordinates + turn-based travel
   (full Voyage spatial model), or hierarchy-only without geometry? How does travel
   time integrate with `advance_time`?
4. **Runtime vs authored split**: what lives in authored YAML (the "Truths": geography,
   factions, political state) vs what is generated live and persisted (dynamic areas,
   loot, relationships)? How does this interact with `world_state` JSONB persistence?
5. **Loader/index**: manifest format, reference resolution (region → its locations),
   lazy-loading strategy, and how authored YAML seeds the campaign `world_state`.
6. **Migration**: how existing flat-dict campaigns/templates migrate; impact on
   `move_to` (flat string → hierarchical address) and on the system-prompt `<scene>`
   block.

## In-game world editor / creator (WIP — coupled, same decision)

The per-entity file model is only viable for non-technical users if they never have to
hand-edit the files. The answer is an **in-game world editor / creator** that sits
*above* the world files: the files stay the deterministic, git-friendly source of
truth, and the editor is the authoring surface. Users create/edit worlds through it and
never touch raw files; it writes **well-formed, cross-referenced, validated** files
(each file points to others through validated references), making the world
deterministic and **preventing broken-reference errors by construction**.

This is the same approach as Voyage's `creator_agent` / "Voyage Studio", which performs
**"multi-file world edits"** rather than exposing files to the user. Editor and file
model are **one decision** here; they may later split into two sprints, but not two
ADRs.

**Open (with the rest of this ADR):**
- **Form**: manual structured UI, an **AI creator agent** (mirroring `creator_agent`;
  if so, a new `AICallType`/provider/model — recall SAGA is BYOAK), or both.
- **Integrity model**: validation/lint rules, how broken references are prevented,
  atomicity of multi-file edits.
- **Scope**: full "studio" vs minimal create-world wizard for v1.
- **Templates**: interaction with the existing `templates/` YAML and campaign seeding.
- **Edit-during-play**: in-session edits and their reconciliation with live
  `world_state` and the Director (ADR 0006).

## Consequences / risks (preliminary)

- Largest of the three spin-off refactors; touches `world_state` schema, templates,
  `move_to`, context building, and persistence.
- Strong upside for authoring, customizability, and the "Living World" pillar; pairs
  with ADR 0006 (the Director moves the off-screen world that this ADR represents).

## Notes

Source: `scratch/research/voyage.md` §2.6, §3.4. Composes with ADR 0006 (off-screen
world mover operates over this model) and ADR 0007 (state-audit reconciles state held
in this model).
