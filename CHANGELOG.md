# Changelog

All notable changes to SAGA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This log is curated by hand — it is not a dump of `git log`. Add entries under
`[Unreleased]` as you work, split into `### Highlights` (user-facing) and
`### Internal`. On release the notes move to
`docs/changelog/CHANGELOG-vX.Y.Z.md` (and the GitHub Release) and
`[Unreleased]` is reset; this root file keeps only `[Unreleased]`.

## [Unreleased]

### Highlights
- [Gameplay] Dice rolls now work outside combat too — lockpicking, sneaking, persuading, climbing all resolve on the same d20 frame.
- [Gameplay] The DM classifies how hard a task is instead of picking a target number, so the same obstacle stays as hard the second time you try it.
- [Gameplay] Traps, falls and healing are computed by the engine as a share of your health, and no tool can invent an HP number any more.
- [Gameplay] Combat is no longer a mode you enter and leave: an attack is just an action, available any time, and the engine computes every hit and every wound.
- [Gameplay] Everyone who can be hit is a real character with HP and a statblock drawn from their class, so a butcher can never fight like a general.
- [Gameplay] Campaign creation now offers Easy / Medium / Hard instead of the old death modes; the dice are the same at every setting, only death is.
- [Gameplay] Fixed: the campaign's death setting was never read, so every campaign silently ran as "the player cannot die" — Hard included.
- [UI] Everyone standing in the scene now shows a life bar, in a fight or not, replacing the combat-only tracker.
- [UI] A dice reveal shows the difficulty draw alongside the roll, so every result can be checked rather than trusted.
- [World & DM] The world editor can give an NPC a class and a statblock; leave a field blank and the engine draws it from the class.

### Internal
- ADR 0003 is Accepted: implemented over S1–S4, with dated implementation notes recording where the code contradicted the design.
- Alembic `005` renames `death_mode` to `difficulty` and the world-state fate counter; existing campaigns are converted, and unmappable values now abort the migration instead of nulling the column.
- CLAUDE.md spells out the full check each stack's CI runs — `mypy` and `knip` are gates that a passing test suite says nothing about.
- `npm ci` resolves without `--legacy-peer-deps`: `@eslint/js` was declared at v10 while `eslint` stayed at v9.
- ADR index gained `Blocked by` / `Gates` columns, copied from each ADR's implementation plan and relationship section.
- ADR 0003 S0 pass: config defaults fixed from the verified spreads, exchange convention left prompt-only, S2 split into two branches.
- ADR 0003 S1: `request_dice` moved to the always-on `core` group, `update_hp` deleted, and tool schemas now inline enums Pydantic hoists into `$defs`.
- ADR 0003 S2: world-state rung v7→v8 backfills a statblock on every NPC record and drops `combat_state`; `combat_graph`, both initiative paths and the `score_importance` combat bonus are gone.
- New `/adr-implement` skill captures the sprint half of the ADR workflow — S0 pass, branch topology, and the assumption reconciliation that keeps a gating ADR honest.
- The importance-scoring combat bonus reads a key nothing writes and has never fired; ADR 0016 redirected from fixing the score to retiring it.
