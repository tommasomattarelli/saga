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
- [World & DM] DM relation notebook shows why each link exists and only in-game time; relations are ranked by importance with cap overflow reported (ADR 0023).
- [World & DM] Faction lore gets its own prompt block and name list; zero-stance reputation bands stay visible (ADR 0023).
### Internal

- ADR 0022/0023: landed hybrid recall and relational graph designs; ADR 0002 is superseded by both.
- ADR 0023 accepted: v9 `relations` keyed by faction slug retires `reputation_change`; authored edges seed stance bands and `prominent` defaults.
- `graph.*` caps and per-kind defaults drive an always-present `<relations>` block, NPC-scoped rows, a separate faction block and game-time `why=`; silent scene caps are gone (ADR 0023).
- DM `update_relation` and batch `relations[]` share typed endpoints, frozen clock/depth and tool-wins precedence; turns persist claim-time `game_minutes` (ADR 0023).
- PR review and eval fixes added kind descriptions, `nemesis`, a single kind catalog, turn-depth-free producer evidence, stance checks, frozen provenance and deterministic replay; live playtest stays owner-gated (ADR 0023).
- Recall fuses dense and full-text candidates in one history-isolated query, then ranks and dedups them into a typed `<recalled_memories>` block (ADR 0022).
- The second dense branch embeds the composed action-and-scene query; `search_vector` is Postgres-generated and retrieval knobs live in config (ADR 0022).
- `rrf_k=20` is measured; 0.02 boosts are owner-accepted without a gain, with labelled pairs and an offline comparator for recall@5/MRR@5 (ADR 0022).
