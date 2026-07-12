# ADR 0016 — Importance scoring for model routing

- **Status**: Proposed (all forks closed by owner interview 2026-07-13; weights/thresholds
  are Refined defaults validated empirically via the per-turn breakdown log. Flips to
  Accepted after implementation + playtest. Single sprint, **no hard gate** — the
  0006/0014 signals join the formula as those ADRs land.)
- **Date**: 2026-07-13.
- **Context items**: TODO router line "RIFARE `score_importance` — studio dedicato"
  (NEQ action_predictor spunto); owner interview 2026-07-13.

Legend: **Decided** = settled by owner. **Refined** = shape fixed, values tuned
empirically at implementation/playtest. **TODO** = consciously open.

## 1. Context

Routing low/medium/high is real — `route_ai_call` picks the DM tier from
`importance_score` — but the score it runs on is broken (grounded 2026-07-13):

- `score_importance` (`ai/context.py:182`) is base 5 ± 2 on **English-only keyword lists**
  ("attack", "look around"). Italian play never matches → **score is always 5 → tier is
  always medium**. The routing effectively routes nothing for a bilingual game.
- The combat bump reads `world_state.get("in_combat")` — a key with **zero writers**
  (dead code; the real flag was `combat_state.active`, which 0003 removes anyway).
- Only `DM_NARRATION` is tiered; `importance_score` is persisted on Turn but consumed by
  nothing else.

Constraint: BYOAK + latency. A dedicated pre-classifier LLM call would tax **every turn**
(~0.3-1s serial + 1 call) to catch the rare sudden peak — the owner rejected it on that
ground. The 2026-07 design passes changed what's available: engine state got richer
(in-combat window 0014-C3, sheet-holders present, arc tension 0006) and budget calls
already in flight can carry a rating (the post-turn summarizer). And one embedding per
turn is **already computed** for recall — reusable for semantic classification at zero
marginal cost.

## 2. Decisions

### A. Three-layer score, zero new LLM calls (Decided)

`importance = clamp_0_10(base 5 + Σ weighted signals)`, thresholds map the sum to the
tier. The layers:

1. **Engine-state signals (instant, deterministic, language-free).**
   In-combat window active (0014-C3 `last_hostile_event_turn` stamp — enters the formula
   when 0014 lands); sheet-holder/boss present in scene (0014); player HP below a
   threshold; 0006 `narrative.arc` tension high (when 0006 lands). Each signal has a
   config weight; absent subsystems simply contribute nothing.
