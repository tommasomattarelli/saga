# ADR 0009 — NPC enrichment (lifecycle/condition status, `update_npc`, removed-NPC re-entry)

- **Status**: Proposed (direction + cross-ADR boundaries fixed via the 2026-06-21 design
  interview, grounded in the live code; **fine mechanics remain explicit TODOs**, may
  still be revised). Supersedes the earlier "WIP, nothing decided" stub.
- **Date**: 2026-06-21
- **Context items**: Voyage analysis (`scratch/research/voyage.md` §3.5); spun off from
  ADR 0007 (2026-06-15); deep design interview 2026-06-21 (all choices by the project
  owner), grounded in `npc_prehook.py`, `tools_world.py`, `core/death.py`, `prompts/npc.py`.
- **Scope note**: enriches the **NPC record and its mutation surface**. Excludes NPC↔NPC
  relations (ADR 0002), off-screen autonomy and the *causes* of off-screen death (ADR
  0006), the world-hierarchy address (ADR 0008), and the disposition/affect model (ADR
  0005). This ADR is implemented **after** the v1 affect work (0005); it is recorded now
  to fix the cross-ADR boundaries while that reasoning is loaded — not to schedule a build.

---

## 1. Context

SAGA's NPC model is already fairly rich: `disposition_toward_player` (±100),
`personality`, `motivation`, `secret`, `fear`, `last_interactions`, plus a pre-hook
auto-create at three detail levels (`minimal`/`standard`/`rich`,
`npc_prehook.py::_create_npc_profile`). Comparing against Voyage (§3.5), three gaps were
identified for the NPC *record/mutation surface* — but the interview's code review found
**two of the three are not greenfield**:

- **Physical/behavioural `status`** (`alert`/`injured`/`fleeing`) — but a `status` string
  is **already read** (`npc_prehook.py` reads `npc.get("status", "alive")` and treats
  `dead`/`removed` as sentinels), in a redundant OR with a `npc.get("is_dead")` read. Yet
  **no code path writes either onto an NPC record today** — the only `is_dead` writer
  (`dm_nodes.py:183`) is the *player's* death flag from `check_player_death`. So the NPC
  pre-hook is **read-only scaffolding with no writer**: NPC death/removal is effectively
  unimplemented, and this gap is partly a **cleanup of a duplicated reader**, not a new
  field.
- A generic **`update_npc` tool** — genuinely new (no generic NPC writer exists in
  `tools_world.py`; only `change_npc_disposition` & co.).
- A **removed-NPC archive** — `removed` is **already** the soft-delete sentinel value of
  `status`; there is no separate archive list today. The question is whether to *promote*
  it to a structure, not to invent it.

NPC↔NPC relations (ADR 0002) and off-screen autonomy (ADR 0006) are out of scope here —
already documented. The third heavy seam, **the world-hierarchy address (ADR 0008-J-iii)**,
was previously unacknowledged and is addressed below (§3.E).

---

## 2. Scope & boundaries

**In scope:** the NPC status model (lifecycle + condition); the `update_npc` mutation
tool and its field-write guardrails; removed-NPC re-entry; the auto-create interplay.

**Out of scope (owned elsewhere):**
- **NPC↔NPC relations → ADR 0002** (relationship graph). Removed NPCs keep their edges.
- **Disposition / affect model → ADR 0005** (multi-axis psychology). `update_npc` never
  writes disposition (§3.B1).
- **Off-screen autonomy + the *causes* of off-screen death → ADR 0006** (Director). The
  Director may write `lifecycle` through its queue (§3.A3).
- **The world-hierarchy address of an NPC → ADR 0008-J-iii.** Deferred (§3.E1).

---

## 3. Decisions

> Legend: **Decided** = settled in the interview. **TODO** = consciously deferred to
> implementation time, with a note on *what* must be resolved.

### A. NPC status model — split lifecycle / condition

