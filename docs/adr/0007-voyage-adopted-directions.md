# ADR 0007 — Directions adopted from the Voyage competitive analysis

- **Status**: Proposed
- **Date**: 2026-06-15
- **Context items**: Voyage (Latitude/AI Dungeon) analysis — `scratch/research/voyage.md`
  (built from a real session HAR + interrogation of Voyage's in-world "Narrator
  Assistant", 2026-06-15)
- **Scope note**: this is a **direction-setting** record. It fixes the *shape* of the
  lighter directions that came out of the Voyage analysis and do **not** warrant their
  own ADR. The three heavy refactors (world model, NPC enrichment, PG customization)
  get dedicated ADRs — see *Spin-off ADRs* at the end.

## Context

We obtained beta access to **Voyage**, Latitude's AI-native RPG platform, and
reverse-engineered its architecture from a real-session HAR and from targeted
questions to its in-world "Narrator Assistant". The full analysis lives in
`scratch/research/voyage.md`. The headline finding: Voyage and SAGA share the same
core thesis (authoritative state + two-tier model routing + semantic memory), which
validates SAGA's bets. Voyage's cost-optimization machinery (per-feature
`costMicros`, fine-tuned cheap models, a usage pool) is **largely irrelevant to
SAGA**, because SAGA is BYOAK + self-hosted single-instance: the user pays their own
API bill, so there is no pool to optimize and any pattern that doubles per-turn LLM
calls is a real cost to the operator, not a free win.

This ADR records the directions that survived that lens and are light enough to live
in one place.

## Decision

### 1. Per-turn state reliability — **hybrid state-audit pass** (not full two-pass)

Voyage runs a dedicated small **state engine** that computes state deltas *before* a
separate **story engine** narrates ("DB = reality, narration = perception"). Copying
this literally is a trap on SAGA's BYOAK generic models: it hands the *hardest*
reasoning (deciding outcomes — did the lockpick break? did the blow land?) to the
*weakest* model. Voyage gets away with it because their state engine is fine-tuned
for the task; SAGA has no such model.

Adopted shape instead:

- The **strong DM model keeps narrating and deciding outcomes inline** with its tool
  calls (unchanged from today's single-pass loop and the BACKSTOP rule).
- Add a **cheap secondary "state-audit" pass** whose only job is the *easy* task:
  extract/reconcile the structured state implied by the narration against the tool
  calls that actually ran, and patch the drift (e.g. narration says "you pick up the
  sword" but `add_item` never fired → emit it). Extraction, not decision — safe for a
  cheap model.
- The audit can run **async / off the player's critical path** (no added latency),
  with the correction landing as a deterministic patch.

This delivers Voyage's "state is the truth" reliability without giving outcome
decisions to a weak model and without doubling the expensive narrative call.

### 2. **Maximum configurability** of memory + per-subsystem models (config-first, std 14)

Voyage exposes memory as preset depth levels (standard/enhanced/deep) and a model
variant per subsystem. SAGA's principle is stronger: **expose the raw knobs, not
presets**, all in `saga.config.yaml` (std 14).

- **Memory depth as raw numbers**: `context_window_turns`, retrieved-facts count,
  token cap, summary cadence, etc. are all directly configurable — *not* bucketed
  into named levels.
- **Guardrails are mandatory**: every such knob has an enforced **recommended range
  with a hard min and max** (e.g. you cannot set 9999 context turns and blow up the
  prompt; a sane minimum is also enforced). The exact ranges are provisional and
  settled at implementation.
- **Per-subsystem model + params**: SAGA already routes per subsystem (DM low/med/high
  tiers, NPC, compression). Extend this so the model and generation params of *every*
  subsystem — including the new state-audit pass — are configurable knobs.

### 3. **Narrator-corrector / turn editing** — deferred (future)

Voyage's "Narrator Assistant" is a meta agent, separate from the DM: read-only on
state, able to **edit a past turn** (`rewriteLastStory`-style) and patch state, running
*outside* the turn loop and asking confirmation before applying. SAGA has nothing like
this. It is an attractive feature — particularly **the ability to edit/rewind a turn** —
but **deferred**: not scheduled here. Captured so it is not lost.

## Rejected alternatives

- **Full two-pass (state engine then story engine)** — gives outcome decisions to the
  weaker/cheaper model on BYOAK generic models, risking *worse* state, and doubles
  per-turn LLM calls. Rejected for the hybrid audit. Reconsider **only** if SAGA ever
  ships a fine-tuned state-extraction model (then full two-pass becomes attractive).
- **Single-pass only (status quo)** — no safety net against "narrated but no tool
  called" drift beyond prompt discipline. Rejected in favour of adding the audit pass.
- **Preset memory levels (standard/enhanced/deep)** — less flexible than raw numeric
  knobs; contradicts the "everything configurable, with guardrails" goal. Rejected.

## Consequences

- **Positive**: state reliability improves without latency on the player turn and
  without handing decisions to a weak model; the engine becomes maximally tunable per
  self-hosted deployment; the turn-editing idea is preserved for later.
- **Trade-off**: the state-audit pass is a new (cheap) LLM call and a new
  reconciliation code path; its correctness must itself be tested. Config guardrails
  add validation surface to `config.py`.
- **Trade-off**: correction from the audit lands as a patch (possibly visible to the
  next turn), not synchronously within the narration.

## Spin-off ADRs (heavy, dedicated)

The three large refactors from the analysis each get their own record. **All three are
WIP — direction noted, nothing decided, requiring deep dedicated analysis before
acceptance:**

- **World model → multi-layer YAML refactor → ADR 0008.**
- **NPC enrichment (`status`, `update_npc`, removed-NPC archive) → ADR 0009.**
- **Player-character customization (skill progression + configurable ability scores)
  → ADR 0010.**

## Notes

Relationship to existing ADRs: **ADR 0006 (AI Director) is not superseded** — it owns
*proactive, off-screen* world movement (background), which is orthogonal to this ADR's
*reactive, per-turn* state-audit. The two are distinct "second brains". Source
analysis: `scratch/research/voyage.md` (local, gitignored research note).
