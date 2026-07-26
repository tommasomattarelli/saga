# ADR 0002 — Relationship graph alongside pgvector recall

- **Status**: Proposed (direction 2026-06-09; expanded in place by the 2026-07-13 design
  pass — every fork closed by owner interview, re-anchored on the 0008/0009 world (UUID
  records, world files, psychology 0005, Director 0006, promotion 0014). Provisional values
  tagged Refined. Flips to Accepted after implementation + playtest. **No hard external
  gate** — first implementable ADR in the design queue.)
- **Date**: 2026-06-09; design pass 2026-07-13.
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork A; owner
  interview 2026-07-13. Resolves the faction→player `disposition` seam deferred by
  ADR 0005 C4 / carried by 0006.

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values at
implementation. **TODO** = consciously open.

## 1. Context

SAGA's long-term memory is a three-tier stack (verbatim window → rolling/global summaries →
pgvector over `MemoryFact`). Grounded 2026-07-13:

- `search_similar_facts` is **pure top-K cosine** with a **hardcoded `limit=3`** (std 14
  violation) and the query is the **naked player action** (`context.py:128`) — recall is
  blind to where you are, who's present, and what the last five turns were about.
- No recency weighting, no boost-on-access: a stale fact ranks like a fresh one; the
  campaign's pillar facts never rise.
- **Relational state is fragmented and dead.** Authored faction↔faction `relations`
  (`FactionDef.relations {stance -10..10, label}`, tier-3 validated) are **dropped at
  instantiation** — the overlay keeps `{description, disposition: 0}` and nothing ever
  writes or reads it. `char_data.reputation` is written by `reputation_change` and **read
  by nothing**. Authored `reputation_tiers` never reach runtime. NPC↔NPC relations exist
  nowhere at all.
- New consumers exist that didn't in June: the **0006 Director** (faction webs, off-screen
  stance shifts, the faction→player rework promised to this ADR) and the **0014 acting
  call** (a boss must know who hates whom).

Two complementary layers, as originally framed: **semantic recall** answers "what past
events fit this moment's theme"; the **relationship graph** answers "who relates to whom,
here, now". This pass designs both against the current engine.

## 2. Decisions

### R. Recall enrichment

