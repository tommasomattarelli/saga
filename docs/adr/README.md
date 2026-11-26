# Architecture Decision Records

One file per decision, append-only: an accepted ADR is never edited — a new one
supersedes it. Naming and the rest of the doc map are in [`../README.md`](../README.md).

**Status** is the ADR's own word. `Accepted` = decided and implemented (or signed
off). `Proposed` = design closed by an owner interview but not implemented yet —
most of the table, and the queue work is drawn from. `WIP` = problem recorded,
nothing decided; do not implement against it.

**Last movement** is the most recent dated pass on the decision — direction,
design pass, or acceptance. The creation date is not tracked here: ADR numbers are
already chronological.

**Blocked by / Gates** are copied from each ADR — its *Implementation plan* heading
and its §*Relationship to other ADRs*. `(soft)` marks a pair that
composes in one direction without either side declaring a gate. They exist because
the numbers are chronological.

```
0003 ─┬─▸ 0010 ─┬─▸ 0012 ─▸ 0014
      │         ├─▸ 0015
      │         └─▸ 0014
      ├─▸ 0004 S2 ─▸ 0017
      └─▸ 0016 (soft)
```


| # | Status | Blocked by | Gates | Last movement | Title | In brief |
|---|--------|------------|-------|---------------|-------|----------|
| [0000](0000-distribution-and-deployment-architecture.md) | Accepted | — | — | 2026-06-16 | Distribution & deployment architecture | How SAGA is shipped and run for two audiences — Docker users and non-technical "download and double-click" users — against a hard PostgreSQL 16 + pgvector dependency that the reference engines avoid by having no database. |
| [0001](0001-db-session-lifecycle.md) | Accepted | — | — | 2026-06-08 | DB session lifecycle for the turn endpoint | Splits the turn handler into two short sessions so none is held open across the LLM graph, and claims `turn_number` with an atomic `UPDATE … RETURNING` instead of a racy read-then-write. |
| [0002](0002-relationship-graph-recall.md) | Superseded by [0022] + [0023] | — | 0014 (soft) | 2026-11-24 | Relationship graph alongside pgvector recall | Split in two: 0022 owns the recall half (R1–R4), 0023 owns the graph half (G1–G6). Its original claim — pure top-K cosine on the naked action — was verified still true in 2026-11. |
| [0003](0003-deterministic-combat-resolution.md) | Accepted | — | 0010 · 0012 · 0014 · 0015 · 0004 S2 · 0016 (soft) | 2026-08-04 | Deterministic resolution: unified d20 checks + server-side damage | One resolution system for every d20 check in the game, with damage and HP arithmetic computed server-side instead of picked and applied by the LLM. Combat is its main consumer, not its scope. |
| [0004](0004-dm-core-game-system-separation.md) | Proposed | 0003 (S2 only) | 0017 | 2026-10-28 | DM core vs game system; per-campaign tone & overrides | S2 YAML/tool contracts, language, bounded turns and clock fix; coherent-travel validation supports prevention, while recovery of existing conflicts remains unreliable; S1 deferred. |
| [0005](0005-npc-multi-axis-psychology.md) | Accepted | — | — | 2026-07-07 | Multi-axis NPC psychology (world-defined axes) | Replaces the single disposition scalar with world-defined axes, so an NPC can fear, respect and dislike the player at once — a scalar cannot represent that, and made "friendly" NPCs betraying the player look like a bug. |
| [0006](0006-ai-director-layer.md) | Proposed | — | — | 2026-07-12 | AI Director layer above the DM | The world only moves as a side effect of the DM's tool calls. Adds a background agent that owns the off-screen world: moves absent NPCs, advances faction agendas, plants foreshadowing, schedules future events. |
| [0007](0007-voyage-adopted-directions.md) | Proposed | — | — | 2026-07-13 | Directions adopted from the Voyage competitive analysis | §1 designs a cheap async state-audit that patches the drift the DM leaves behind (narration says you picked up the sword, `add_item` never fired). §2 stands as direction, §3 stays deferred; the three heavy refactors it spun off are 0008/0009/0010. |
| [0008](0008-world-model-multilayer-yaml.md) | Accepted | — | — | 2026-07-07 | World model: multi-layer, file-authored worlds with a deterministic spatial graph | Replaces the flat `world_state["locations"]` dict with file-authored layered worlds, world-defined vocabularies and a deterministic travel graph. Fixes the world at campaign start only — evolution is 0006, rich NPCs are 0009. |
| [0009](0009-npc-enrichment.md) | Accepted | — | — | 2026-07-26 | NPC enrichment (identity, lifecycle/condition, traits, `update_npc`) | Uniform UUID NPC records with identity, lifecycle and condition, world-defined traits, and a single mutation surface. Excludes NPC↔NPC relations (0002), off-screen autonomy (0006) and affect (0005). |
| [0010](0010-player-character-customization.md) | Proposed | 0003 S1–S2 | 0012 · 0014 · 0015 | 2026-07-12 | Player-character customization (rulebook, items, skill progression) | `character_data` is a free untyped dict seeded by the frontend. Defines a per-world character rulebook, a typed sheet with progression and equipment, item records and placements, and NPC inventory pools. |
| [0011](0011-frontend-e2e-mocked-golden-path.md) | Accepted | — | — | 2026-06-16 | Frontend E2E: mocked golden path (no backend/Docker) | The golden path as a Playwright spec with every `/api/**` call mocked in the browser — no backend, no Docker, no LLM key, because the gap it guards is the cross-page browser flow, not the backend contract. |
| [0012](0012-active-abilities.md) | Proposed | 0010 S1–S4 · 0003 | 0014 | 2026-07-12 | Active abilities + the structured input rail | Player-triggered special moves with loadout, ability points and cooldowns, plus the design of the structured input rail (UI action straight to the engine, no LLM). Effect math belongs to 0003. |
| [0013](0013-ui-visual-redesign.md) | Accepted | — | — | 2026-07-06 | Frontend visual redesign: clean modern dark | Retires the "Grimoire / Illuminated Parchment" identity — rejected as a direction, not just an execution — for a clean modern dark UI. A re-skin on the existing token system, not a rewrite. |
| [0014](0014-npc-promotion.md) | Proposed | 0010 S4 · 0012 S1 · 0003 · [0023] (soft, index only) | — | 2026-11-24 | NPC promotion: companions & elites | Every NPC is recruitable, and recruiting promotes an existing NPC record rather than migrating schema. Retires the pre-0009 `companions` fossil (a separate dict with no writer, a redundant loyalty scalar, a dead column). |
| [0015](0015-commerce.md) | Proposed | 0010 S4 · 0003 | — | 2026-07-13 | Commerce: prices, shops, haggling, services | What things cost, who sells, and how a transaction executes without letting the LLM near the money — prices are computed by the engine only, which excludes "sell it to me for 1 coin" by construction. |
| [0016](0016-importance-scoring.md) | Superseded by [0018](0018-byoak-personal-config-and-embedding-index.md) | 0003 (soft) | — | 2026-10-17 | Importance scoring for model routing | Retired before implementation: with a single generation model per user the score routes nothing and survives only as turn metadata. Superseded by ADR 0018. |
| [0017](0017-npc-dialogue-turn-architecture.md) | Accepted | 0004 S2 (met: #105) | — | 2026-11-04 | NPC dialogue: batched beats and engine-spliced verbatim lines | Owner accepts after frontend playtest and full evaluation; deliver the dialogue contracts while retaining model-quality defects and richer NPC exchanges as follow-ups. |
| [0018](0018-byoak-personal-config-and-embedding-index.md) | Accepted | — | — | 2026-10-20 | BYOAK configuration contract: personal providers, credentials and the embedding index | Personal profiles, encrypted keys and consented fallback are joined by the versioned embedding index and essential settings UI, delivered together in one PR. |
| [0019](0019-quest-persistence-and-database-migrations.md) | Accepted | — | — | 2026-10-20 | Quest persistence and database migration coverage | Quest persistence shipped in #97; the Alembic bootstrap, exact unversioned-schema adoption and migration-backed suites shipped in #98. |
| [0020](0020-batched-memory-and-history-checkpoints.md) | Accepted | — | — | 2026-11-21 | Batched memory production and history checkpoints | S6 integrated evaluation accepted; quality follow-ups and checkpoint canary remain tracked. |
| [0021](0021-unified-structured-generation-and-recovery.md) | Accepted | 0020 S6 base (met: b72a3f2) | — | 2026-11-23 | Unified structured generation and bounded recovery | W5 complete; evaluation harness separates logical results from recovery sends. Live evaluation and S6 return remain owner-gated. Owner decision: tool-enabled DM steps use prompt-only prose with native tools. |
| [0022](0022-memory-retrieval.md) | Proposed | — | — | 2026-11-27 | Memory retrieval: deterministic multi-query, hybrid, no write path | Replaces naked-action cosine with two deterministic queries fused by RRF against pgvector + Postgres full-text, light metadata boosts, 25→5 selection and a structured `<recalled_memories>` block. Runtime config, fallback chain, offline labelled benchmark. Supersedes 0002's recall half. |
| [0023](0023-relational-state-graph.md) | Proposed | #123 (S3 extraction only) | 0014 (soft, index only) | 2026-11-24 | Relational state graph alongside fact recall | Curated edges in `world_state.relations` with world-defined kinds, stance as the only machine semantics and turn+game-time references. Writers: seed, `update_relation` tool, guarded batch extraction gated on #123 (S3 only). Compact XML rows in `<scene>`, both local scene caps removed, faction rekey and reputation retirement. Supersedes 0002's graph half. |
