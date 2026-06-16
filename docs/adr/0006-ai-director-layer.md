# ADR 0006 — AI Director layer above the DM (v2.5)

- **Status**: Proposed
- **Date**: 2026-06-09
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — item #10; target v2.5
- **Scope note**: this is a **direction-setting** record for unbuilt v2.5 work. It
  fixes the architectural *shape* and the rejected alternatives. Concrete mechanics
  (queue schema, apply-time validation rules, the cadence value N) are **provisional**
  and settled at implementation time.

## Context

SAGA's "Living World" is a core pillar, but today the world only moves as a
**side-effect of the DM's tool calls during a player turn** — there is no proactive
world-mover. Nothing plants/pays off foreshadowing, advances faction agendas, or
moves absent NPCs unless the reactive turn loop happens to. The surveyed
production system (aidm) separates a higher-level **Director** (arc planning,
foreshadowing ratification, off-screen world movement) from the turn-level DM —
a "drama manager" above the scene runner.

## Decision

Introduce an **AI Director** that sits *above* the DM and owns the off-screen
world. Its decided shape:

1. **Domain separation (the backbone).** The Director governs the **off-screen
   world** (factions, *absent* NPCs, world clock events, narrative arc/tension,
   foreshadowing seeds). The DM governs the **on-screen scene** (present NPCs,
   dialogue, active combat). They never write the same state — this is what makes
   "always accepted" safe: the Director *cannot contradict the DM* because their
   write-domains are disjoint. The Director must not touch entities present in the
   current scene.
2. **Background cadence.** The Director runs as a fire-and-forget background task
   every N turns (reusing the existing pattern of `_background_global_summary` in
   `app/api/turns.py`), off the player's critical path. N is configurable
   (`saga.config.yaml`, std 14); provisional.
3. **Queue → deterministic apply (single writer).** The Director never mutates
   live `world_state` directly. It **enqueues proposed off-screen changes**
   (`pending_world_changes`) and updates narrative fields. The **turn path** is the
   sole writer of live `world_state`: it applies the queue deterministically at the
   start of the next turn it processes — see *Timing* below — before the DM node
   runs. No concurrent mutation, so no lost-update race (cf. ADR 0001).
4. **Output is world data only.** Everything the Director produces is a write to
   world data: mechanical facts *and* narrative fields (`narrative.tension_level`,
   `narrative.seeds`, `director_notes`). There is no separate side channel.
5. **DM reads results, not reasoning; no creative veto.** The DM consumes the
   *results*: hard world-facts as ground truth, plus soft narrative directives
   (tension, emphasis, foreshadowing) as **advisory** context it interprets
   stylistically. The DM never sees the Director's *deliberation*, and has **no
   discretionary/creative veto** over the facts ("always accepted"). The *only*
   filter on a Director change is the mechanical **consistency check at apply**
   (point 6) — "always accepted" is not "applied even if impossible".
6. **Consistency validation at apply.** When the turn path applies a queued change
   whose precondition no longer holds (e.g. the Director queued "Aldric travels to
   town" but the player killed Aldric meanwhile), it **discards or reconciles** that
   change rather than writing an incoherent world.
7. **Routing & loop control.** A new `AICallType.DIRECTOR` (thinking tier, off the
   critical path). The Director's planning loop carries an explicit
   `max_iterations` hard cap (std 19). Being a background task that does LLM calls
   *and* DB writes, it follows the rule-15 discipline (read → close session →
   reason/LLM → open session → write the queue), per ADR 0001.

## Rejected alternatives

- **Inline node in the turn graph** — adds latency to every turn and chains
  world-movement to the player's cadence. Rejected for background cadence.
- **Direct mutation of live `world_state`** — reopens the concurrent-write race
  and lets the Director stomp the active scene. Rejected for queue → apply +
  domain separation.
- **All-hard output** (narrative pressure as binding world data) — over-constrains
  the DM's prose. Rejected: facts hard, pressure soft/advisory.
- **On-screen authority for the Director** — would let it contradict the DM
  mid-scene. Rejected: off-screen only.

## Consequences

- **Positive**: the world genuinely moves on its own without latency on the player
  turn; foreshadowing/arc get an owner; "always accepted + disjoint domains"
  removes Director↔DM contention by construction; single-writer apply sidesteps the
  concurrency race.
- **Trade-off**: a real new agent layer (state, prompts, routing, scheduling) — v2.5
  weight, sequenced behind the v1 forks (ADR 0002-0005).
- **Trade-off**: consequences the player triggered off-screen surface with a lag of
  one Director cycle. Acceptable — that lag *is* the "world moving while you were
  away" effect.

## Timing (precision)

Changes apply at the start of the **first turn after the queue is ready** — not
necessarily N+1. A thinking-tier Director fired after turn N may not finish before
a fast player submits N+1; in that case its changes land at N+2. The apply step is
idempotent and guarded (cf. the `chronicled_at`-style guard on existing background
tasks).

## Notes

Composes with: ADR 0001 (session lifecycle / turn-number claim — the apply is a
turn-path write), ADR 0002 (the relationship graph the Director reads/updates for
faction agendas), and the `foreshadowing-seeds` and `narrative_arc` TODO items
(the Director is their owner). Distinct from the DM: the DM resolves the *scene*,
the Director moves the *world*.