- **A1 — Two orthogonal fields (Decided).** Replace the single overloaded `status` with
  **`lifecycle`** (closed enum `{alive, dead, removed}` — the sentinel the pre-hook
  already gates on) and **`condition`** (a transient physical/behavioural descriptor:
  `alert`/`injured`/`fleeing`/`calm`…). The pre-hook checks only `lifecycle`; `condition`
  is narrative flavor. Rejected: a single enum mixing both (collapses two axes — an
  `injured` NPC loses its `alive`-ness, and "injured-then-fleeing" is unrepresentable); a
  `list[str]` of states (pre-hook must scan the list; alive+dead can co-occur).
- **A2 — `lifecycle` is the single source of truth (Decided).** Resolve the duplicated
  **reader** (`is_dead` OR `status`) in the pre-hook: `lifecycle == "dead"` becomes the
  only death signal, and the NPC `is_dead` read is removed. Since no NPC `is_dead` is
  populated today (A1 context), the `world_state` migration that lifts `is_dead:true →
  lifecycle:dead` is **defensive** (it normalizes any stray data, not a populated field).
  Rejected: keeping the NPC `is_dead` read (leaves `removed` orphaned, doesn't resolve the
  duplication).
- **A3 — Write ownership + guardrail (Decided invariant; writer existence is a TODO).**
  `condition` is **DM-writable** (via `update_npc`); engine systems **may also** set it
  deterministically (e.g. combat → `injured`) — unlike `lifecycle`/`disposition` it has no
  single-owner restriction (it is non-terminal, non-identity flavor). `lifecycle` is
  **engine-owned**: the DM **cannot** flip it via the generic `update_npc` field write
  (keeping the dangerous `alive→dead` transition out of a plain field write). The
  authoritative writers — an **on-screen NPC combat/death path** and the **Director's
  off-screen queue (ADR 0006)** — **do not exist yet** (today `death.py` is player-only,
  `tools_combat.py` does not kill NPCs); standing them up is a **TODO**, symmetric with C's
  removal mechanism. What is *Decided* is the **invariant**: when those writers exist, they
  own `lifecycle`, the death system carries the `narrative_instruction`, and `update_npc`
  never touches it. The *causes* of off-screen death (faction seeds, disease, aging) are
  **owned by ADR 0006**, decided there. Rejected: `lifecycle` via `update_npc` (DM would
  bypass the death system / Director).
