# ADR 0023 — Relational state graph alongside fact recall

- **Status**: Proposed (design closed by the owner interview on 2026-11-24; not yet implemented). **Implementation gate**: the extraction writer (S3 only) stays dark until issue #123 (open as of 2026-11-24) is closed and a real-DB two-speaker test proves both correct attribution and unique resolution of every relation endpoint. S1, S2, S4 and S5 are not gated. No contract below assumes #123 is already fixed.
- **Date**: 2026-11-24.
- **Context items / sources**: ADR 0002 (Proposed, superseded by 0022 + this ADR), 0005, 0006, 0008, 0009, 0014, 0018, 0020, 0021, 0022; issue #123; `scratch/findings-playtest-adr-020.md` (F6/F10); the code map and review produced during the interview.

Legend: **Decided** = settled by the owner. **Refined** = shape fixed, value to be measured during implementation. **TODO** = consciously deferred, with an explicit trigger.

## 1. Context

ADR 0002 designed a relationship graph alongside pgvector recall. Its recall half moved to ADR 0022. Its graph half was never implemented, and its premises were re-verified against the current tree on 2026-11-24:

- Authored `FactionDef.relations {stance -10..10, label}` and `reputation_tiers` are tier-3 validated but **dropped at instantiation**: `world_instantiation.py:127-130` builds factions as `{description, disposition: 0}` only.
- The overlay `factions[].disposition` is seeded to `0` and has no reader and no other writer in the backend.
- `char_data.reputation` is written by the `reputation_change` handler (`memory/updater.py:111-119`) and **read by nothing**; the handler is not exposed as a DM tool.
- NPC↔NPC relations exist nowhere in the codebase.
- There is no `world_state.relations` key and no `update_relation` tool.
- The closest existing artefacts are **not** edges: `FactPayload.category = "relationship"` is prose about a relationship, and `GlobalPayload.relationships` is a tuple of strings in a checkpoint.
- Facts carry `canonical_ref` on resolved NPC and quest entities, attached only from unambiguous successful operations (`producer_contracts.py:114-147`). This is the identity substrate an edge extractor can use without a new resolver for those two types.
- `world_state` has `CURRENT_SCHEMA_VERSION = 8` and a migration registry (`memory/world_state.py`), and saves/export already carry it. That is the natural home for edges — but `ALLOWED_WORLD_STATE_KEYS` (`:58-76`) does **not** contain `relations`, and `validate_world_state` (`:234-242`) strips unknown top-level keys with only a warning.
- ADR 0020 removed the **global** prompt cap `gameplay.context_token_cap`. Two **local** caps survived: `world.scene.scene_context_max_tokens: 700` (`saga.config.yaml:282`) truncates derived scene lines from the tail (`scene.py:103-117`), and `description_max_chars: 600` (`:281`) silently truncates the authored node description before that (`:68-71`). Neither covered `<npcs_present>`, `<time>` or `<weather>`.
- Other inherited silent windows, named here so neither ADR pretends the signals are complete: the player action is cut to 2000 hardcoded characters before the recall embedding (`ai/sanitizer.py:63-67`), and `gameplay.npc_last_interactions_kept: 3` (`saga.config.yaml:131`, `npc_results.py:42-48`) bounds the interaction history used by 0022's gazetteer. The first is fixed by ADR 0022 R6; the second is an accepted bounded window with a TODO trigger. The NPC-speaker prompt limits (`npc_max_lines`, `npc_narrative_max_chars`, `npc_condition_max_chars`) are separate tool/prompt work recorded in `TODO.md`.

Four relational fragments exist and all four are dead in runtime. The consumers 0002 designed for (0006 Director, 0014 acting call) are still unimplemented, which is why this ADR defines the contract without pretending to wire those consumers.

## 2. Scope

### In scope

1. Edge shape, identity, time semantics, storage and lifecycle.
2. The authored taxonomy of relation kinds and its validation boundary.
3. Writers: instantiation seed, DM tool, batch extraction.
4. Rendering into the DM's `<scene>` block, and retirement of both local scene caps.
5. Faction rekeying and retirement of the parallel reputation system.
6. Configuration and tests.

### Out of scope

