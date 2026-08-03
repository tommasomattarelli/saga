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

### Internal
- `npm ci` resolves without `--legacy-peer-deps`: `@eslint/js` was declared at v10 while `eslint` stayed at v9.
- ADR index gained `Blocked by` / `Gates` columns, copied from each ADR's implementation plan and relationship section.
- ADR 0003 S0 pass: config defaults fixed from the verified spreads, exchange convention left prompt-only, S2 split into two branches.
- The importance-scoring combat bonus reads a key nothing writes and has never fired; ADR 0016 redirected from fixing the score to retiring it.
