# ADR 0005 — Multi-axis NPC psychology (world-defined axes)

- **Status**: Accepted — **implemented 2026-07-07**, full cycle S0–S3 on
  `adr/0005-npc-psychology` (suites green: 548 unit + 41 integration/playtest BE, 129 FE,
  mypy/ruff clean). Pending, tracked in `TODO.md`: manual playtest of budget-model delta
  quality (the ADR's #1 risk — fix would be prompt wording, not schema) and the PR to `main`.
- **Date**: 2026-06-09 (direction) · 2026-07-07 (S0 design pass + implementation)
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork D; S0 design
  interview 2026-07-07 (all choices by the project owner), grounded live in
  `npc_director.py`, `memory/updater.py`, `tools_world.py`, `prompts/npc.py`,
  `prompts/dm.py`, `npc_prehook.py`, `world_instantiation.py`, `models/world.py`,
  `memory/world_state.py`.

---

## 1. Context

"Living World — NPC psychology" is a SAGA core pillar, but the current model is thin:
NPC dispositions reduce to a **single scalar**. A scalar collapses distinct relationship
dimensions — an NPC can fear the player, respect them, and dislike them at once, and a
scalar cannot represent that. It also makes narrative inconsistencies easy (a "friendly"
score doesn't stop betrayal driven by low trust).

The full scalar surface today (verified in code, 2026-07-07):

- **Writers** (all converge on one updater handler):
  `npc_director.py:74` (LLM emits `disposition_change: int` in the NPC dialogue JSON) →
  applied in `dm_tools_executor.py:292`; the DM tool `ChangeNpcDisposition`
  (`tools_world.py:142`); both route through `memory/updater.py:26`
  (`_handle_npc_disposition`, clamps ±100).
- **Readers**: the NPC's own prompt (`prompts/npc.py:68`, raw number on a −100/+100
  scale); the DM `<scene>` block (`prompts/dm.py:27` `_disposition_label` — 5 hardcoded
  labels loyal→hostile); auto-create seed (`npc_prehook.py:43`, seeds 0); world
  instantiation seed (`world_instantiation.py:92` ← authored `NpcRecord.disposition`,
  `models/world.py:227`).
- **Adjacent but distinct**: factions carry their own scalar
  (`world_state.factions[*].disposition`, `world_instantiation.py:111`; FE `FactionData`).
- The FE never renders NPC disposition — frontend impact of this ADR is limited to the
  world editor (Sprint 3).

Two surveyed repos converge on multi-axis relationship models: ai_rpg's
`dispositions.yaml` (6 independent axes, each ±200 with named thresholds and a
`first_impression_multiplier: 3`) and NEQ's 5D emotional vectors (trust, power,
intimacy, fear, respect). The convergence is the signal; romantic/lust axes are
genre-specific and out of scope.

## 2. Scope & boundaries

**In scope:** the per-NPC internal psychology model (how an NPC feels about the player),
its authoring (world taxonomy + seeds), its mutation surface (NPC dialogue contract, DM
tool, first-impression amplification), its reading surface (NPC prompt, DM `<scene>`),
and the `world_state` schema rung.

**Out of scope (owned elsewhere):**
- **NPC↔NPC / inter-entity relations → ADR 0002** (relationship graph). The graph may
  *read* these axes when resolving scene context; it does not own them.
- **NPC lifecycle/status, generic `update_npc`, removed-NPC re-entry, NPC world-address
  → ADR 0009** (explicitly sequenced *after* this ADR; `update_npc` never writes
  psychology, 0009 §3.B1).
- **Off-screen autonomy → ADR 0006** (the Director may move axes only through its queue).
- **Faction→player disposition** — same scalar disease, different beast (inter-entity
  relation, not individual psychology). Stays as-is; reworked under 0002/0006 territory.
  Tracked as an explicit `TODO.md` line.
- **LLM-generated full profiles at auto-create** (`npc_enrichment` config stub, v1.5+) —
  enrichment territory (0009). This ADR seeds auto-created NPCs at axis defaults; the
  first-impression multiplier then differentiates them from the first exchange.

## 3. Decisions

Legend: **Decided** (settled in the S0 interview) — there are no open TODOs.

### P. Axes are world-defined — 0008 P0 pattern reused (Decided)