- **R1 — Composite score in SQL + a dormant reranker seam (Decided).**
  `score = (1 − cos_dist) × exp(−age_turns / half_life) × (1 + k·ln(1 + access_count))` —
  the DB orders, no double fetch. Migration adds `last_accessed_turn` + `access_count` to
  `memory_facts`; **retrieval = access** (the returned rows update both, same session as
  the context build). Age is measured in **turns**, not game-time — memory follows played
  time. `half_life`, `k`, `limit` in `saga.config.yaml`. The pipeline exposes an optional
  **rerank hook** (`reranker: {enabled: false, provider, model}` — Cohere-style
  cross-encoder): **off by default, TODO** — on a small corpus of atomic facts it adds a
  network call per turn on the critical path for marginal gain, and it knows nothing of
  recency/usage (it would sit *on top of* R1, not replace it). Turn on only if playtests
  show poor recall despite R1+R2. Rejected: *Python rerank of top-20 cosine* (double
  staging; the fresh-but-21st candidate never surfaces); *decay-only* (pillar facts don't
  rise — half of aidm's point lost).
- **R2 — Composed query (Decided).** The embedded query becomes
  `action + present scene entities (NPC names, current place) + last K turn summaries`
  (summaries already computed per turn — free). "I open the door" in the crypt with Lyra
  finally recalls crypt/Lyra facts. Still **one embedding per turn**. Config: `K`, scene
  toggle, and a **hard query-length cap** — the 384-dim embedding model has a small input
  window; silent truncation is a guarded failure, not an accident. Rejected: *action +
  summaries without scene* (the most discriminating signal — who/where now — left out);
  *status quo* (the TODO line's original complaint).
- **R3 — Knobs (Decided).** The hardcoded `limit=3` moves to config with the rest
  (`recall: {limit, half_life, boost_k, query_turns, query_scene, query_max_chars}`).
- **R4 — Legacy fields untouched (Decided).** `MemoryFact.entity_name/entity_type` stay
  free strings (pre-0009); recall doesn't use them and the graph doesn't either (it
  resolves via F2). The unused `search_vector` TSVECTOR column stays for the separate
  fulltext-tool TODO. Pre-existing note: `memory_facts` was never snapshot-consistent with
  save/restore — unchanged here.

### G. The relationship graph

- **G1 — Perimeter: entity↔entity edges + faction→player, one system (Decided).** Typed
  edges NPC↔NPC, NPC↔faction (beyond membership — `npc.faction`/`npc.location` stay record
  fields, never duplicated), faction↔faction (runtime life for the authored relations —
  drop fixed), and **faction→player as the same edge type**, unifying the three dead
  fragments: overlay `disposition` (removed), `char_data.reputation` +
  `reputation_change` handler/tool (**retired**), authored `reputation_tiers` (become the
  **band labels** of the faction→player edge stance — the 0005 bands pattern).
  `knows_about` **excluded v1**: half relation half fact — MemoryFact already covers the
  episode, and as edges it explodes (one per secret per NPC); the continuity-checklist
  TODO is its natural home. Edge shape:

  ```
  {src: {type: npc|faction|player, id}, dst: {…},
   kind: ally|enemy|rival|family|debt|loves|fears|hunts|custom(label),
   stance: -100..100, label, since_turn, until_turn?}
  ```

  Contradictory kinds on one pair (open `ally` + `enemy`) are **allowed v1** — no
  auto-closing of opposites (DM/Director curate; TODO if playtest shows dirt).
- **G2 — Storage: `world_state.relations` (Decided).** Dozens-to-hundreds of edges ride
  the overlay: **save/restore/export consistency for free** (campaign snapshots capture
  world_state — a table would silently desync on restore), single-writer turn path
  (Director goes through its 0006 queue), BFS on ≤500 edges is a trivial in-memory filter
  (0008 NetworkX pattern), TOAST unchanged (world_state rewrites every turn anyway).
  Trivial rung; `max_relations` cap (std 19). Rejected: *`campaign_relations` table*
  (restore desync, export extension, indexes buying nothing at this cardinality).
- **G3 — Four writers (Decided).** (a) **Instantiation seed**: authored faction relations
  finally instantiated (×10 to the unified scale), plus a new authored `relations:` field
  on world-file NPCs ("Lyra hates the captain" is authorable, tier-3 validated). (b) **DM
  tool `update_relation`** — F2 reject-with-candidates, upsert semantics (same
  src/dst/kind updates stance/label in place, never duplicates), replaces
  `reputation_change`. (c) **Director change type** (0006) — stances move off-screen
  through the queue. (d) **Guarded fact-extractor extension**: the per-turn background LLM
  call gains an optional `relations[]` output (src/kind/dst triples) — **zero extra calls,
  zero latency**; guards: both endpoints must F2-resolve uniquely (no unique match =
  silent drop + log, F7 posture), enum kinds only (no `custom` from extraction), per-turn
  cap. Rejected: *verb-table extraction* (the original idea — regex over free bilingual
  prose has hopeless recall; built for structured logs); *no auto-population* (relations
  emerge in narration constantly; the graph would grow only when the DM remembers).
- **G4 — Consumers & the scene query (Decided; render shapes Refined).** (a) DM `<scene>`:
  relations among present entities + toward the player, one compact line next to the 0005
  salient axes, under the 0008 token cap. (b) Director B2 context: the faction web + edges
  of recently-touched NPCs. (c) 0014 acting call: the sheet-holder's own edges. Query =
  filter "both endpoints present" ∪ one hop out (the original 2-hop BFS, right-sized to an
  in-memory filter). Secret-ish edges are DM-visible by design (dm_notes posture — the DM
  seeds, discretion at the prompt level).
- **G5 — Staleness: tombstones (Decided).** Closing a relation sets `until_turn` — the
  edge stays as history ("allies until turn 89"); reopening = a new edge. No deletes.
- **G6 — Identity fixes surfaced by the backcheck (Decided).** The player is the sentinel
  ref `{type: player}`. **Overlay `factions` is rekeyed by `slug`** at instantiation
  (today keyed by display name — un-renameable, typo-fragile; `name` moves inside the
  dict). Cross-ADR note: 0006's `factions.{}.agenda/moves` prose refers to the same dict —
  no contract change, keys become slugs. Stance scale unified **-100..100 everywhere**
  (authored -10..10 seeds ×10, documented; `reputation_tiers` thresholds already in that
  scale).

### S. Schema, config, testing

- **Schema**: `memory_facts` migration (+`last_accessed_turn`, +`access_count`); world_state
  rung (number at implementation): +`relations: []`, factions rekeyed by slug with
  `name`/band-tiers inside, `char_data.reputation` dropped.
- **Config** (std 14): `recall: {limit, half_life, boost_k, query_turns, query_scene,
  query_max_chars}`, `reranker: {enabled: false, …}`, `graph: {max_relations,
  extract_max_per_turn, scene_hops: 1}`.
- **Testing** (std 1/11): score ordering under age/access permutations (real DB); access
  bump persists; composed query respects the cap; seed ×10 + rekey migration round-trip;
  upsert semantics (no dupes); tombstone close/reopen; F2 drop on ambiguous extraction;
  reputation handler removal; scene filter + hop; export/restore carries relations.

## 3. Decided vs Open — quick index

**Decided**: R1-R4, G1-G6, S.
**Refined**: all config numbers, render shapes (scene line, Director/0014 blocks), exact
kind-enum final list.
**TODO**: reranker stage (config stub ships dark); `knows_about` / continuity-checklist;
auto-closing contradictory kinds; fulltext search tool over `search_vector` (separate TODO
line, column already exists).

## 4. Rejected alternatives (with reasons)

Python rerank / decay-only (R1); scene-less or naked query (R2); `knows_about` v1 /
factions-only perimeter (G1); dedicated edge table (G2 — restore desync); verb-table /
no-auto-population (G3); a fourth parallel faction→player system — the point of G1 was
retiring three; live reranker v1 (network call on the critical path for marginal gain on a
small atomic corpus).

## 5. Consequences

- **Positive**: recall finally sees the scene and the recent thread, ranks by
  freshness+usage, and every knob is tunable; the graph gives one uniform relational
  system where four fragments (three of them dead) existed; authored faction content stops
  being dropped; Director and acting call get the relational context they were designed
  expecting; everything rides save/export by construction.
- **Trade-off**: fact-extractor contract grows (guarded, zero extra calls) — extraction
  quality gates graph growth; misses degrade gracefully to semantic recall (the original
  ADR's stance, unchanged).
- **Trade-off**: retrieval now writes (access bump) — 3 row updates per turn, same session.
- **Trade-off**: faction rekey is a breaking rung for anything name-keyed downstream
  (checked: overlay-internal only; 0006 unimplemented).

## 6. Relationship to other ADRs

- **0005** — dispositions (NPC→player feelings) stay axes; the graph holds *relations*;
  `reputation_tiers` reborn as faction→player bands.
- **0006** — the Director reads the faction web in B2 and writes stances via its queue;
  the faction→player rework promised there lands here.
- **0008/0009** — UUID/slug identities, F2 resolution, NetworkX pattern, tier-3 validation
  of new authored fields.
- **0014** — acting-call context consumes the sheet-holder's edges.
- **0007** — memory-depth knobs land in the same config family (§2 max-configurability).

## 7. Implementation plan (fixed — no external gate; first in the implementation queue)

- **S1 — Recall enrichment (standalone, immediate payoff).** Migration; SQL score;
  composed query + cap; access bump; config block + hardcoded-limit removal; reranker stub
  dark. Integration tests on real DB.
- **S2 — Graph core.** Rung (relations + faction rekey + reputation drop); instantiation
  seeds (faction ×10, authored NPC relations + editor field); `update_relation` tool +
  `reputation_change` retirement; scene render; caps.
- **S3 — Auto-extraction + consumer wiring.** Fact-extractor `relations[]` + guards;
  Director change type and 0014 context blocks wired as those ADRs land.

## 8. Notes / sources

Original survey: aidm heat decay + boost-on-access; open-tabletop-gm scene-context graph.
Design pass grounded in code (semantic.py, context.py:128, memory_fact.py,
world_instantiation.py:116 name-keyed factions, updater.py reputation writer with zero
readers, world.py FactionDef.relations dropped at runtime) — no external validation needed;
the reranker question was examined and parked behind a config stub on first principles
(corpus size, critical-path latency, provider matrix).