- Fact retrieval, query construction and ranking: ADR 0022.
- `knows_about` edges, continuity checklists and multi-hop traversal: deferred.
- The Director change type and the 0014 acting-call consumer: contracts only, wired when those ADRs land.
- Supersession or contradiction tracking between **facts**: separate work.
- Consolidation of the DM tool surface (lifecycle tools, unused psychology tool): TODO, §7.
- Backfill of authored relations into existing campaigns; new campaigns only, consistent with 0020.

## 3. Decisions

### P. Perimeter

- **P1 — Open endpoint types (Decided).** An edge endpoint is `{type, id}` with `type ∈ {npc, faction, player, location, item, quest}`. In v1 the tool surface writes only `npc`, `faction` and `player`; `location` and `item` are defined but inert until 0008/0010 work gives them a writer. `quest` is declared and **has a real resolver** — `update_quest` supplies `canonical_ref` — so extraction may emit quest endpoints, but the DM tool does not expose them in v1. The kind vocabulary is a **config default plus a world-authored taxonomy**, never a fixed enum in code.
- **P2 — Edge vs field rule (Decided, binding).** A link is an edge only if all three hold: (a) it is not naturally owned by either record (many-to-many, symmetric or ownerless); (b) it carries a `kind`/`stance`/`label` that changes over time; (c) a consumer reads it *as a relation*. Otherwise it is a record field: `npc.location`, `npc.faction` (0009) and item ownership (0010) stay fields. A faction controlling a location, a faction hunting an NPC, a debt owed by the player and a sword promised to Lyra are edges. Travel topology stays in 0008's spatial graph: **the relational graph never stores topology, the spatial graph never stores stance**.

### E. Edge shape, time and scale

- **E1 — Shape (Decided).** As in 0002 G1, extended with the open endpoint types of P1:
  ```
  {src: {type, id}, dst: {type, id}, kind, stance: -100..100,
   label, since_turn, until_turn?, since_game_minutes, until_game_minutes?}
  ```
  `stance` is the single machine-readable semantic axis; `kind` is an opaque label; `label` carries the human-readable reason. The player is the sentinel ref `{type: player, id: null}`; it has no NPC record.
- **E2 — Two clocks (Decided).** `since_turn`/`until_turn` are `Turn.history_depth` (`models/turn.py:76-80`): completed turns along the shared lineage, child = parent + 1. It is **not** `turn_number`, which is not unique per campaign. A fork copies existing edges with their original depth; a child cannot write into a parent's edge history. The value must be threaded into both writers: `execute_tool`/`execute_with_context` (`tools_base.py:69-86`, `dm_tools_executor.py:162-169`) and `TurnContextSnapshot` for the tool, and `BatchTurnSource` captured **at job creation** for extraction (`batch_source_contracts.py:50-55`) — never reconstructed at publication. `since_game_minutes`/`until_game_minutes` snapshot `clock.total_minutes` at edge open/close: the tool reads `world_state["clock"]`; extraction uses a frozen value that must be **persisted** — `Turn.game_minutes`, stamped from the claim-time `world_state.clock.total_minutes` at turn commit, copied by `load_turn_input` into `BatchTurnSource.game_minutes` (`memory/batch_input.py:47-104`) and included in `source_hash()`. `BatchInput` is rebuilt from persisted turns, not captured once, so a field that is not stamped at commit cannot exist. No live campaign clock read at publication (0020 §8 immutable-source posture). The wire notation is `18t/3d4h` — `t`, `d`, `h` are stable technical keys; the human-readable form is rendered from the same values in `{campaign_language}`. Duration: days when ≥24h, hours when <24h, no minutes; months = 30 days, **year = 120 game days (4×30)**, matching `GameClock.current_season` (`world_state.py:34-43`). Accuracy is bounded by clock advancement (F10: `advance_time` never called in 21 turns); see §4 TODO for a world-authored calendar. No duration is synthesised from turn count.
- **E3 — Unified scale and bands (Decided).** Authored faction relations are seeded at ×10 into the -100..100 scale. Authored `reputation_tiers` become the **band labels** of faction→player edges: the `label` field of `ReputationTier` (`models/world.py:206-212`) is used; `perks` and `penalties` are not carried into the graph. One scale, no second reputation system.
- **E4 — Tombstones (Decided).** Closing an edge sets `until_turn` and `until_game_minutes`; the edge remains as history ("allies until turn 89"). Reopening creates a **new** edge. Two contradictory kinds on one pair (`ally` + `enemy`) are allowed in v1; no automatic closing of opposites. Tombstones are not deletes.