The axis set, per-axis range, named threshold bands, `first_impression_multiplier` and
`max_delta_per_turn` are **all defined by the World**, in a new optional `psychology`
block of `taxonomy.yaml` (extends the ADR 0008 P0 vocabulary pattern; 0008 is Accepted
and is **not edited** — this ADR records the extension). Rationale (owner): everything
that is *game* is customizable in the world; global config holds infra/AI knobs only.
Consequences accepted in the interview:

- meta-schema + three-tier validation grow (unknown axis in an authored NPC = load
  error, referential tier);
- the world editor grows a psychology section (Sprint 3);
- a **bundled default** psychology block is copied into every new world at creation
  (0008 C4 pattern) — a world always has explicit axes;
- worlds/baselines predating this ADR lack the block → the engine accessor falls back
  to the bundled default set (one line; no baseline surgery).

```yaml
# taxonomy.yaml (bundled default, copied into new worlds)
psychology:
  first_impression_multiplier: 3.0
  max_delta_per_turn: 10
  axes:
    trust:
      range: [-100, 100]
      default: 0
      bands:
        - {min: -100, label: "betrayed-wary"}
        - {min: -30,  label: "suspicious"}
        - {min: -10,  label: "neutral"}
        - {min: 30,   label: "trusting"}
        - {min: 70,   label: "confides fully"}
    respect: {...}
    affection: {...}
    fear: {...}
```

### A. Axis model (Decided)

- **A1 — default set: 4 axes — trust, respect, affection, fear.** The classic
  interpersonal matrix (reliability / competence / warmth / threat), orthogonal, minimal
  prompt cost. More default axes was judged over-engineering: every axis costs tokens
  per NPC per turn in two prompts; budget models must judge one independent delta per
  axis; the extra candidates overlap (deference ≈ respect+fear; familiarity ≈ a counter,
  and `last_interactions` already tracks history). The escape valve is the world-defined
  design itself (a samurai world adds `honor`).
- **A2 — default range ±100** — the current scalar's scale (the prompt convention LLMs
  already see today); per-axis custom ranges allowed.
- **A4 — named threshold bands, per-axis labels** — default: 5 bands per axis with
  axis-specific evocative labels (trust: "suspicious"… "confides fully"; fear:
  … "terrified"). Band count and cuts are free per axis and per world (one axis may
  have 5, another 7).
- **A5 — DM `<scene>` render: salient axes only.** Each present NPC shows only the axes
  whose value sits **outside the band containing the axis `default`**; an all-neutral
  NPC renders clean (`<npc name="Bran" role="innkeeper"/>`). Contract detail: each axis
  has a `default` value (typically 0); the band containing it is the suppressed one.
  Rationale: the scene block is paid every turn per present NPC under a hard token cap
  (0008 J4) — everything shown must be signal.

### B. Mutation surface (Decided)

- **B1 — NPC dialogue contract**: `npc_director` output gains
  `axis_changes: {axis: int_delta}` (replaces `disposition_change`); omitted axes = 0;
  **unknown axes are dropped with a warning log** (parallel fire-and-forget calls — no
  feedback channel; never crash, std 13). Deltas are **clamped to
  `max_delta_per_turn` before the first-impression multiplier** is applied.
