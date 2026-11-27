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

- [Memory & AI] Keep player reports and NPC commitments as separate memory facts with reporter attribution (#123)
- [Gameplay] Player actions longer than `gameplay.max_action_chars` are rejected before a turn is claimed, instead of being silently truncated (ADR 0022 R6).
- [UI] Retire the character sheet reputation tab and align faction types with the world-state v9 contract (ADR 0023).
### Internal

- ADR 0022/0023: landed hybrid recall and relational graph designs; ADR 0002 is superseded by both.
- ADR 0023: refined the graph contract with `prominent` edges defaulted from the kind taxonomy, an always-present `<relations>` block, NPC-scoped secondary rows and two separate row caps.
- World-state rung v9 carries `relations` and keys factions by slug; `reputation_change` is retired (ADR 0023).
- `graph.*` knobs with hard bounds and per-kind `prominent` defaults live in `saga.config.yaml` (ADR 0023).
- Authored faction and NPC relations seed the v9 graph with stance bands and `prominent` defaults (ADR 0023).
- Turns persist claim-time `game_minutes`; batch sources carry the frozen clock and history depth (ADR 0023).
- DM `update_relation` opens and upserts edges with typed endpoint resolution and kind validation (ADR 0023).
- Batch output carries `relations[]` with typed wire refs, frozen clock/depth and tool-wins precedence (ADR 0023).
- DM `<scene>` renders prominent relations always and local ones with present NPCs; both silent scene caps are gone (ADR 0023).
- Recall fuses dense and full-text candidates in one history-isolated query, then ranks and dedups them into a typed `<recalled_memories>` block (ADR 0022).
- The second dense branch embeds the composed action-and-scene query; `search_vector` is Postgres-generated and retrieval knobs live in config (ADR 0022).
- `rrf_k=20` is measured; 0.02 boosts are owner-accepted without a gain, with labelled pairs and an offline comparator for recall@5/MRR@5 (ADR 0022).