### S. Storage and lifecycle

- **S1 — `world_state.relations` (Decided).** Edges ride the overlay so save/restore/export carry them in the same snapshot; there is no second format to synchronise on restore, and a filter over at most `max_relations` edges is trivial in memory. No dedicated table. The world-state rung must do **all** of: add `relations: []` via migration, add `relations` to `ALLOWED_WORLD_STATE_KEYS` (otherwise `validate_world_state` strips it silently on every merge, `world_state.py:234-247`), rekey factions by slug, and retire `reputation_change`. There are **two turn-path writers** — the explicit tool and the guarded extraction — with tool-wins precedence (W2).
- **S2 — Edge lifecycle (Decided).** Edges reference stable UUID endpoints; `remove_npc` and `kill_npc` do **not** delete edges, consistent with 0009's promise that removed NPCs keep them. A save taken mid-tombstone preserves the `until_*` values. A fork copies the edge array into the new continuation; a late extraction job may not write edges into a head superseded by a load (same fencing posture as 0020 §8). Real-DB tests cover two continuations reusing the same `turn_number`, a mid-tombstone save and a late publish after load.

### T. Taxonomy of kinds

- **T1 — World-defined with a configured default (Decided).** `relation_kinds:` is authored in world files and validated tier-3. When absent, the default set in `saga.config.yaml` applies. `kind` is an **opaque string**: stance, not a second enum, expresses hostility. There is no `custom(label)` special case — every kind is a string, and the taxonomy exists for authoring consistency, tool/LLM guidance and validation. An unknown kind is rejected **with candidates** (F2 posture), never silently accepted.
- **T2 — Taxonomy reaches the writers (Decided).** The default + world kinds are injected into the `update_relation` tool description and into the batch producer's relation instruction; **one shared validator** is used by the seed, the tool and the extraction writer. Without this the validator would be decorative and extraction kinds would be rejected blindly. A test asserts that an unknown kind is rejected with candidates.
- **T3 — No hardcoded semantic buckets (Decided).** Future consumers (0006 Director, 0014 acting call) read `stance`. They must not need a mapping from world-specific labels to `hostile`/`friendly`.

### W. Writers

- **W1 — Three writers (Decided).**
  1. **Instantiation seed**: authored faction relations, plus an authored `relations:` field on world-file NPCs, tier-3 validated; seeds never touch `met_player`. Unresolvable authored targets are dropped with a log, never silently coerced.
  2. **DM tool `update_relation`**: upsert over **open** edges only — same `(src, dst, kind)` with no `until_turn` updates `stance`/`label` in place, never duplicates; if the only matching edge is closed, a **new** edge is created with a fresh `since_turn`/`since_game_minutes`. Both endpoints are resolved per W3; the payload is the delta only, not the graph.
  3. **Batch extraction**: `relations[]` in the same output as facts from the 0020 batch producer. No additional generation call on the successful path. This **extends the 0020 batch output contract** — `BatchPayload`/response schema, producer version, prompt, worked examples and fixtures must be updated, and a larger schema may increase bounded recovery sends under 0021. It does not rewrite the producer implementation or change the fact contract.
