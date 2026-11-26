# ADR 0022 — Memory retrieval: deterministic multi-query, hybrid, no write path

- **Status**: Proposed (design closed by the owner interview on 2026-11-24; not yet implemented). Numeric weights and thresholds remain **Refined** and must be fixed by the benchmark in §8, not by intuition.
- **Date**: 2026-11-24.
- **Context items / sources**: ADR 0001, 0002 (Proposed — its recall half is superseded here), 0005, 0007, 0008, 0018, 0020, 0021; ADR 0020 playtest (`scratch/findings-playtest-adr-020.md`, F6/F7/F8/F10); external surveys `scratch/research/retrieval-prior-art-2026.md` and `scratch/research/query-construction-if-2026.md`.

Legend: **Decided** = settled by the owner. **Refined** = shape fixed, value to be measured during implementation. **TODO** = consciously deferred, with an explicit trigger.

## 1. Context

Memory production is shipped: ADR 0020 (batches, intermediate summaries, global checkpoints, facts with provenance) and ADR 0021 (unified structured generation and bounded recovery). Retrieval is still in its pre-0020 state.

Verified in the code on 2026-11-24:

- `core/dm/dm_nodes.py:78-80` embeds **the sanitized player action only** — no scene, no location, no present NPCs, no recent turns.
- `memory/semantic.py:16-67` is **pure cosine top-K**: no threshold, no decay, no access boost, no reranker, no lexical fusion, no filtering by category/entity/importance. The only *relevance* filter is active-history isolation (`:47-63`), which is correct and must be preserved. The query also applies campaign, index, workspace-state and dimension filters (`:36-46`).
- `ai/context.py:45` hardcodes `limit=3`; `:49` passes only `fact.content` to the prompt; `:50-52` turns any exception into an empty list. There is already a `logger.exception` there (`:51`), but it is a generic failure log, not a retrieval-specific diagnostic.
- `ai/prompts/dm.py:25-30` types `recalled_memories: tuple[str, ...]`; `:212-218` renders it as `- text`: no category, attribution, age or importance.
- `models/memory_fact.py:22-82`: produced facts carry `category`, `assertion_type`, `fact_metadata` (entities with `canonical_ref`, attribution, temporal references, importance), `batch_id`, `generation_id`. **None of it is spent by retrieval.**
- `search_vector` exists with a GIN index (`:80`) but **nobody writes it**; the legacy `embedding: Vector(384)` column is unused and recall reads `source_embeddings` (`semantic.py:36-67`).
- `memory/batch_source_contracts.py:45-49`: the producer receives turns (action + narration) and operations with deltas, **not the scene**. Write-time contextualisation would require a change to the 0020 contract.
- `saga.config.yaml:88-116`: no `recall:` block exists.
- `ai/sanitizer.py:63-67` silently truncates the player action to **2000 hardcoded characters**, and this happens before the recall embedding (`dm_nodes.py:62,78-80`). The query is therefore built from an already-cut text.
- No retrieval-quality metrics exist: no hit rate, recall@k, MRR, relevance labels or latency measurement. The canary probe is a documented procedure, not code; #115 was closed with the caveat that the canary was duplicated in facts and 15 embeddings.

The defect is therefore not "the ranking is wrong" but: **retrieval uses the weakest available signal while everything else — paid for and persisted — goes unused.**

## 2. Scope

### In scope

1. Query construction and candidate generation.
2. Fusion, ranking, selection, dedup and rendering of recalled facts.
3. Failure behaviour and observability of the retrieval path.
4. Configuration, the full-text migration, and an offline evaluation of retrieval.

### Out of scope

- The relationship graph: ADR 0023 (see §7).
- Any change to the embedded text of facts or to the embedding index.
- Reconciliation, supersession or updatable truth state for facts.
- Semantic dedup between facts and summaries/checkpoints.
- A `recall` tool called by the DM, and LLM escalation: both TODO with triggers in §4.
- Backfill or conversion of memory predating the 0020 cutover.

## 3. Decisions

### R. Query construction