- **A4 — `condition` is a simple descriptor now (Decided).** No `duration`/tick/expire;
  the DM updates/clears it via `update_npc`. The timed status-overlay shape of **ADR
  0008-G3** (`duration_minutes` + tick/expire auto-expire) is **noted as a future
  alignment** option, not adopted (a tick-pass is out of place in a direction-only ADR).
  Rejected: adopting the timed shape now (machinery a "no mechanics decided" ADR
  shouldn't carry); never-timed (would forgo reuse of the 0008-G3 machine).
- **A5 — Surfacing (direction; rendering details TODO).** `condition` is prompt-surfaced
  (narratively relevant → the `<npcs_present>` scene block and optionally `prompts/npc.py`,
  which today render neither status nor condition); `lifecycle` is not surfaced except as
  the pre-hook gate.

**TODO (A):** exact field rename (`status` → `lifecycle`); `condition` enum vs free-form;
the migration ladder version; the exact prompt rendering of `condition`; **stand up the
NPC-death writer(s)** — an on-screen combat/death path and the Director off-screen path
(none exists today; the pre-hook reads a `dead` state nothing writes).

### B. `update_npc` tool

- **B1 — Excludes disposition (Decided — the crux).** `update_npc` writes only the
  non-affective fields. Disposition stays **exclusively** with ADR 0005
  (`change_npc_disposition` evolves into per-axis deltas). Domain split: **affect → 0005,
  everything-else → 0009**, so 0009 stays independent of 0005's axis-schema maturity.
  Rejected: subsume-everything (couples 0009 to 0005; loses `reason` / first-impression
  multiplier / named thresholds); disposition-as-escape-hatch (two write paths to one
  field → divergence). Mirrors the disjoint-write-domains pattern of ADR 0006.
- **B2 — Exhaustive whitelist ⊎ blacklist + an exhaustiveness test (Decided).** Every NPC
  field must belong to **exactly one** of `MUTABLE_WHITELIST` or `IMMUTABLE_BLACKLIST`
  (disjoint, total coverage). A unit test asserts the partition and **fails on any
  unclassified field** (std 11) — closing the "ghost field" gap that pure-whitelist (new
  field silently immutable) and pure-blacklist (new field silently mutable) both leave;
  this also guards the schema drift the free-dict NPC record already suffers (`npc.py`'s
  legacy `personality` dict-vs-string). `name` (identity key), `lifecycle` (engine-owned),
  and `disposition_*` (0005-owned) are blacklisted by construction.
- **B3 — Upsert, complementary to the pre-hook (Decided).** `update_npc` is
  create-if-missing + update. It **complements** the auto-create pre-hook: the pre-hook
  auto-creates minimal NPCs **reactively** on `invoke_npc`; `update_npc` is the
  **explicit/proactive** create+enrich path (the narrator can introduce a fully-specified
  NPC without it speaking). No conflict: the pre-hook creates **only if absent** (already
  `if name in npcs: …proceed`), so a `update_npc`-created NPC is not re-created or
  overwritten when later invoked. Rejected: update-only (DM can't introduce a rich NPC in
  one call); subsume-the-pre-hook (couples the paths, bloats the lean validator).

**TODO (B):** the exact whitelist/blacklist contents; **whether to introduce a typed NPC
Pydantic model** — the exhaustiveness test (B2) needs a canonical field set, which presses
toward typing the NPC record (a good direction, coherent with 0008-E1's typed entities,
but its own decision).

### C. Removed-NPC archive

- **C1 — No separate structure (Decided).** A removed NPC stays in `world_state.npcs` with
  its record intact, `lifecycle=removed`; the pre-hook already blocks it; scene rendering
  filters it but does **not** delete it. Re-entry = an engine action that sets
  `lifecycle` back to `alive` (+ optional `location`). NPC↔NPC relations (ADR 0002) are
  preserved by construction. Rejected: a separate `removed_npcs{}` store (two stores to
  keep consistent; 0002/0006 would have to look in the archive too → more surface).
- **C2 — `removed` and `dead` are orthogonal terminals (Decided).** `dead` is irreversible
  (narrated necromancy is out of scope); `removed` is "alive but off-stage" (exiled
  bandit, departed merchant) → it **has re-entry**. Both are gated by the pre-hook (already
  so). Rejected: removed-as-superset-of-dead (loses the reversible/irreversible
  distinction that re-entry requires).

**TODO (C):** the mechanism that sets `lifecycle=removed` and the re-entry action — a
dedicated semantic archive action (a DM tool? the Director?), which **must honor the A3
invariant** (not a generic `update_npc` field write).

### D. Auto-create interplay

- **D1 — Shared base scaffold; `lifecycle` always present (Decided).** Both creation paths
  (pre-hook `_create_npc_profile` and `update_npc` upsert) go through a **shared base
  function** so they cannot drift: `name` + `lifecycle="alive"` are **always** present at
  birth; `condition` is **optional** (born only if the DM sets it). The
  `minimal`/`standard`/`rich` levels keep governing the *other* fields. Rejected:
  each-path-its-own scaffold (the two diverge → re-introduces drift); deferring
  (`lifecycle='alive'`-at-birth is an invariant, not a fine mechanic).

### E. NPC `location` ↔ ADR 0008

- **E1 — Defer to 0008-J-iii (Decided).** ADR 0008 owns the world hierarchy → it owns how
  an entity addresses it. 0009 does **not** decide the representation: it only notes that
  `location` must migrate from a flat string to a hierarchy address (UUID + scoped
  resolution per 0008-F7), coordinated with 0008-J-iii. 0009 keeps `location` in the
  mutable whitelist (B2). Rejected: deciding the address here (would contradict a not-yet-
  settled 0008 and duplicate model-world ownership).

---

## 4. Decided vs Open — quick index

**Decided:** A1, A2, A3, A4, B1, B2, B3, C1, C2, D1, E1 (+ A5 direction).

**Open TODOs before Accepting (may still be revised):** field rename `status`→`lifecycle`
+ migration version (A); `condition` enum-vs-free-form (A); `condition` rendering (A5);
**the NPC-death writer(s) — on-screen + Director — which do not exist today** (A3); exact
whitelist/blacklist contents + whether to introduce a typed NPC model (B); the removal +
re-entry mechanism (C); the `location` hierarchy address (deferred to 0008-J-iii).

---

## 5. Rejected alternatives

- **Single overloaded `status` enum / `list[str]`** — rejected for the lifecycle/condition
  split (A1).
- **Keeping the `is_dead` bool alongside `status`** — rejected; `lifecycle` is the single
  truth (A2).
- **`lifecycle` writable by the DM via `update_npc`** — rejected; engine-owned, to keep
  `alive→dead` inside the death system / Director (A3).
- **`condition` with the timed 0008-G3 shape now** — rejected; descriptor-only, G3
  alignment noted for later (A4).
- **`update_npc` subsuming disposition / disposition as an escape-hatch** — rejected;
  affect is 0005's, disjoint domains (B1).
- **Pure whitelist / pure blacklist** — rejected for the exhaustive partition + test (B2).
- **`update_npc` update-only / subsuming the pre-hook** — rejected for upsert +
  complementary (B3).
- **A separate `removed_npcs{}` store** — rejected; `lifecycle=removed` in place (C1).
- **`removed` as a superset of `dead`** — rejected; orthogonal terminals (C2).
- **Per-path creation scaffolds** — rejected for a shared base function (D1).
- **Deciding the NPC hierarchy address here** — rejected; deferred to 0008-J-iii (E1).

---

## 6. Consequences / risks

- **Positive:** resolves the `is_dead`↔`status` duplication; establishes a clean
  **affect / facts / lifecycle** domain split across 0005 (affect), 0009 (facts +
  lifecycle field), and the engine (lifecycle transitions); the exhaustive partition +
  test prevents NPC schema drift by construction; the archive adds **zero new structure**
  and preserves relations (0002) for free; the previously-silent 0008 and 0005 seams are
  now documented.
- **Trade-offs:** a `world_state` migration (`is_dead`→`lifecycle`); the exhaustiveness
  test presses toward typing the NPC record (extra surface, but a healthy direction); a
  coordination dependency on ADR 0008 for the `location` address.
- **Risks:** the NPC-death writers don't exist yet — until they're built (A3 TODO) the
  pre-hook gates on a `dead` state nothing produces, so NPC death is inert; once built, the
  multiple authoritative paths (combat/death/Director) must stay consistent — mitigated by
  engine-ownership (A3) and the Director's queue consistency-check (ADR 0006). Residual
  schema drift in the free-dict NPC record — mitigated by the B2 test and the typed-model
  pressure.

---

## 7. Relationship to other ADRs

- **ADR 0002 (relationship graph)** — NPC↔NPC relations, out of scope; a `removed` NPC
  keeps its edges (C1).
- **ADR 0005 (multi-axis psychology)** — disposition/affect, out of scope; `update_npc`
  excludes disposition (B1) and `disposition_*` is blacklisted (B2). The clean affect↔
  facts boundary is this ADR's central deconfliction.
- **ADR 0006 (AI Director)** — off-screen autonomy and the *causes* of off-screen death;
  the Director writes `lifecycle` through its queue (A3). Not superseded.
- **ADR 0007 (Voyage directions)** — parent ADR; this is its NPC-enrichment spin-off.
- **ADR 0008 (world model)** — the NPC `location` hierarchy address is deferred to its
  J-iii (E1); `condition` may later adopt its G3 timed-overlay shape (A4).

## 8. Notes / sources

Source: `scratch/research/voyage.md` §3.5 (competitor analysis). Decisions from the
2026-06-21 design interview (all calls by the project owner), grounded in the live code:
`npc_prehook.py`, `tools_world.py`, `core/death.py`, `prompts/npc.py`.
