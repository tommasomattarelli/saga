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

- [Memory & AI] Fixed: Gemini multi-turn tool calls no longer fail with a 400, because the thought signature returned with each call is echoed back on the next request (#56).
- [Memory & AI] Personal generation keys and models now reach every foreground and background call, with consented fallback and isolated clients (#73, #74).
- [Infra] Development commands and Git hooks now select pinned Node automatically without changing global runtimes.
- [Infra] Full tests now include both stacks, fail immediately if PostgreSQL cannot start, and always clean up test infrastructure.
- [Infra] Updated vulnerable dependencies across both stacks, with clean runtime audits and two documented development-tool advisories retained for a separate Tailwind migration.
- [Infra] Replaced python-jose with PyJWT, removing vulnerable legacy cryptography dependencies while preserving existing tokens, login and refresh behavior.
- [Memory & AI] Removed direct Anthropic integration while preserving historical keys and Claude access through OpenRouter; retired provider selections now fail explicitly without fallback.
- [Installer] Native installation now uses pinned Python and Node runtimes on every platform, avoiding unsupported system versions and the macOS dependency-installation failure.
- [World & DM] World editing and import/export now reject unsafe paths, Windows device filenames, and symbolic links before accessing files outside a world.
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
- [World & DM] The DM is told how hurt you are as a state — unharmed through near death — instead of a malformed number it was never meant to do arithmetic on.
- [UI] Fixed: a brand-new campaign showed no day count until enough time had passed, because the seeded clock carried only its raw minutes.

### Internal

- Added PostgreSQL regressions for concurrent users, consent combinations, provider policy, ignored legacy variables and database-free model calls.
- Covered generation credentials from #65; embedding credentials remain in ADR 0018 Part B alongside #55.
- Background memory and NPC calls inherit the owning user's configuration, with database read sessions closed before generation and embeddings.
- Removed temperature plumbing, Cohere/Groq factories, and importance scoring; generation uses provider defaults while importance survives only as neutral turn metadata.
- Generation calls resolve personal credentials before use, isolate cached clients by credential and endpoint, and reject unusable profiles before claiming a turn.
- Replaced the provider tiers with one generation model: a single output cap in `saga.config.yaml`, a provider allowlist, migrated call sites and startup validation.
- Added personal generation and embedding profiles, named local endpoints, and server-key fallback consent, with credential provenance in the settings API and migration 006.
- Pinned the ruff pre-commit hook to the locked version and fixed the isort classification of the `alembic` package, so hooks and CI agree on migration imports.
- ADR 0018 is Proposed: one generation model and one embedding model per user, personal encrypted keys with consented server fallback, and a rebuildable embedding index.
- Aligned Ruff hooks with the backend configuration so local commits and CI format repository tooling consistently.
- Covered HTTP authentication and progressive narrative reveal, and enforced the existing frontend coverage thresholds in CI without lowering them.
- Added behavioral coverage for world authoring, including taxonomy edits, node hierarchies, encounter tables and NPC field or psychology migrations.
- Migrated Vitest and coverage together, patched frontend tooling, and made unused type exports internal to satisfy the updated Knip checks.
- Replaced the legacy icon wrapper with tree-shakeable Game Icons exports, removing its React 16 and Webpack 4 dependency tree while preserving class selection.
- Updated Axios and React Router to security-fixed releases without changing React or the application's routing behavior.
- Patched backend test dependencies, including pytest temporary-directory handling and Pygments parsing.
- Updated LangGraph, checkpoints and LangSmith to security-fixed versions without changing provider SDKs, with backend unit and PostgreSQL integration coverage.
- Patched backend HTTP, parsing and cryptography dependencies, with malformed-Host regressions and compatibility coverage for previously encrypted provider keys.
- CI, Docker and native installation enforce the Python lockfile; launchers keep development dependencies excluded, and frontend installation uses standard peer resolution.
- Native installers use the pinned Node version without replacing global runtimes, with real download and cache tests on Linux, macOS and Windows.
- Pinned development, CI and Docker to Python 3.12.14 and Node 24.22.0, with runtime contract checks and unchanged dependency versions.
- Recorded the stabilization order: reproducible runtimes, vulnerable dependencies, provider credentials, quest persistence, then guided gameplay debugging.
- World filesystem tests run on Linux, macOS and Windows for every PR, including native Windows junction checks.
- Moved repository skills to `.agents/skills/`, fixed frontmatter validation, and aligned invocation, tools, and session checks with Codex and `AGENTS.md`.
- Renamed the project guide to `AGENTS.md` and updated active documentation references.
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
- `/dead-code` gained a key mode: static tools cannot see inside a JSONB payload, so dead dict keys need a reader/writer trace instead.
- A reader/writer audit of `world_state` and `character_data` found the DM prompt was shipping a Python dict repr as the player's HP on every turn.
- Dropped what the audit found unread: the flat-location prompt branch, `global_flags`, two `GameContext` fields, and the frontend's stale copy of the world-state allowlist.
