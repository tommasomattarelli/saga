# ADR 0017 — NPC dialogue: mid-turn tool call vs. parallel pre-pass

- **Status**: **WIP — nothing decided.** Stub written 2026-07-26 to hold the problem
  while it is fresh from the playtest. No fork below is closed; no owner interview has
  happened yet. Do not implement against this document.
- **Date**: 2026-07-26 (stub)
- **Context items**: playtest on `v0.2.0-beta.1` (issues #52, #53); `app/ai/prompts/dm.yaml`
  rules 31/42, `app/ai/npc_director.py`, `app/core/dm/dm_nodes.py`,
  `app/core/dm/dm_tools_executor.py`, `app/core/dm/npc_prehook.py`.
- **Relationship to other ADRs**: touches **0004** (prompt factoring — the obligation
  blocks that carry these rules), **0005** (`axis_changes` come back on this path),
  **0009** (the NPC record and the F2 resolver), and **0014**, whose per-turn
  "autonomous acting call for present sheet-holders" is the same shape as the pre-pass
  option below and is therefore a precedent, not a competitor.

---

## 1. Problem

NPC dialogue today goes through a mid-turn tool: the DM narrates, calls
`invoke_npc(name, context)`, receives the NPC's line, and continues. The playtest
exposed three costs.

**Latency.** A scene that alternates dialogue with description serialises the two
models. Three dialogue beats cost roughly `DM → NPC → DM → NPC → DM → NPC → DM` —
seven round-trips in sequence, capped only by `MAX_STEPS`.

**Compliance.** The DM skips the call when it is narratively convenient (#52) and
paraphrases the result when it does call (#53). Both rules exist and both are violated.

**Rhythm.** The tool boundary chops the DM's prose into a "before" and an "after"
around each line, which is the opposite of how a scene reads.

## 2. What must be preserved

The value of a separate NPC call is **not** the prose. It is that the NPC's *decisions* —
what it reveals, whether it lies, how it feels (`axis_changes`), what its secret agenda
pushes it toward — are not made by the DM, which knows everything and would leak.
Any option that makes the DM ventriloquise the NPC is disqualified on those grounds.

## 3. Options on the table

**A. Status quo** — mid-turn tool call.
Independence and a dedicated bubble, at the cost of everything in §1.

**B. Parallel pre-pass** — before the DM narrates, invoke every present NPC that
plausibly reacts, **concurrently**; their verbatim lines and `axis_changes` enter the DM
context; the DM writes one continuous scene that places those lines as given.
Collapses the three-beat scene to two serial round-trips, and uses fewer total calls than
A. `invoke_npcs_parallel` already exists. Cost: the NPC reacts to the player's action
rather than to the DM's framing of it, and cannot react to something the DM invents
mid-turn.

**C. Intent-only NPC call** — the NPC returns stance and beats, the DM writes the words.
Best narrative flow, but it surrenders the distinct voice, which is the point of §2.
Recorded so it is not re-proposed; the stub author's view is that this should be rejected.

## 4. Open forks — none of these are decided

- **F1.** Does B replace A, or does `invoke_npc` survive as an escape hatch for NPCs not
  present at turn start (a bandit revealed behind a door)? The stub author leans hybrid:
  pre-pass as the normal path, tool for genuine mid-turn arrivals.
- **F2.** Which present NPCs get invoked each turn, and who decides? All present, a
  cheap relevance filter, or a DM-declared list from the previous turn? Bounded by cost —
  N NPCs present means N calls per turn even when parallel.
- **F3.** How does the frontend render a line the DM has woven into its prose? Inline
  quoted dialogue (drop the bubble), or speaker-tagged segments the DM must emit?
  ADR 0013 already ships colour-coded speakers, so the surface exists either way.
- **F4.** How is "place these lines verbatim" enforced any better than rule 42 is today?
  If the answer is "another negative instruction", B inherits A's compliance problem.
- **F5.** Interaction with 0014's acting call — one mechanism serving both dialogue and
  actions for promoted NPCs, or two? Answering F5 probably answers F2.
- **F6.** What happens when the pre-pass runs and the player's action turns out not to
  involve the NPCs at all? Wasted calls, or is that acceptable given they are parallel
  and off the critical path?

## 5. Next step

An owner design interview, as with every other ADR here. Until then this file is a
holding pen: it records the problem and the shape of the options, not a decision.