- **R1 — No write-time context (Decided).** The embedded text stays `content`, as in 0020 §7.1. The reasons are contractual and operational: the producer cannot see the scene and the scene may change several times within B=4 turns; metadata must not be added to embedded text; changing it would require a new embedding index version (0018) plus reindexing. External research rates write-time enrichment as high-value, so this is a deliberate trade against index churn, not a claim that it cannot help; §4 carries the trigger to reopen it.
- **R2 — Deterministic queries plus one lexical query, fused by rank (Decided).** One **embedding batch call** embeds (a) the sanitized action and (b) a short natural-language scene anchor, via `embed_texts(space, [action, anchor], user_id=...)`; the anchor is built from `snapshot.history`, so the call stays outside any DB session (standard 15). `PreparedRecallQuery` becomes a **named vector map** (`action`, `anchor`, and `composed` for eval variant (b)); each variant states which vector feeds `search_similar_facts`. The lexical query uses the **same `simple` regconfig as the index**: `to_tsquery('simple', <expression>)` where the expression is the OR of the distinct lexemes of the action (from `to_tsvector('simple', action)`, length ≥ 2), with `:*` appended to any lexeme that matches a known gazetteer name. `plainto_tsquery` ANDs all lexemes and would usually match nothing; `websearch_to_tsquery` has no prefix syntax, so it is not used. The three candidate lists are fused with RRF in SQL. One database round-trip, no dilution of signals into a single vector.
- **R3 — Scene anchor (Decided).** Current location + canonical names of present NPCs + **last mentioned entity** in the previous two turns if not already present. Example: `At Thornhaven, with Lyra and Aldric.` The last entity is derived deterministically by scanning recent narration against the R4 gazetteer. The anchor reads **untruncated `world_state`**, not the rendered prompt: the prompt-side `<scene>` caps are 0023's scope and must not bias retrieval. A length cap on the anchor itself is **Refined** (the anchor is embedded, so changing its length requires a new authorised embedding batch); the action always stays the first component because it carries intent.
- **R4 — Gazetteer derived from state, not a new table (Decided).** Two uses, two filters:
  - **Expansion** (which names to add to the anchor): NPCs with `met_player OR last_interactions` in `world_state.npcs`, plus present NPCs. `met_player` is engine-owned and not writable by the LLM tool (`models/npc.py:25`, `IMMUTABLE_FIELDS`); in current runtime paths it is raised only by a psychology delta (`memory/updater.py:68`), so an NPC who merely spoke would be missed, hence `last_interactions` (`npc_results.py:47-48`). That signal is itself a bounded window — `gameplay.npc_last_interactions_kept: 3` — so an NPC who has not spoken in the last three recorded interactions drops out of the expansion filter; this is an accepted limitation with a TODO trigger in §4. Authored seeds never raise `met_player` (`world_instantiation.py:100`); the v5→v6 migration also sets it, but only for pre-1.0 saves.
  - **Matching** (recognising a name in the action or narration for "last mentioned entity"): **all** known names — `world_state`, `world_baseline` and entity names from fact metadata. If the player writes "Morrowglass" the name is already in the query and must be recognised even if that NPC was never met.