- **W2 — Gate and precedence (Decided).** Only the extraction writer (S3) is gated on #123 plus a real-DB test proving correct attribution **and** unique endpoint resolution. The two writers are complementary: tool-only leaves a graph that grows only when the DM remembers it (F10: 0 `advance_time` calls in 21 turns); extraction-only leaves the DM unable to correct it. When both touch the same open triple in one turn, the DM tool wins, because it is an explicit instruction. S1/S2/S4/S5 are not gated.
- **W3 — Endpoint resolution by type (Decided).** F2 is an NPC-only resolver and `canonical_ref` is produced only for NPC/quest operations, so a single resolver is impossible. The wire format from extraction is `{type, name}`; **the model never supplies UUIDs**. Resolution:
  - `npc` → F2 / `canonical_ref`, reject-with-candidates on ambiguity;
  - `faction` → the wire `name` is the display name (`FactionDef` carries both `slug` and `name`, `models/world.py:226-227`); a named `resolve_faction_slug` resolver matches slug first, then display name, rejecting on ambiguity;
  - `player` → the sentinel, special-cased **before** any resolution;
  - `quest` → `canonical_ref` from `update_quest` (extraction only; not in the v1 tool surface);
  - `location`, `item` → rejected by v1 writers, declared for future use.
  An ambiguous or unresolved endpoint is dropped with a log; the rest of the batch still publishes.
- **W4 — Director deferred (Decided).** 0006's change type is a contract in this ADR, not a wired consumer. Connecting it before 0006 exists would write a contract with no way to verify it.

### R. Rendering and the scene caps

- **R1 — Compact XML rows in `<scene>` (Decided).** Relations whose endpoints are both present, plus relations toward the player, are rendered under `<npcs_present>` as
  `<relation from="Lyra" to="player" kind="ally" stance="45" since="18t/3d4h"/>`
  with a dedicated `graph.scene_max_relations` row cap. Rows are structured, not prose — a graph is data, and prose loses countability and limits. The cap counts rows; rows beyond it are **omitted** (not truncated mid-token).
- **R2 — Both local scene caps removed, with no replacement (Decided).** `scene_context_max_tokens: 700` silently truncates derived scene lines from the tail, and `description_max_chars: 600` silently truncates authored descriptions **before** that; neither content is recoverable from another memory tier. This is the same pathology 0020 removed from raw turns, so both go. If a world exceeds the model window, the resulting provider error is classified and surfaced by the existing structured error path (`generation_errors.py:146-147,165-166`), not converted into invisible loss. This reverses the cost premise in 0008 J1 (BYOAK per-turn tokens) and the "under the 0008 token cap" clause in 0002 G4; both are superseded here while 0008 remains Accepted and unedited. The row cap in R1 is a count, not a token budget, and truncates no text.

### F. Factions and reputation

- **F1 — Rekey and retire (Decided).** `world_state.factions` is rekeyed by `slug`, with `name` moved inside the dict. `reputation_tiers[].label` becomes the band label of faction→player edges; `perks`/`penalties` are not migrated. `char_data.reputation` and the `reputation_change` handler are retired. This is part of the world-state rung, with round-trip tests for save/restore and export. Keeping both systems would preserve the very duplication 0002 set out to remove.

### C. Configuration

- **C1 — `graph.*` runtime-global (Decided).** All knobs live in `saga.config.yaml` with immediate effect, as in 0022: `max_relations`, `scene_max_relations`, `extract_max_per_batch`, default relation kinds. No per-campaign snapshot: relational policy is read-side policy and must be tunable during a playtest. Every cap has a hard bound (config-first is standard 14; the loop-cap standard is 19). `scene_hops` from 0002 is **removed**: R1's filter is "both endpoints present + toward the player", a different rule with no hop traversal, and an unused knob would be misleading.

### X. Tool boundary

- **X1 — `update_relation` stays separate from `update_npc` (Decided).** `update_npc` patches descriptive fields of one NPC record and explicitly never writes psychology (`tools_npc.py:23-50`); psychology deltas belong to `change_npc_psychology`, and NPC actor results carry their own `axis_changes`. `update_relation` writes an edge between two typed refs with stance and lifecycle. The two channels are deliberately distinct (0005): Lyra can respect the player (axis) while being their enemy (edge). Merging them at the tool surface would produce a union-schema god-tool and erase that distinction. The F2 resolver and the validated-write/upsert helper **are** shared internally.
- **X2 — Tool-surface cleanup is separate work (Decided).** Consolidating `kill_npc`/`remove_npc`/`restore_npc`, evaluating whether the never-called `change_npc_psychology` should be retired, and documenting that tool schemas travel as the provider's native `tools` parameter (`openai.py:169`) are recorded in `TODO.md`, not in this ADR.

## 4. Decided vs Open — quick index

