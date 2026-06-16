# ADR 0002 — Relationship graph alongside pgvector recall

- **Status**: Proposed
- **Date**: 2026-06-09
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork A

## Context

SAGA's long-term memory is a three-tier stack (active window of verbatim turns
→ rolling/global summaries → pgvector semantic search over the `MemoryFact`
corpus). `app/memory/semantic.py::search_similar_facts` is a **pure top-K cosine**
query: no recency weighting, no boost-on-access, and — crucially — no model of
*who relates to whom*. Two gaps surface on long campaigns:

1. **Flat relevance.** A stale fact ranks identically to a fresh one of equal
   cosine similarity. Frequently-recalled, still-relevant memories don't rise.
2. **No relational recall.** "Who, present in this room, is loyal to whom / hates
   whom / knows about X" is a *graph* question. Semantic search answers it poorly
   and expensively (it retrieves by theme, not by scene topology).

The survey found two complementary patterns: aidm's per-category **heat decay +
boost-on-access** on semantic memory, and open-tabletop-gm's **relationship graph**
with a `scene-context` query that returns a 2-hop BFS subgraph around the current
location/present NPCs — high precision, few tokens, and populated semi-automatically
from the session log via deterministic verb-table extraction (no LLM).

## Decision

Keep pgvector as the thematic recall layer and **add two things**:

1. **Recall enrichment on `search_similar_facts`** — combine cosine distance with
   a recency/decay weight and a boost-on-access bump, so relevance reflects both
   semantic match *and* freshness/usage. Decay curves and the boost delta live in
   `saga.config.yaml` (std 14). This is a scoring change, not a new subsystem.
2. **A relationship graph subsystem** — a typed graph of NPC/faction/location
   edges (`loyal_to`, `opposes`, `member_of`, `lives_in`, `knows_about`, …) stored
   in Postgres (table or JSONB), exposing a `scene_context(place_id, present_npc_ids)`
   query that returns the 2-hop subgraph relevant to the current scene. The graph
   is populated semi-automatically from the turn/session log (deterministic
   verb-table extraction first; LLM extraction is a later option). It is
   **complementary** to pgvector: the vector store answers "what past events are
   thematically relevant", the graph answers "who relates to whom, here, now".

The graph is consulted by the DM context builder when assembling scene context,
replacing the need to reload the full NPC/faction state on every turn.

## Consequences

- **Positive**: relational queries become cheap and precise; recall ranking
  reflects recency/usage; full NPC/faction blobs no longer need to ride in every
  prompt. Deterministic extraction keeps graph upkeep LLM-free and auditable.
- **Trade-off**: a second memory store to keep consistent with world state. Edges
  carry `since/until` session markers so stale relations age out rather than being
  deleted.
- **Trade-off**: deterministic verb-table extraction has limited recall (~higher
  precision than recall). Accepted — the graph is an index/cache, not the source
  of truth; misses degrade gracefully to pgvector recall.

## Notes

Recall enrichment ships first (small, isolated, immediate payoff on long
campaigns). The graph subsystem is the larger piece and can land incrementally:
schema + manual edges → `scene_context` query wired into context building →
deterministic auto-extraction. Interacts with the per-campaign NPC psychology
redesign (ADR 0005): the graph holds *relations*, the NPC JSONB holds *dispositions*.