2. **Embedding-anchor similarity (instant, reads the CURRENT action's intent).**
   Config holds anchor phrases per pole (high: "attacco qualcuno", "tradisco un alleato",
   "confesso il segreto"; low: "guardo in giro", "riposo", "controllo l'inventario"),
   embedded once and cached; the action's similarity to high-anchors minus low-anchors
   yields a bounded ±2 contribution. Catches paraphrase ("lo pugnalo alle spalle" ≈
   "attacco qualcuno") and works cross-language in multilingual embedding space.
   **No extra call**: the recall embedding request becomes a **batch of two texts**
   (0002-R2 composed query + naked action) — embedding APIs accept arrays; one call, two
   vectors.
3. **Summarizer stakes-rating (one-turn lag, reads the arc).** The existing post-turn
   summarization call extends its contract with a scene `stakes` rating; turn N routes
   with the rating from N−1 through a config map (`low → −2, normal → 0, high → +1,
   critical → +2`). The sudden peak the lag would miss is exactly what layer 2 catches.

The old keyword scorer and the dead `in_combat` bump are **removed**.
Rejected: *mini-LLM pre-classifier* (latency + a call on every turn on BYOAK, to catch
what anchors catch free); *local onnx classifier* (an ML runtime in the self-hostable /
casual-installer deploy for the same gain); *bilingual keyword expansion* (per-language
hand maintenance, blind to paraphrase — the original complaint); *hybrid with optional
classifier* (two scoring paths to validate).

### B. Thresholds, weights, and how they get decided (Decided)

- Scale stays **0-10** with config thresholds (today's `≤3 low / ≤6 medium / >6 high`
  become `saga.config.yaml` values, not enum states).
- **Sizing principle**: one *strong* signal alone moves the tier (combat window +2:
  5→7 high); *weak* signals must compound (hp low +1 + tension +1 = high only together);
  anchors capped ±2 (noisiest layer).
- **Empirical validation, not eyeballing**: every turn logs the full breakdown via
  structlog (each signal, sum, tier); `importance_score` already persists on Turn.
  Playtests read the log ("this turn deserved high — which signal failed?") and tune
  **config only, zero code**. LangSmith traces (existing TODO) give the cost-per-tier
  ground truth.

### C. Plumbing & failure modes (Decided)

- Scope v1: only `DM_NARRATION` is tiered (unchanged); other call types keep their own
  config. Extending tiers to the 0014 acting call is a future knob, not v1.
- Anchor embeddings cached **keyed by embedding provider+model** (provider switch must
  not reuse incompatible vectors); invalidated when the config anchor list changes.
- Embedding `None` (known provider-hardcode bug, TODO) or anchor layer unavailable → the
  formula runs on the remaining layers; never a crash, never a blocked turn (fallback =
  state signals + stakes, worst case base 5).
- The batch-embedding touch lands in `embeddings.py` — works today on OpenAI; the
  provider-wiring TODO stays the prerequisite for multi-provider embeddings, **not** for
  this ADR.
- No migration, no rung — config + code only.

## 3. Decided vs Open — quick index

**Decided**: A (three layers, zero new calls, keyword scorer removed), B (0-10 + config
thresholds, sizing principle, breakdown-log validation), C (scope, cache keying,
fallbacks, no schema).
**Refined**: all weights/thresholds/anchor lists (start values per §B, tuned from the
breakdown log); stakes-rating wording in the summarizer contract.
**TODO**: tiering other call types (acting call); multi-provider embeddings (existing
TODO, prerequisite only for non-OpenAI anchor scoring).

## 4. Rejected alternatives (with reasons)

Pre-classifier LLM call (latency+cost on every turn, owner-rejected on BYOAK grounds);
local onnx classifier (ML runtime in the casual deploy); bilingual keyword lists
(paraphrase-blind, per-language maintenance); optional-classifier hybrid (double scoring
path); keeping the dead `in_combat` bump (zero writers, and 0003 removes its ancestor).

## 5. Consequences

- **Positive**: routing becomes real for bilingual play at **zero added calls and ~zero
  latency**; every contribution is explainable (breakdown log) and tunable in config;
  the design absorbs future signals (0006 tension, 0014 combat window/boss) without
  rework; narrative peaks actually reach the strong model — the "Intelligent AI Routing"
  pillar stops being aspirational.
- **Trade-off**: anchor quality depends on the embedding model and ships degraded until
  the provider-wiring bug is fixed for non-OpenAI setups (fallback keeps it safe).
- **Trade-off**: the summarizer contract grows one field; its rating arrives with a
  one-turn lag by design (accepted — layer 2 covers entry spikes).

## 6. Relationship to other ADRs

- **0003** — removes `combat_state`; this ADR removes its dead reader.
- **0014** — the in-combat window stamp and sheet-holder presence are the two strongest
  state signals; they join when 0014 lands.
- **0006** — `narrative.arc` tension as a soft signal, when the Director lands.
- **0002** — the batch-embedding piggyback rides R2's composed-query call.
- **Narrative-probe TODO** — *which models* sit in each tier stays that line's scope;
  this ADR only decides *when* each tier is used.

## 7. Implementation plan (single sprint, no hard gate)

**S1**: remove keyword scorer + dead bump; state-signal registry (weights config,
absent-subsystem tolerance); anchor layer (config lists, batch embedding in
`embeddings.py`, provider-keyed cache, ±2 clamp); summarizer `stakes` field + config map;
threshold mapping in `route_ai_call` unchanged but config-fed; structlog breakdown;
tests: signal permutations → expected tier (deterministic layers), anchor scoring against
fixture embeddings, fallback paths (no embedding, no rating), config reload/invalidations.

## 8. Notes / sources

Grounded in code (`context.py:182` keyword scorer, `router.py:221` tier mapping, zero
`in_combat` writers, Turn persistence). NEQ's `action_predictor` was the June spunto; the
owner rejected its call-based shape on BYOAK grounds and the design landed on
reuse-what-already-runs (embedding batch + summarizer piggyback). No external validation
needed — the risky assumption (multilingual anchor quality) is guarded by the fallback
and validated by the breakdown log in playtest, not by prior art.