| Area | Status | Reference |
|---|---|---|
| P1-P2: open endpoint types, edge-vs-field rule | Decided | §3 P |
| E1-E4: edge shape, two clocks, scale, tombstones | Decided | §3 E |
| S1-S2: storage + allow-list rung, lifecycle across save/fork/load | Decided | §3 S |
| T1-T3: world-defined kinds, validator reaches writers, stance as semantics | Decided | §3 T |
| W1-W4: three writers, tool-wins precedence, per-type resolution, Director deferred | Decided | §3 W |
| R1-R2: compact XML rows, both local scene caps removed | Decided | §3 R |
| F1: faction rekey, reputation retired | Decided | §3 F |
| C1, X1-X2: runtime config, tool boundary | Decided | §3 C/X |
| `max_relations`, `extract_max_per_batch`, scene row cap, band thresholds | **Refined**, measured in S5 | §3 C |
| #123 closed + endpoint-resolution test | **Gate for S3 only** | W2, §8 |
| World-authored calendar (seasons, month/year length, names) in world taxonomy | **TODO**, trigger: a world defines its own seasons; until then the 120-day engine clock governs | E2 |
| `knows_about`, continuity checklist, multi-hop traversal | **TODO** | §2 |
| Director / 0014 consumer wiring | **TODO**, gated on those ADRs | W4 |
| Fact supersession / contradiction | **TODO**, separate work | §2 |
| DM tool-surface consolidation | **TODO** | X2 |
| Backfill of authored relations into existing campaigns | Out of scope | §2 |

## 5. Rejected alternatives

- **`campaign_relations` table.** Rejected: restore desync and manual export extension; indexes buy nothing at this cardinality.
- **Relations as fields on NPC/faction records.** Rejected: symmetric edges written twice and able to diverge, no home for the player, no cross-type edges.
- **Fixed kind enum + `custom(label)` (0002 G1).** Rejected: the owner wants maximum world customisability; stance already carries machine semantics.
- **Entirely author-owned taxonomy with no default, or free-form strings with no taxonomy.** Rejected: small worlds would repeat the base list, and without a validation boundary the F2 reject-with-candidates posture is lost.
- **Extraction gated on a separate periodic job.** Rejected: it reintroduces an LLM call with its own deadline, lease and retry — the cost 0020 just brought under control.
- **Extraction-only or seed-only.** Rejected: the first leaves the DM unable to correct the graph; the second leaves it static.
- **Auto-closing contradictory kinds, or deleting edges on NPC removal.** Rejected: both destroy stratified history, which is most of the value of a graph over a field.
- **One lifecycle tool `manage_npc`, or one merged `update_world` tool.** Rejected here: they change obligated tool names used by 0009/0017 tests and have no connection to edges; deferred to tool-surface work.
- **Keeping either local scene cap.** Rejected: silent loss of authored or derived content with no recovery path; the provider's structured over-window error is preferable.

## 6. Consequences

**Positive**: four dead relational fragments become one curated system; authored faction content stops being discarded; the DM sees who relates to whom with both turn and game-time reference; save/restore/export carry the graph for free; extraction adds no new generation call; the taxonomy is world-owned without losing a validation boundary.

**Trade-off**: a world-state rung plus an extension to the 0020 batch output contract; two turn-path writers with a precedence rule; no token ceiling on the scene, so verbose worlds can produce a provider error; the graph is inert for consumers until 0006/0014 land.

**Risks**: extraction quality is gated on #123 and on endpoint resolution, and ambiguous endpoints will still be dropped by design (with a log); game-time durations are currently distorted by the stalled clock (F10); cumulative edges can grow without a consumer to prune them, hence `max_relations`.

## 7. Relationship to other ADRs