- **R5 — Distant anaphora: declared limitation (Decided).** "I think back to what she said" with an antecedent older than the raw window is only covered when the name is recoverable from state or the previous two turns. It is not solved in v1. LLM escalation is in §4 with trigger and gate.
- **R6 — No silent input cut (Decided).** The 2000-character hardcoded cut becomes `gameplay.max_action_chars` in configuration. An action over the limit is **rejected with a structured error at the API boundary, before the turn claim**: no turn number consumed, no embedding call, no partial text. Post-claim interruptions (playtest F1, issue #120) are a separate, already-tracked defect and are not addressed here. The rejection is a visible limit, not a truncation.

### C. Candidates and fusion

- **C1 — Dense + lexical hybrid in Postgres (Decided).** The dense branch queries `source_embeddings` with the query embedding (not the legacy column). The lexical branch queries `search_vector`. **Both branches and the fused result apply the identical ancestry predicate from `semantic.py:47-63`**; lexical rows are also restricted to `campaign_id` and to batches whose full membership lies in the active ancestry. A hit from an abandoned continuation must never reach the prompt — `turn_number` is not unique per campaign, so it cannot be used as the guard. No new service, no ANN index: at a few hundred facts an exact scan is irrelevant.
- **C2 — `search_vector` becomes a generated column (Decided).** `GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED`, using the existing GIN index. Postgres 16 supports generated columns and `to_tsvector(regconfig, text)` is IMMUTABLE. The dead column comes alive without a trigger or application writer and cannot drift from `content`.
- **C3 — `simple` configuration (Decided).** No stemming, no stopwords: invented names stay intact, Italian and English campaigns share one index, and common-word noise is absorbed by ranking. Campaign language does not enter the index.
- **C4 — No hard filters (Decided).** Category, importance and entity **do not exclude** candidates. A wrong filter makes a fact invisible — the opposite failure from the one we are trying to avoid. They enter as boosts (K1).

### K. Ranking and selection

- **K1 — RRF plus light boosts (Decided).** The RRF score receives three boosts:
  1. **Entity match, split by what can actually be resolved.** (a) `canonical_ref` equality for tool-resolved NPCs and quests — `producer_contracts.py:114-147` produces `canonical_ref` only for those; (b) **name match against the R4 gazetteer** for locations and the last-mentioned entity. Without (b) the boost would be a no-op for exactly the cases R3 was built to improve: `location` entities never carry a canonical ref, and NPCs who only spoke carry none either.
  2. A boost for `importance.level = critical`.
  3. Recency as a **low-weight tie-break**, measured in completed turns of the active continuation, **never a multiplier**. A multiplicative decay (0002 R1) would bury old promises under recent trust micro-deltas.
  The weights are **Refined** and E2 isolates them with cumulative variants.
- **K2 — Pool 25, inject 5, text dedup (Decided).** Each retriever returns up to 25 candidates; after fusion and boosts the top 5 are injected in descending score order (most relevant first). When `recall.critical_always_include` is on, `critical` facts **fill those same 5 slots first** (they are not additional slots), capped by `recall.max_critical_inject` (hard bound, standard 19) so an unbounded rubric cannot blow the budget; the remaining slots go by score. Identical or near-identical content is dropped after normalisation (case, whitespace, punctuation); the **highest-scoring representative of a duplicate group survives**. The near-duplicate threshold is **Refined** and E2 includes a dedup-off variant. A wide pool costs rows, not prompt tokens.
- **K3 — No access count (Decided for v1).** `last_accessed_turn` and `access_count`, with updates to returned rows in the same session, stay out: the literature shows the signal is used (Generative Agents, AI Dungeon) but provides no isolated ablation, and it costs a migration plus three updates per turn. Trigger to reopen in §4.
- **K4 — No dedup against `<history>` or `<global_summary>` (Decided for v1).** The same event may appear twice: redundant, not destructive. The playtest F7 case concerns probe isolation, not narration quality.

### P. Prompt rendering

- **P1 — Typed, compact rendering with speaker (Decided).** `DMPromptContext.recalled_memories` becomes a tuple of `RecalledFact` values instead of bare strings, with `content`, `category`, `age_turns`, `speaker`, `importance` and `assertion_type`. Rendering:
  `- (38 turns ago · commitment · Lyra said) <content>`
  - `age_turns` is derived by joining `memory_fact_sources` → `memory_batch_turns` and counting completed turns in the **active continuation**; production facts have `turn_number IS NULL` by check constraint (`memory_fact.py:68-70`) and that number is not campaign-unique, so it cannot be used.
  - `speaker` is resolved from `fact_metadata.attribution` (indices into `entities`), not invented: `statement → said`, `belief → believed`, `intention → intended`; occurrences have no speaker.
  - `critical` adds a marker; `ordinary` is omitted.
  - Rendering is localised with an explicit table (no `str | RecalledFact` union anywhere):
    | token | en | it |
    |---|---|---|
    | age | `turns ago` / `1 turn ago` | `turni fa` / `1 turno fa` |
    | statement | `said` | `disse` |
    | belief | `believed` | `credeva` |
    | intention | `intended` | `intendeva` |
    | critical | `critical` | `critico` |
    | category | `event/information/commitment/relationship/state_change` | `evento/informazione/impegno/relazione/cambiamento` |
  - The eval harness is adapted at all four call sites: `Scenario.recalled_memories()` returns `tuple[RecalledFact, ...]` via an explicit adapter with documented defaults (age 0, category `information`, `assertion_type statement`, no speaker), updating `eval/scenario_tools/scenario.py:33,51,56,269`, `eval/support/live_calls.py:93-95` (removing the `type: ignore`), `eval/dialogue/trial.py:99`, `eval/dialogue/pipeline.py:67`, both signatures in `ai/prompts/dm.py:45,76`, and `tests/unit/ai/test_prompt_templates.py:73`.
  Estimated cost 8-12 tokens per fact.
- **P2 — Block at the tail (Decided).** `<recalled_memories>` moves **after `<quests>`**, as the last system-prompt block: closest to the user message and least disruptive to the shared prefix of stable blocks. No current test asserts absolute block order (`test_prompt_templates.py:84` only checks instructions-before-history; `test_dm_prompt_xml.py:210` only checks `<quests>` presence), so S5 adds an explicit order assertion.
- **P3 — No new authority rule (Decided).** `templates/dm.yaml:5` already says *"CURRENT STATE IS AUTHORITATIVE … override conflicting earlier assistant messages, summaries and recalled memories"*, and `:14` says *"Distinguish rumors and claims from established events"*. The problem was that flat rendering made the rule inapplicable: P1 exposes `assertion_type` and attribution. Another warning would duplicate the instruction.

### F. Failures and observability

- **F1 — Fallback chain (Decided).** Embedding unavailable → lexical only; lexical empty or unavailable → dense only; both down → empty list plus a structured error log. **The turn never fails** because of recall: it is enrichment, not a requirement.
- **F2 — Distinct logging (Decided).** The existing `logger.exception` at `context.py:51` is a generic failure log. It becomes a retrieval-specific diagnostic that separates "no results" from "branch failure", with branch used, counts and latency. No new schema: persisting a per-turn diagnostic record belongs to the debug page and is out of scope (§2).

### S. Configuration and schema

- **S1 — All knobs in `saga.config.yaml`, runtime-global (Decided).** A `recall:` block with immediate effect on all campaigns. Retrieval writes no immutable artifacts, so it does not share the per-campaign snapshot protecting the memory policy (0020 §20.8): being able to retune a weight and see the effect on the same campaign is the whole point of the evaluation. Expected fields, with values fixed here where decided:
  ```
  recall:
    enabled: true
    candidate_pool: 25
    inject_limit: 5
    rrf_k: <Refined>
    critical_always_include: false   # toggles E2 variant (f) in production
    max_critical_inject: 5           # hard bound; critical facts fill the inject_limit slots
    query:
      include_scene: true
      recent_narration_turns: 2
      anchor_max_chars: <Refined>
    boosts:
      entity_canonical_ref: <Refined>
      entity_name: <Refined>
      critical: <Refined>
      recency_tiebreak: <Refined>
    dedup:
      enabled: true
      similarity_threshold: <Refined>
  ```
  Retrieval knobs go in `recall:`; gameplay input limits such as R6 go in `gameplay:`. All live in `saga.config.yaml`, never in code (standard 14). The generated-column migration introduces no application writer; there is no dark default left behind.
- **S2 — Migration (Decided in shape).** The only schema change is the generated column in C2; **no new application-populated column** on `memory_facts` and no column on `turns`. `world_state` is untouched by 0022.
- **S3 — Legacy columns out of scope (Decided).** `memory_facts.embedding`, `entity_name`, `entity_type` and `turn_number` stay as they are. The 0020 constraint still distinguishes legacy and production rows; removing them would need a rung and an export/import round-trip check with no reason tied to this work.

### E. Evaluation

- **E1 — Offline benchmark with labels (Decided).** The controlled source used during 0020 S6 (52 turns, 13 batches of 4) was **local-only evidence under `scratch/` and is no longer on disk**; it must be **regenerated**, not merely referenced. Use the deterministic builder `python -m eval.memory_scenarios.build --out <dir> --batch-size 4 --raw-turns 8 --intermediate-limit 2 --global-updates 9` from `backend/` (`eval/memory_scenarios/build.py`, fixed seed and `uuid5` identities). Then author 20-30 **query → expected facts** pairs against the facts that producer run actually emits: the generated annotations hold per-turn world-state expectations, **not** query→fact labels, so labels are new manual work; each query also needs its own state snapshot for the anchor and the boosts. Query embeddings are provider calls (`openai/text-embedding-3-small` via OpenRouter) and therefore require **explicit owner authorisation for each manifest** per `backend/eval/README.md`; a CLI flag is not consent, and the 0020 playtest runs grant no inherited approval. Compute them once per variant — up to ~90 texts for three query forms × 20-30 queries — then variant comparison is pure SQL with no provider calls. The anchor-length sweep changes the embedded text, so each length needs a **separately authorised batch**; it is not part of the free SQL comparison.
- **E2 — Variants to compare (Decided).** (a) naked action with cosine top-3, baseline; (b) single composed query; (c) multi-query + RRF; (d) + canonical-ref entity boost; (e) + name-match, critical and recency boosts; (f) + unconditional injection of `critical` facts, behind `recall.critical_always_include` and `recall.max_critical_inject`, reporting injected tokens so the slot accounting is visible. Plus a dedup on/off variant and the separately authorised anchor-length sweep. Variants (a)-(d) isolate the query, fusion and canonical-ref signal; **(e) is a boost-family comparison** — its three boosts are tuned together, not individually. Unconditional critical inclusion comes from the research and the closest analogue (aidm v5); variant (f) measures it rather than assuming it.
- **E3 — Metrics (Decided).** recall@5, MRR@5, contamination@5 (stale or contradicted facts in the top 5), injected tokens, p50/p95 latency of the retrieval path alone, **lexical-branch hit counts** (so a degenerate lexical query is visible), boost-family ablations from E2 (individual weights are not isolated), and the number of facts dropped by dedup.
- **E4 — No inherited authorisation (Decided).** The initial embedding batches and any live run require explicit owner authorisation for that manifest, per `backend/eval/README.md`. The 0020 playtest runs are historical evidence, not consent for new calls.
- **E5 — The canary probe remains separate work (Decided).** To isolate consumption of the global checkpoint the canary detail must exist **only** in that source: not as a fact, not as an embedding, not in raw turns. That is fixed with #115, not by bending retrieval.

## 4. Decided vs Open — quick index

| Area | Status | Reference |
|---|---|---|
| R1-R6: deterministic multi-query, state-derived gazetteer, no write path, no silent input cut | Decided | §3 R |
| C1-C4: dense+FTS hybrid with shared ancestry guard, generated column, `simple`, no hard filters | Decided | §3 C |
| K1-K4: split entity boost, critical, recency tie-break, pool 25 → 5, text dedup, no access count | Decided | §3 K |
| P1-P3: typed rendering with speaker and language, tail block, no new authority rule | Decided | §3 P |
| F1-F2: fallback chain, retrieval-specific logging | Decided | §3 F |
| S1-S3: runtime config, migration, legacy untouched | Decided | §3 S |
| E1-E5: labelled benchmark, six variants, metrics, owner gate | Decided | §3 E |
| Boost weights, `rrf_k`, anchor cap, dedup threshold | **Refined**, measured by E2/E3 sweeps | §3 E |
| 20-30 labelled query→fact pairs + per-query state snapshots | **TODO — work, not a decision** | E1 |
| Real-DB test plan for generated column, fusion, fallback, branch isolation | **Refined** | S2, C1, F1 |
| LLM escalation for distant anaphora | **TODO**, trigger: low top-1 or unresolved anaphora | §3 R5 |
| DM `recall` tool | **TODO**, trigger: evidence the model would use it (F10 says it would not) | §2 |
| Dedup against summaries/checkpoint | **TODO**, trigger: benchmark shows harmful duplication | K4 |
| `last_accessed_turn` / `access_count` | **TODO**, trigger: benchmark shows pillar facts buried | K3 |
| `last_interactions` gazetteer horizon (3 entries) | **TODO**, trigger: expansion misses an NPC the player clearly knows | R4 |
| Write-time enrichment with a new embedding index version | **TODO**, trigger: E2 shows RRF below the enriched-key upper bound | R1 |
| Dormant reranker seam of 0002 R1 | **TODO**, trigger: recall still low after RRF+boosts and owner accepts an extra call | §7 |
| Relationship graph | Out of scope → ADR 0023 | §7 |

## 5. Rejected alternatives

- **A dedicated LLM query rewrite every turn.** Rejected as a default: no shipped interactive-fiction product does it (AI Dungeon embeds the naked last action; NovelAI, SillyTavern and KoboldAI use key triggers; aidm uses deterministic decomposition and an LLM filter over *candidates*, not the query). The literature does not compare a rewrite against a deterministic composed query, and confidence gating captures about half the gain while paying on fewer than 40% of queries.
- **A single concatenated vector.** Rejected in favour of multi-query: heterogeneous signals are mixed and intent is diluted.
- **`plainto_tsquery('simple', action)`.** Rejected: it ANDs all lexemes and usually matches nothing on a full sentence; OR/prefix construction is required for the hybrid to work at all.
- **0002 R1's multiplicative decay and access count.** Rejected: the first buries important old facts, the second costs a migration and a write per turn with no ablation to support it.
- **Hard filters by category/entity.** Rejected: a wrong filter makes the fact invisible.
- **A `campaign_relations` table for the gazetteer.** Rejected: state already holds authoritative names and flags; a table would be a third copy to synchronise.
- **DM-tool-only retrieval.** Rejected for v1: the playtest shows the DM does not call obligated tools (0 `advance_time` in 21 turns), and no shipped IF product delegates retrieval to model discretion.
- **Maintaining `search_vector` with a trigger.** Rejected: Postgres can derive it; a trigger is one more moving part.
- **Indexing with campaign language.** Rejected: stemming damages invented names and forces an index rebuild when the language changes.

## 6. Consequences

**Positive**: retrieval stops using the weakest available signal; the scene enters ranking without an extra writer; `attribution`, `canonical_ref` and `importance` finally affect what the DM sees; hybrid search recovers proper nouns the vector alone loses; faults are distinguishable from empty results; every knob is configurable.

**Trade-off**: two embeddings per turn instead of one (in one batch call) and two search branches; a migration for the generated column; ~50 extra tokens per turn in rendering; a typed DTO and an eval-harness adaptation; distant anaphora remains uncovered until further judgement.

**Risks**: boost weights are still numbers to tune — with wrong weights the system can be worse than the naked baseline, and E2 exists precisely to catch that; the quality of the `ordinary`/`critical` rubric caps the value of the matching boost; write-time enrichment and the reranker remain open leverage that E2 may show is needed.

## 7. Relationship to other ADRs

- **0002 (Proposed, superseded)**: its recall half (R1-R4) is superseded by this ADR; its graph half (G1-G6) is owned by ADR 0023, which now exists. Its dormant reranker hook (R1) is carried here as a TODO with a trigger, so no decision is left ownerless.
- **0001 (Accepted)**: no DB session spans an embedding or a generation; the fallback introduces no exception to this.
- **0005 (Accepted)**: `met_player` is reused as a knowledge signal without changing its meaning or ownership.
- **0007 (Proposed)**: the `recall.*` knobs that 0007 placed in 0002 S1 land here.
- **0008 (Accepted)**: the scene anchor uses 0008's topology and canonical names; the spatial graph stays distinct from the relational graph of 0023.
- **0018 (Accepted)**: embedding spaces, the versioned index and consent are unchanged; 0022 does not alter the embedded text.
- **0020 (Accepted)**: no change to producer contracts; the history-isolation filter (`semantic.py:47-63`) is preserved and extended to the lexical branch. Reordering the block and rendering metadata are legitimate consequences of the reopening explicitly stated in 0020 §1/§7.1.
- **0021 (Accepted)**: the structured-generation recovery path is untouched.

## 8. Implementation plan

- **S1 — Schema and SQL.** Migration for the generated column, replacing the old dead-column path; dense+lexical query with RRF and the **same ancestry predicate on both branches and on the fused result**. Real-PostgreSQL integration tests with facts in different batches and two continuations reusing the same `turn_number`.
- **S2 — Query and gazetteer.** Two vectors in one `embed_texts` call, `PreparedRecallQuery` extended, anchor built from `snapshot.history` outside the DB session, gazetteer from `met_player OR last_interactions`, matching against all known names, OR/prefix lexical construction. Tests for short anaphora, cited-but-unmet names and lexical hit counts.
- **S3 — Ranking, dedup, rendering, fallback.** Split boosts, 25→5 selection, highest-score dedup survival, typed `RecalledFact`, localized tokens, tail block, fallback chain, retrieval-specific logging, harness adaptation. Tests that the turn never fails, that the log distinguishes the two faults, and that block order is asserted.
- **S4 — Evaluation.** Build the labelled pairs and their state snapshots, authorised embedding batches, offline harness comparing variants (a)-(f) plus sweeps. Refined weights are fixed here.
- **S5 — Cutover.** Enable the `recall:` block, remove the hardcoded `limit=3`, replace the sanitizer cut with `gameplay.max_action_chars` plus a structured pre-claim rejection (R6), bilingual prompt test, prompt-order test, full check of both stacks.

No live call or production-quality conclusion follows from S1-S3. Every run contacting a provider requires owner authorisation for that manifest.

## 9. Notes and sources

- `scratch/research/retrieval-prior-art-2026.md` — initial survey: multi-signal scoring, query composition, hybrid search, rerankers, graphs, supersession, K discipline.
- `scratch/research/query-construction-if-2026.md` — follow-up: official docs for AI Dungeon, NovelAI, SillyTavern and KoboldAI; aidm source (`retrieval.ts`, `tiers.ts`); NarrativeEngine-P; HyDE, Query2Doc, RAG-Fusion, Self-RAG, Adaptive-RAG, FLARE and "Better Together" (2026). Sources carry quality tags; vendor claims were not treated as efficacy evidence.
- `scratch/findings-playtest-adr-020.md` — F6 (attribution), F7 (duplicated canary), F8 (noise), F10 (ignored tools).
- Code claims in §1 were verified by grep/Read during the interview and the review pass, not assumed from documents.