- **B2 — DM tool renamed**: `change_npc_disposition` →
  **`change_npc_psychology(npc, changes: {axis: delta}, reason)`** — contract symmetric
  with B1 (one mental model across both LLM surfaces). Unknown axis =
  **reject-with-candidates** ("Unknown axis 'honor'. This world's axes: trust, respect,
  affection, fear") — the DM loop can retry (0008 F7 pattern, std 13). Same cap. The
  rename touches the prompt-block reference in `saga.config.yaml` (`when: npcs_present`).
  The B1/B2 asymmetry (silent-drop vs reject) is intentional: the tool has a feedback
  channel, the parallel dialogue calls do not.
- **B3 — first impression**: explicit **`met_player: bool`** flag on the NPC record,
  `false` at creation/seed, flips to `true` at the **first interaction event of any
  kind** — a completed `invoke_npc` dialogue (even with zero/omitted deltas) or an
  applied axis mutation, whichever comes first ("met is met": a first chat with no
  emotional shift still consumes the first impression). The flip is **immediate**: if
  the same turn carries a second mutation on the same NPC (e.g. dialogue deltas plus a
  DM tool call), only the first applied one is amplified. While `false`, applied deltas
  are multiplied by `first_impression_multiplier`. Authored seeds (C3) do **not** flip
  it: authored prejudice is baseline; the first real meeting still amplifies on top.
  Migration marks existing NPCs `true` (never retro-amplify).

### C. Data & migration (Decided)

- **C1 — JSONB shape**: nested dict on the NPC record —
  `psychology: {trust: -12, fear: 24, ...}` + `met_player` — replacing
  `disposition_toward_player` (all readers updated in the same sprint).
- **C2 — schema rung v5→v6, trivial, no data lift.** The dev volume was wiped, pre-1.0,
  no external users (0008 J2 precedent): the rung only initializes `psychology` from
  axis defaults and `met_player: true` on any NPCs present, so a v5 save never crashes.
  No scalar→axis lifting.
- **C3 — authored seeds**: `NpcRecord` drops `disposition: int`, gains optional
  `psychology: {axis: value}` validated against the world taxonomy (unknown axis = load
  error). The editor NPC form exposes it. `world_instantiation` seeds
  taxonomy defaults merged with the authored values, `met_player: false`.
- **C4 — factions: out of scope** (see §2), with an explicit TODO line.

### D. Prompt surfaces (Decided)

- **D1 — NPC's own prompt**: each axis renders **number + band label**
  (`- trust: -30 (suspicious) [−100..100]`) — the number gives the gradient for
  calibrating deltas, the label gives the semantics for playing the part. The prompt
  also teaches the contract: the axis list valid in `axis_changes` and the per-turn cap
  (both world-derived, injected dynamically).
- **D2** = A5 (DM scene, salient-only).
- **D3 — labels live in the world taxonomy bands** (no i18n indirection; author-owned
  text, like every other world string).

## 4. Decided vs Open — quick index

**Decided**: P (world-defined, default bundled, fallback), A1 (4 default axes), A2
(±100 default), A4 (5 per-axis bands, free count), A5/D2 (salient-only scene,
default-band suppression), B1 (`axis_changes` dict, silent-drop, cap-then-multiplier),
B2 (`change_npc_psychology`, reject-with-candidates), B3 (`met_player`, flips at first
interaction event of any kind, immediate flip, authored seeds don't flip), C1 (nested
`psychology`), C2 (trivial rung, no lift), C3
(optional authored `psychology`, validated, editor field), C4 (factions out), D1
(number+label+taught contract), D3 (labels in bands).

**Open**: none. Implementation-time details (exact Pydantic model names, band resolver
placement, prompt wording) are free within the decisions above.

## 5. Rejected alternatives

- **Axis set in global `saga.config.yaml`** (the original Decision text) and **hardcoded
  axes + config thresholds** — rejected for the owner's placement principle: game
  content belongs to the world (0008 P0 precedent); config keeps infra/AI knobs.
- **±200 range** (ai_rpg) — no benefit over the ±100 convention the prompts already teach.
- **Generic shared band labels** ("very low"… "very high") — loses the point of named
  thresholds ("fear: high" vs "terrified"); **7 default bands** — 28 labels to write,
  adjacent bands LLM-indistinguishable.
- **Scene: all axes always** — token spend on repeated "neutral"; **single composite
  label** — re-collapses the model into a scalar exactly where narration happens.
- **`axis_changes` as a list of {axis, delta, reason} objects** — more output tokens
  from a budget model, more parse repair; the reason is already implicit in the dialogue.
- **Engine-fixed delta cap** — not tunable without code; the cap is game feel → world.
- **First-meeting inference from `last_interactions`** — a display ring buffer written
  only by dialogues; a DM tool change before the first dialogue would double-amplify.
  **Multiplier on first dialogue only** — a DM-narrated intimidation before any dialogue
  (common) would lose amplification. **Flip only on first *non-zero* mutation** — a
  first chat with zero deltas would leave the ×3 armed for the Nth encounter;
  unpredictable ("met is met" chosen instead).
- **Scalar→axis lifting migration** (onto trust and/or affection) — moot: volume wiped,
  pre-1.0, no saves to lift (J2); a trivial rung keeps the ladder intact at zero cost.
- **Authored NPCs always neutral** — regresses authoring (the scalar seed already
  exists today).
- **Single-axis-per-call DM tool** — N tool-calls per multi-axis shift (loop iterations,
  std 19); **keeping the `change_npc_disposition` name** — the name would lie about a
  dead concept.
- **Factions in scope** — doubles the surface (DM prompt, tools, FE `FactionData`) and
  a faction feeling "affection" is semantically wrong.
- **NEQ gravitational/crystallisation retrieval** — still explicitly not adopted (too
  complex); only the multi-axis idea is taken.

## 6. Consequences / risks

- **Positive**: mixed feelings become representable and legible (betrayal/loyalty get
  mechanical grounding); named bands read better than raw numbers in both prompts; the
  world owns its psychology vocabulary end-to-end (author → validation → prompts);
  auto-created NPCs differentiate fast via the ×3 first impression without any extra
  LLM call in the critical path.
- **Risk — budget-model delta quality**: `npc_director` runs on cheap models; judging 4
  independent deltas per exchange is unvalidated. Mitigations already in the design:
  per-turn cap, omitted-axes-are-zero, silent-drop of garbage axes. Validate in playtest;
  if quality is poor the fix is prompt wording, not schema.
- **Trade-off**: more state per NPC and a richer contract — bounded by the 4-axis
  default, salient-only scene render, and the hard scene token cap (0008 J4).
- **Editor scope grows** (taxonomy psychology section + NPC form field) — accepted in
  the interview; isolated in Sprint 3.
- **0008 stays frozen**: the taxonomy extension pattern is recorded here; `taxonomy.yaml`
  gains an optional block, old worlds keep loading (accessor fallback to the bundled
  default).

## 7. Relationship to other ADRs

- **0008 (Accepted)**: reuses the P0 world-defined-vocabulary pattern and the C4
  bundled-default pattern; extends `taxonomy.yaml` and the editor (I7) without editing
  0008 itself. Scene render lives inside the 0008 `<scene>` block under its J4 cap.
- **0009 (Proposed)**: sequenced after this ADR; owns lifecycle/status, `update_npc`
  (which never writes psychology), re-entry, enrichment.
- **0002**: the relationship graph may read axes for scene context; inter-entity
  relations (incl. faction→player) are its territory, composed with — not replacing —
  this model.
- **0006**: the Director mutates axes only through its pending-changes queue.

## 8. Notes / sources

Sources: NEQ emotional vectors, ai_rpg `dispositions.yaml` (research session
2026-06-09). Validation research for S0 was **skipped deliberately**: every decision
stands on first principles, code verified live during the interview (grep/Read, no
claims from memory), and patterns already shipped in 0008; the external prior art was
digested in the original research session.

## 9. Implementation plan (fixed 2026-07-07)

**Branch model** (0008 §9 precedent): one long-lived ADR branch
`adr/0005-npc-psychology` off `main`; each sprint on its own sub-branch
(`0005/s1-…`), merged into the ADR branch; a single PR lands the cycle on `main`.

- **Sprint 0 — design pass (no code). DONE 2026-07-07** (this interview): closed every
  fork; headline revision — axes **world-defined** (P0 pattern), not config-global as
  the original Decision text said. Committed directly on the ADR branch.
- **Sprint 1 — taxonomy + core. DONE 2026-07-07.** `psychology` block in the taxonomy meta-schema +
  bundled default; loader/validator (incl. referential check of `NpcRecord.psychology`);
  band resolver (value → band/label, default-band test for A5); updater handler
  multi-axis + clamp + `met_player` flip; schema rung v5→v6; instantiation seeds
  (taxonomy defaults ⊕ authored values). Pure backend, LLM contracts untouched.
- **Sprint 2 — LLM surfaces. DONE 2026-07-07.** `npc_director` contract + prompt (D1); executor applies
  `axis_changes` with cap→multiplier order; `change_npc_psychology` tool (B2) +
  `saga.config.yaml` prompt-block rename; prehook auto-create seeds axes; DM `<scene>`
  salient render (A5).
- **Sprint 3 — editor (FE). DONE 2026-07-07.** Psychology section in the taxonomy editor form; `psychology`
  field in the NPC form (validated refs, 0008 I7 pattern); i18n for editor chrome only
  (band labels are author content, D3).

Sprints 1–2 are backend-vertical; the cycle is shippable after Sprint 2 if needed
(worlds without authored psychology play fine on defaults), but the intended PR
includes all three.