- **0002 (Proposed, superseded)**: 0022 owns R1-R4, this ADR owns G1-G6. G3 is updated here (extraction extends the 0020 batch producer, not a per-turn call); **G4's "under the 0008 token cap" clause is superseded by R2**; **G3(d)'s enum-only extraction rule is replaced by T1**.
- **0005 (Accepted)**: dispositions stay axes; the graph holds relations. Dispatching both from one tool is explicitly rejected in X1.
- **0006 (Proposed)**: the Director reads the faction web and writes stances through its own queue; the change type is defined here, the wiring is not.
- **0008 (Accepted)**: the spatial graph is separate. This ADR retires `world.scene.scene_context_max_tokens` and `description_max_chars`, reversing J1's cost premise, without editing 0008.
- **0009 (Accepted)**: UUID identity and F2 resolution are the substrate for NPC endpoints; `npc.location`/`npc.faction` remain fields and removed NPCs keep their edges (S2).
- **0014 (Proposed)**: its soft gate is recorded in `docs/adr/README.md` as pointing to this ADR; 0014's body does not mention 0002 and, being append-only, is not edited.
- **0018 (Accepted)**: embedding spaces and the versioned index are untouched.
- **0020 (Accepted)**: W1 extends the batch output contract (schema/version/prompt/examples/tests); no producer implementation is rewritten and the fact contract is unchanged. The #123 gate protects the attribution premise. R2 follows 0020 §4's rule that an over-window input must be a recognisable error, not a silent cut.
- **0021 (Accepted)**: structured generation and bounded recovery are unchanged; a larger batch schema may consume more recovery sends, which the gate test accounts for.
- **0022 (Accepted)**: separate subsystem. 0022 ranks facts; this ADR manages current relational state. They share the F2 posture and the config-first discipline, not a data model.

## 8. Implementation plan

- **S1 — Schema, rung and seed.** Add `relations` to `ALLOWED_WORLD_STATE_KEYS` and seed it; rekey factions by slug; add `relations:` to authored NPCs with tier-3 validation; band labels from `reputation_tiers[].label`; retire `reputation_change`. Real-DB round-trip tests for save/restore/export, a merge carrying `relations`, and an unknown key still being stripped.
- **S2 — Resolver, tool and lifecycle.** `resolve_faction_slug`, player sentinel, per-type resolution and reject-with-candidates; `update_relation` with open-only upsert and fresh-edge reopen; shared validator with taxonomy injected into the tool description. Real-DB tests for ambiguous endpoints, unknown kinds with candidates, no duplicate open edges, mid-tombstone save, fork copy and late publish after load.
- **S3 — Extraction (gated).** Close #123 and prove attribution plus unique endpoints; then add `relations[]` to the batch output contract with schema/version/prompt/examples/fixtures updated, wire format `{type, name}`, and a per-batch cap. Real-DB two-speaker test through the real batch producer; tool-wins precedence test; a test that a batch rebuilt after a clock advance still carries the frozen `game_minutes` from its turns.
- **S4 — Rendering and cap removal.** Compact XML rows with the dedicated row cap; remove the `700` and `600` caps together — config keys `saga.config.yaml:281-282`, hardcoded defaults `ai/prompts/scene.py:19-20`, the slice at `:68-71` and the tail cut at `:103-117`, and rewrite `tests/unit/ai/test_scene_block.py:62-68` (`test_block_respects_token_cap`), which currently asserts the 700 cap. Assert block structure, the bilingual rendering of `t/d/h` and the duration, and a simulated over-window request classified as a provider context-length error.
- **S5 — Playtest and tuning.** Confirm the graph is actually visible and used by the DM; fix `Refined` caps; bilingual prompt check where relevant; full check of both stacks.

No consumer wiring for 0006/0014 is implied by these steps.

## 9. Notes and sources

- ADR 0002 `§2 G1-G6` — the original graph design, retained here with the changes forced by 0020/0021 provenance and by the owner interview and review.
- `scratch/findings-playtest-adr-020.md` — F6 (speaker bundling), F10 (an ignored tool, stalled clock).
- Code map verified during the interview and review: `world_instantiation.py:127-130`, `memory/updater.py:111-119`, `producer_contracts.py:114-147`, `models/npc.py:25` and `IMMUTABLE_FIELDS`, `tools_npc.py`, `tools_world.py`, `tools_special.py`, `memory/world_state.py`, `ai/prompts/scene.py`, `saga.config.yaml`, `openai.py:169`.
- `scratch/research/retrieval-prior-art-2026.md` found that graph databases lose to flat memory on single-hop and cost more; that finding concerns storage technology, not the curated relational state defined here.
