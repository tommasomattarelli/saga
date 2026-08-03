# ADR 0017 — NPC dialogue: batched beats and engine-spliced verbatim lines

- **Status**: Proposed (every structural fork closed by the owner interview 2026-08-02;
  numeric values, the exact marker token and the frontend segment split remain explicit
  TODOs. Flips to Accepted after implementation + playtest. Supersedes *in place* the
  2026-07-26 WIP stub of this same ADR, which recorded the problem and six open forks and
  decided none of them.)
- **Date**: 2026-07-26 (stub); design interview 2026-08-02.
- **Context items**: playtest on `v0.2.0-beta.1` (issues #52, #53); owner interview
  2026-08-02, grounded live in `ai/prompts/dm.yaml`, `ai/npc_director.py`,
  `core/dm/dm_nodes.py`, `core/dm/dm_graph.py`, `core/dm/dm_tools_executor.py`,
  `core/dm/npc_prehook.py`, `ai/router.py`, `models/turn.py`, `saga.config.yaml`, and
  FE `features/narrative/components/turn-block.tsx`, `shared/schemas/turn.ts`.
- **Scope note**: this ADR owns **where NPC lines come from inside a turn, who decides
  them, and how they reach the player**. Out of scope: the affect model (**0005**), the NPC
  record and its resolver (**0009**), what a promoted NPC may *do* and its context budget
  (**0014**, whose C1–C5 this ADR does not reopen), prompt factoring (**0004**, which
  inherits the rule changes in §E).

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values at
implementation. **TODO** = consciously open.

---

## 1. Context

**Grounding (live code, 2026-08-02).** The stub asserted three costs. The interview
verified them and corrected two of its premises.

- **The latency mechanism is specific, not diffuse.** `invoke_npc` is in `MEANINGFUL_TOOLS`
  (`ai/tools/dm_tools.py:36`), and `route_after_tools` sends the graph back to `dm_node`
  whenever a meaningful tool ran (`core/dm/dm_graph.py:55`). Every NPC line therefore
  *forces* another DM round-trip. The ceiling is not generous: `max_agent_steps: 5`
  (`saga.config.yaml:94`), so a three-beat scene (~6 calls) exceeds it.
- **`invoke_npcs_parallel` has never run in parallel.** `core/dm/dm_tools_executor.py:150`
  always calls it with `npc_names=[npc_name]` — a one-element `asyncio.gather`. The stub
  treated "it already exists" as free reuse; what exists is the signature, not the path.
- **The prompt forbids batching.** `dm.yaml:31` says *"Call invoke_npc for ONE NPC at a
  time — if multiple NPCs should speak, call them sequentially in narrative order, one per
  tool call."* The serialisation is instructed, not incidental.
- **`npc_dialogues` feeds memory, not only the UI.** `memory/fact_extractor.py:53-59`
  builds an `NPC dialogues:` section of the extraction prompt from it. Any change to how
  lines are carried has a second consumer the stub did not name.
- **Psychology moves at tool time.** `dm_tools_executor.py:305-314` applies `axis_changes`
  and flips `met_player` when the tool runs, i.e. **before** the DM narrates. A line that
  never reaches the player has already moved the world.
- **One line per NPC per turn is already enforced.** `dm_tools_executor.py:122` answers
  `"{name} has already spoken this turn."` on a second call.
- **Failure is player-visible.** A failed NPC call returns `NPCDialogue(dialogue="...")`
  (`ai/npc_director.py:99-101`), so the player reads an NPC saying literally "...".
- **The frontend renders bubbles after prose, not inside it.** `turn-block.tsx:70-76`
  renders `segment.text`, then maps `segment.npc_dialogues` to `<NPCBubble>`.

## 2. What must be preserved

The value of a separate NPC call is **not** the prose. It is that the NPC's *decisions* —
what it reveals, whether it lies, how it feels (`axis_changes`), what its secret agenda
pushes it toward — are not made by the DM, which knows everything and would leak. Any
option that makes the DM ventriloquise the NPC is disqualified on those grounds. This is
the same constraint 0014-C1 states from the other side: *"the DM narrator never sees
agendas — if the DM moved the companion in combat, the traitor could never betray."*

---

## 3. Decisions

### A. Turn architecture

- **A1 — One mechanism, two cadences (Decided).** 0014-C3 already decided that every
  present sheet-holder gets its own autonomous call every turn, and explicitly rejected
  DM-invoked acting (*"a forgetful DM = statue companion"*) — the same argument as #52.
  This ADR generalises that path from sheet-holders to **all present NPCs**: one code path,
  one contract. What differs is the **cadence**, not the mechanism: promoted NPCs are
  invoked automatically (0014-C3), ordinary NPCs are invoked **because the DM chose to**.
  *Rejected: two mechanisms* — 0014-C3 had already discarded the hybrid because two code
  paths mean the call pattern itself telegraphs who has secrets. *Rejected: everything
  through the mid-turn tool* — it reopens 0014-C1 and re-mutes the traitor.
- **A2 — Promoted NPCs run as a pre-pass, at party level (Decided).** Present promoted
  NPCs are invoked in parallel **before the first DM call**; their lines and actions enter
  the DM's context together with the player's action. They are not reacting to the player,
  they are **acting alongside** the player — party members at the same level as the
  player's own input. Adds **zero round-trips**: they run while the DM has nothing to do
  yet. *Rejected: same beat as ordinary NPCs* — the DM's first prose would be written blind
  to the companions' autonomous actions and could contradict them. *Rejected: pre-pass only
  in combat* — outside combat is exactly where agendas and betrayal live, and the forgetful
  DM would return there.
- **A3 — Ordinary NPCs are the DM's choice (Decided).** No engine-side relevance filter and
  no forced call for every present NPC. The DM decides who speaks. This dissolves the
  stub's F6 (wasted calls when the action turns out not to involve the NPCs): for ordinary
  NPCs nothing is spent unless the DM asks, and for promoted ones the cost knob is already
  0014-C3's `party_autonomy`.
- **A4 — Batching (Decided).** The DM emits **all** the `invoke_npc` calls of a beat in a
  **single response**; the executor dispatches them in parallel and the graph loops back
  **once**. A beat therefore costs three round-trips regardless of how many NPCs speak,
  against today's `2N+1`. *Rejected: a dedicated selector pre-pass* — it adds a call to
  every turn, including turns with no NPC to invoke. *Rejected: raising `max_agent_steps`
  alone* — it makes the symptom fit inside the cap while worsening latency and cost and
  leaving #52/#53 untouched.
- **A5 — Parallel within a beat, serial across beats (Decided).** A **beat** is one
  stimulus. NPCs reacting to the *same* stimulus are genuinely independent, so they run
  concurrently. An NPC reacting to *another NPC's line* is genuinely dependent, so it
  belongs to the next beat, whose call carries the previous beat's lines. The mechanism
  expresses the real dependency instead of picking one globally. A two-beat scene costs
  five round-trips against today's seven, and scales with **beats**, not with NPCs.
  *Rejected: a serial chain inside one step* — every NPC could react to every predecessor,
  but latency stays `O(N)` and the DM never mediates between lines. *Rejected: always
  parallel, DM orders the lines in prose* — the reaction would be apparent only; the NPC
  answering has seen nothing and is in fact answering the player.

### B. The line contract

- **B1 — One call returns many lines (Decided).** `invoke_npc` returns an **ordered list of
  1..N lines** rather than a single `dialogue`, plus the `action` and the `axis_changes` for
  the whole block. This is what lets an NPC speak three times in a turn without either three
  LLM calls or the DM inventing the intermediate lines — the two options that were the real
  trade before this. **Cap: minimum 1, maximum 6** (Refined — knob, §D3), to bound spam.
  Cost accepted: line 3 is written without knowing what the DM narrates between lines 2 and
  3 — the same concession already accepted in A5 for parallelism inside a beat. *Rejected:
  one call per line* — the cost the owner declined. *Rejected: the DM writes the
  non-load-bearing lines and the NPC owns the rest* — the boundary is a judgment call made
  by the DM, which is the same negative-instruction shape as rules 31/42 that #52/#53
  already show violated.
- **B2 — Marker plus engine splice (Decided).** The DM emits an **empty marker** where a
  line goes; the engine substitutes the verbatim text. The DM chooses **where**, the NPC
  decides **what**, the engine guarantees the **wording**. #53 is closed *by construction*
  rather than by obedience: the DM never types those words, so it cannot shorten, soften or
  mistranslate them. It also saves the tokens of re-emitting lines. *Rejected: the DM
  retypes the line between open/close tags, engine validates* — it pays for the line twice,
  only mitigates #53, and needs a tolerance threshold nobody can set principledly.
  *Rejected: the DM retypes with no validation* — rule 42 with new syntax.
- **B3 — Marker carries name and index: `[[Lyra:2]]` (Decided).** A flat beat-wide index
  (`[[3]]`) is unambiguous but its errors are **undetectable**: a wrong-but-legal index
  silently places another NPC's line where this one should have spoken. Name+index is
  redundant, and the redundancy is what makes a mismatch detectable — an unknown name or an
  index the NPC does not have is caught and degrades to the fallback in B5. Fuzzy name
  resolution already exists (`core/npc_resolver.resolve_npc`, `npc_name_match_threshold:
  0.85`), so accents and spacing are handled by shipped code. Exact token shape: **TODO**.
  *Rejected: index only* — see above. *Rejected: name only* — ambiguous as soon as an NPC
  has more than one line.
- **B4 — The line renders as a bubble at the marker position (Decided).** Not inline inside
  the prose: the existing `<NPCBubble>` surface is kept, but placed where the DM put the
  marker instead of after the whole segment. Consequence: the segment must reach the
  frontend **split** into ordered parts (§F).
- **B5 — Unplaced lines become bubbles at the end (Decided).** A line whose marker the DM
  omitted, or whose marker is malformed or unresolvable, renders as a bubble in the NPC's
  own order at the end of the turn. Zero extra calls, nothing lost, and the degraded path is
  **exactly today's rendering** — already shipped and tested, not a new branch to maintain.
  A forgetful DM costs that turn its rhythm, not its content. *Rejected: discard the line
  and roll back its effects* — `axis_changes` are one block per call, not per line, so they
  would have to be re-split, and it throws away output already paid for. *Rejected: retry
  the narration step* — one more DM call in the turns that are already longest, and a second
  failure still needs one of the fallbacks anyway.

### C. Hooks

The division: the **tool's** hooks own everything that must be true *before the DM narrates*;
the **turn's** post-hook owns everything that depends on *what the DM wrote*.

- **C1 — Pre-hook order: dedupe → beat guard → validate → cap (Decided).** In that order:
  (1) drop duplicate names inside the beat (`[Lyra, Lyra]` is one Lyra, and it does **not**
  fail the call); (2) drop names already invoked in *this* beat; (3) `validate_or_create_npc`
  per surviving name — presence, lifecycle, location, auto-create (`core/dm/npc_prehook.py:14`,
  unchanged); (4) apply the `max_npc_calls` cap **last**, so the budget is not spent on names
  that validation then rejects. The pre-hook **never fails the tool**: it trims and reports
  what it trimmed to the DM in plain language (std 13).
- **C2 — `called_npcs` becomes per beat, not per turn (Decided).** The current guard
  (`dm_tools_executor.py:122`) contradicts A5 head-on: it would block exactly the beat-2
  case A5 exists for. Reset per beat — inside a beat a repeat is pure waste (same stimulus,
  same answer), across beats the stimulus has changed. The per-turn ceiling stays implicit
  in `max_agent_steps`. *Rejected: an explicit per-NPC-per-turn cap* — a new knob overlapping
  two existing ones, with undefined behaviour when it runs out mid-conversation. *Rejected:
  removing the guard* — the same NPC twice in one beat is two paid calls for one question.
- **C3 — Tool post-hook (Decided).** Extends `_handle_npc_results`
  (`dm_tools_executor.py:272`), which already applies psychology, appends `last_interactions`
  and populates `npc_dialogues`. It gains:
  - **Placement handles in the result string.** Today the DM gets `Lyra: "…"` (line 292).
    It must now expose name and index, or the DM has nothing to put in a marker — this is
    the load-bearing part of the whole design:
    ```
    Lyra:1  "Non ho mai visto quel sigillo."
    Lyra:2  "E non voglio vederlo di nuovo."
    Oste:1  "Bevi e taci."
    ```
  - **Truncation to the line cap before the DM sees them.** Cutting afterwards would strand
    markers the DM had already placed.
  - **Empty and `"..."` lines filtered out**, so no placeable bubble can say nothing.
  - **`axis_changes` stay one application per NPC per beat** — not one per line. True today
    because the loop is per NPC result (line 285); written down as an invariant so a
    per-line loop does not regress it.
  - **`last_interactions` gets one entry per turn, lines joined.** Appending one entry per
    line (line 300-303) against `npc_last_interactions_kept: 3` would let a single
    six-line turn evict the NPC's memory of every previous conversation. The knob says
    "three interactions remembered", and a turn is one interaction.
  - **Reports what the pre-hook trimmed**, in plain language (std 13).
- **C4 — Turn post-hook, in `post_process_node` (Decided).** Not in the tool: it depends on
  the DM's narration. `core/dm/dm_nodes.py:161` already reconciles segment text against
  `state["narration"]` (lines 166-174), so the marker pass belongs there and needs no new
  node. It: parses the markers; treats an unknown or duplicated marker as absent (→ B5);
  appends unplaced lines; **strips every leftover or malformed marker**; and assembles the
  ordered segment parts. The load-bearing rule is the stripping — **no raw marker may ever
  reach the player.** If the DM writes `[[Lyra:3]]` and Lyra has two lines, the player reads
  clean prose, not brackets.

### D. Failure, caps, configuration

- **D1 — A failed NPC call means the NPC does not speak (Decided).** No line, no bubble, no
  marker to place. The DM receives a structured note ("Lyra did not answer") and narrates
  without giving her a voice: a silent NPC reads as a scene, an NPC saying "..." reads as a
  bug. The rest of the batch is unaffected — that is what `return_exceptions=True`
  (`npc_director.py:148`) is already for. Nothing is applied for that NPC, so its psychology
  does not move either. *Rejected: retry once* — latency on the critical path exactly when
  the provider is already failing, and on the free tier (the common self-hosted case) the
  retry usually fails identically. *Rejected: fail the whole turn with 502* — consistent
  with the #50 handling for the DM, but a background NPC would destroy a narration already
  paid for.
- **D2 — `max_npc_calls` caps a beat; the turn is bounded by `max_agent_steps` (Decided).**
  The knob already exists (derived from `npc_verbosity`, `medium` = 3, `ai/router.py:120`)
  and is currently dead, because the executor never passes more than one name. Batching
  revives it. Turn ceiling = `max_npc_calls × max_agent_steps`, implicit, **no new knob**
  (principle 2). *Rejected: an explicit per-turn cap* — a third knob overlapping two, and it
  must define what happens when it runs out mid-scene. *Rejected: no per-beat cap* — eight
  present NPCs would be eight parallel calls and a near-certain rate limit on free tiers.
- **D3 — Every tunable in config, none hardcoded (Decided; values Refined).** Knobs: the
  line cap (1..6), the NPC-call `max_tokens`, `max_agent_steps`. Today
  `npc_director.py:79` hardcodes `max_tokens=300` while *discarding* the `npc_behavior`
  value it just resolved from the router (`saga.config.yaml:49` says 1000) — a std 14
  violation on a live config value. The cap must also scale with the line cap: 300 tokens
  was sized for a single line. **On many providers reasoning tokens count against this
  budget**, so a low cap can be consumed entirely by thinking and return truncated JSON →
  `repair_json` → garbage → the `dialogue: "..."` of D1. The low cap is therefore a probable
  *cause* of the failure mode, not a separate concern. The same audit across every other LLM
  call site is tracked in `TODO.md` (four call sites hardcode it; only `dm_nodes.py:122`
  honours the config).
- **D4 — `max_agent_steps: 5` is too low for an agentic loop (Decided; value Refined).**
  Beats consume steps, so the cap now governs how many conversational exchanges a turn may
  contain. It is a tunable, not a constraint to design around. Exact value at implementation.

### E. Prompt seam (→ 0004)

- **E1 — `dm.yaml:31` is rewritten (Decided).** It currently *forbids* the batching A4
  requires, and instructs the sequential pattern that causes the latency.
- **E2 — `dm.yaml:42` is deleted, not reworded (Decided).** It is the "do NOT paraphrase"
  negative instruction that #53 shows violated. Under B2 the DM never writes the words, so
  the rule has nothing left to forbid. Verbatim becomes structural.

### F. Data and frontend

- **F1 — No database migration (Decided).** `narration_segments` is JSONB
  (`models/turn.py:28`) and `npc_dialogues` is not a column — it lives inside that JSONB and
  in the API response. The shape changes without Alembic.
- **F2 — Old turns keep rendering correctly, with no special-casing (Decided).** The B5
  fallback (bubbles after the prose) *is* the current rendering, so turns written before
  this ADR land on the fallback path by construction.
- **F3 — `NarrationSegmentSchema` gains an ordered split; the backend owns it (Refined).**
  `turn-block.tsx:70-76` renders text then bubbles, so placing a bubble mid-prose requires
  the segment to arrive already split into ordered parts. The backend emits the parts and
  the frontend stays dumb. Exact shape: **TODO**.

---

## 4. Decided vs open

| # | Decided | Open |
|---|---------|------|
| A1 | one mechanism, two cadences | — |
| A2 | promoted = pre-pass, party level | — |
| A3 | ordinary NPCs are the DM's choice | — |
| A4 | batch in one response | — |
| A5 | parallel in a beat, serial across beats | — |
| B1 | 1..N lines per call | exact cap value (1..6 agreed) |
| B2 | marker + engine splice | — |
| B3 | name+index marker | exact token shape |
| B4 | bubble at the marker position | — |
| B5 | unplaced lines → bubble at the end | — |
| C1 | pre-hook order, never fails | — |
| C2 | `called_npcs` per beat | — |
| C3 | tool post-hook, six changes | — |
| C4 | turn post-hook in `post_process_node` | — |
| D1 | failure = the NPC stays silent | — |
| D2 | cap per beat, no new knob | — |
| D3 | everything in config | `max_tokens`, line cap values |
| D4 | `max_agent_steps` must rise | value |
| E1/E2 | rules 31 rewritten, 42 deleted | wording (→ 0004) |
| F1/F2 | no migration, old turns safe | — |
| F3 | backend emits split parts | schema shape, FE work not measured |

Additional TODO not attached to a decision: the beat-2 context window. The next beat's NPCs
see the previous prose through `dm_narration=state["narration"][-500:]`
(`dm_tools_executor.py:154`) — a hardcoded 500 characters, never discussed, and now
load-bearing for A5's serial beats.

## 5. Consequences

**Positive.**
- A three-beat scene goes from seven sequential round-trips to five, and the count scales
  with beats rather than with the number of NPCs present.
- #53 is closed structurally: the DM cannot paraphrase a line it never writes.
- #52 is closed for promoted NPCs by A2 (they are never invoked by a DM that might forget)
  and reduced for ordinary ones, since a single batched decision replaces N chances to skip.
- Two rules leave `dm.yaml` instead of being reworded, which is what 0004 wants.
- A dead knob (`max_npc_calls`) and a dead parallel path (`invoke_npcs_parallel`) start
  doing the job they were written for.

**Trade-offs and risks.**
- An NPC writes its later lines without knowing what the DM narrates between them. Accepted,
  and the escape hatch is a second beat.
- The DM gains a new obligation (emit markers) as two others are removed. If it emits none,
  every turn silently degrades to today's rendering — cheap, but the failure is quiet, so
  marker-placement rate is the thing to watch in playtest.
- Batching concentrates load: a beat with the cap at 3 fires three concurrent provider calls,
  which reaches free-tier rate limits sooner than the same three spread across a turn.
- The line cap and the token cap are coupled; setting one without the other reproduces the
  truncated-JSON failure in D3.

## 6. Relationship to other ADRs

- **0014** — this ADR does not reopen C1–C5. It generalises C3's cadence rule to all present
  NPCs (A1) and fixes the seam C3 left open: *when* in the turn the autonomous call runs (A2).
- **0004** — inherits E1/E2 and the obligation blocks that carry them.
- **0005** — `axis_changes` return on this path; C3 fixes them at one application per NPC per
  beat.
- **0009** — the resolver (`resolve_npc`) and `npc_prehook` are reused unchanged; B3 depends
  on the fuzzy matching being there.
- **0003** — removes `start_combat`/`end_combat`; no probe or rule here depends on them.
- **0013** — the `<NPCBubble>` surface and colour-coded speakers are what B4 places.

## 7. Notes

No `/research` pass. Every decision rests on the live code (grounded above with file and
line) and on decisions already taken in 0014; no external prior-art or competitor claim is
load-bearing here.
