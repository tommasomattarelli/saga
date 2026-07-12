# ADR 0007 — Directions adopted from the Voyage competitive analysis

- **Status**: Proposed (directions 2026-06-15; **§1 state-audit fully designed** by the
  2026-07-13 pass — every fork closed by owner interview. §2 stands as direction (its first
  fruit shipped into 0004's whitelist design); §3 stays deferred.)
- **Date**: 2026-06-15; §1 design pass 2026-07-13.
- **Context items**: Voyage (Latitude/AI Dungeon) analysis — `scratch/research/voyage.md`
  (real-session HAR + in-world "Narrator Assistant" interrogation, 2026-06-15); owner
  interview 2026-07-13.
- **Scope note**: §1 is now an implementable spec; §2/§3 remain direction-setting. The
  three heavy refactors spun off in June each have their own ADR (0008/0009/0010).

Legend: **Decided** = settled by owner. **Refined** = shape fixed, values at
implementation. **TODO** = consciously open.

## Context

Voyage runs a dedicated small **state engine** computing state deltas *before* a separate
**story engine** narrates ("DB = reality, narration = perception"). Copying that literally
on SAGA's BYOAK generic models hands the *hardest* reasoning (deciding outcomes) to the
*weakest* model — rejected in June for a **hybrid**: the strong DM keeps deciding inline
(BACKSTOP rule), and a cheap async **state-audit** pass patches the drift the DM leaves
behind: narration says "you pick up the sword" but `add_item` never fired — story and
state silently diverge, and today the only defense is prompt discipline.

Grounded 2026-07-13: everything the auditor needs is already persisted per turn —
`Turn.narration` + `Turn.world_updates.tool_events` (`turns.py:148`) — so the audit is a
pure post-hoc reader. And the 2026-07 design passes shrank the auditable surface: HP,
damage, dice, prices and equip are now **engine-authoritative** (0003/0010/0015) — the
audit must never touch them.

## 1. State-audit pass — designed (2026-07-13)

- **§1-A — Auditable drift classes (Decided; owner-extended, then bounded).**
  **Inventory** (acquired/lost narrated without `add_item`/`remove_item`), **quest**
  (progress narrated without `update_quest`), **location** (movement narrated without
  `move_to`), **NPC `remove`/`restore`** (departures/returns — *reversible* lifecycle ops
  only), **time** (missing `advance_time`, additive, minutes cap in config). **Never**:
  `kill`/`dead` — terminal per 0009, a cheap-model false positive is *unrecoverable*
  corruption, and real death already has two guarded writers (HP→0 engine writer,
  `kill_npc`); never anything engine-authoritative (0003/0010/0015); never psychology.
  Class list is config so playtest can grow it. Rejected: *kill in scope* (irreversible +
  already owned); *inventory-only* (quest/location drift is the same mechanism for free).
- **§1-B — Apply path: the 0006 queue, generalized (Decided).** The `director_changes`
  table becomes the **background-writer queue**: a `source` column
  (`director | state_audit`), same INSERT-by-task / take→guard→apply→mark exactly-once
  transaction at turn start, same audit trail. **Guards are per-source**: the Director is
  forbidden on-screen; the audit is the opposite (it patches the just-narrated scene) —
  different guard policies, one mechanism, one test surface. Whichever ADR lands first
  creates the table with `source` (cross-note added to 0006). Apply order = `created_at`
  across sources. Rejected: *dedicated pending column* (the design 0006 already rejected —
  no trail, and two exactly-once paths to keep coherent); *direct post-task write* (the
  ADR-0001 lost-update race, already paid for once).
- **§1-C — Anti-hallucination guards (Decided).** The audit **only adds missing
  effects** — it can never contradict an executed tool. Per-type preconditions at apply,
  drop+log on failure, never guessing (F7): item dedup (not already in inventory — also
  catches the stale-patch case where the player picked it up manually before the patch
  landed); **location = a direct position set** via 0008 scoped resolution — *never the
  travel engine* (time/encounters must not be rolled for an already-narrated arrival;
  unresolvable place → drop); quest must exist; NPC ops on unique resolve only. Input =
  DM narration + `tool_events` + a minimal state slice (inventory names, active quests,
  position) so the model diffs instead of imagining; NPC dialogue lines excluded v1
  (TODO). Output = typed patch JSON validated per-entry (drop+log), expressed in the
  existing updater/tool semantics (items follow 0010-I2 resolve-or-create).
  `audit_max_patches_per_turn` cap (std 19/14). No self-reported confidence scores — the
  precondition is the filter, not a number the model grades itself on.
- **§1-D — Cadence, routing, idempotency (Decided).** Fire-and-forget after every turn
  (the `_background_*` pattern), **on by default** (`state_audit.enabled: true` — a safety
  net that ships off protects only those who don't need it; cost = 1 budget call/turn,
  kill-switch in config). New `AICallType.STATE_AUDIT`, budget tier. Idempotency:
  `audited_at` stamp on Turn — the first real incarnation of the `chronicled_at` TODO
  pattern — written **in the same transaction** as the patch INSERTs (no double audit on
  crash/retry). Failure = skip + log, never a blocked turn; rule-15 session discipline.
- **§1-E — Accepted trade-off (unchanged from June).** The correction lands at the next
  turn's start, not synchronously — narrated sword appears in the inventory one turn
  later. That lag is the price of zero added latency on the player turn.

## 2. Maximum configurability of memory + per-subsystem models (direction, stands)

Raw knobs over presets, all in `saga.config.yaml` (std 14), every knob with an enforced
hard min/max; model + params per subsystem (now including `STATE_AUDIT` and `DIRECTOR`).
First fruit already shipped in design: 0004's **whitelisted per-campaign
`config_override`** is exactly this principle's guardrail applied per-campaign. The
memory-depth knobs land with 0002 S1 (`recall.*` family). No further design needed here.

## 3. Narrator-corrector / turn editing — deferred (unchanged)

Voyage's meta agent (read-only on state, can rewrite a past turn and patch state, asks
confirmation) remains attractive and remains **deferred** — captured so it is not lost.
Note the boundary: §1 audits *forward* (missing effects of the last turn); §3 would edit
*backward* (rewriting history). Different machines; do not conflate.

## Rejected alternatives

- **Full two-pass (state engine → story engine)** — outcome decisions to the weakest
  model + doubled per-turn calls; reconsider only with a fine-tuned extraction model.
- **Single-pass only (status quo)** — prompt discipline as the only defense against
  silent drift.
- **Preset memory levels** — contradicts raw-knobs-with-guardrails.
- §1 pass: kill-capable audit; inventory-only scope; dedicated pending column; direct
  writes; travel-engine location patches; confidence self-scores.

## Consequences

- **Positive**: "state is the truth" reliability without giving decisions to a weak model
  and with zero player-visible latency; the queue mechanism, guards, audit trail and
  exactly-once apply are shared with 0006 (one implementation, two writers); every knob
  config-first.
- **Trade-off**: +1 budget LLM call per turn (default on, kill-switch); a new
  reconciliation path whose correctness needs its own contract tests (fixture narration +
  tool_events → expected patches).
- **Trade-off**: one-turn patch lag (accepted, §1-E).

## Relationship to other ADRs

- **0006** — shares the generalized background-writer queue (`source` column, per-source
  guards); proactive off-screen vs reactive on-screen: the two "second brains" stay
  distinct in authority, now unified in plumbing.
- **0003/0010/0015** — define the engine-authoritative surface the audit must never touch;
  item patches follow 0010-I2 semantics.
- **0008** — scoped place resolution for location patches (position set, never travel).
- **0009** — reversible lifecycle ops only; `dead` stays behind its two guarded writers.
- **0004** — §2's guardrail principle landed there as the config_override whitelist.

## Implementation plan (single sprint)

**S1**: `source` column on the shared queue (create the table if 0006 S1 hasn't — schema
aligned with 0006 §C2); auditor task (context assembly from Turn rows, prompt, typed
output validation); per-type preconditions + guards; `audited_at` migration + transactional
stamp; `AICallType.STATE_AUDIT` + config block; contract tests (fixtures → expected
patches) + integration tests on apply/dedup/stale-patch/position-set.

## Notes / sources

Source analysis: `scratch/research/voyage.md` (local, gitignored). §1 design pass grounded
in code (turn persistence, tool_events, updater handlers, 0006/0008/0009/0010 contracts);
no external validation needed — the June external claim (Voyage's architecture) was
already validated by the HAR analysis.
