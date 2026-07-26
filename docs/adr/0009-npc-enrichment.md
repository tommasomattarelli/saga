# ADR 0009 — NPC enrichment (identity, lifecycle/condition, world-defined traits, `update_npc`)

- **Status**: Proposed (S0 design pass completed 2026-07-07 — every major fork closed by
  owner interview, grounded in the post-0005/0008 code; a few scoped TODOs remain, may
  still be revised before Accepted). Supersedes the 2026-06-21 direction-only version of
  this ADR, which itself superseded the "WIP, nothing decided" stub.
- **Date**: 2026-06-21 (direction), 2026-07-07 (S0 design pass)
- **Context items**: Voyage analysis (`scratch/research/voyage.md` §3.5); spun off from
  ADR 0007; design interviews 2026-06-21 and 2026-07-07 (all choices by the project
  owner), grounded in `npc_prehook.py`, `world_instantiation.py`, `memory/updater.py`,
  `tools_combat.py`, `dm_tools_executor.py`, `prompts/dm.py`.
- **Scope note**: enriches the **NPC record, its identity, and its mutation surface**.
  Excludes NPC↔NPC relations (ADR 0002), off-screen autonomy and the *causes* of
  off-screen death (ADR 0006), and the affect model (ADR 0005). Implemented **after**
  0005 and 0008, both now shipped — which resolved two premises of the 2026-06-21
  version (see §1).

---

## 1. Context

SAGA's NPC model was compared against Voyage (§3.5) in the 2026-06-21 interview; the
2026-07-07 S0 pass re-grounded everything in the code as it stands **after ADR 0005 and
0008 shipped**, which changed two premises:

- **`location` is solved.** NPC `location` is already a world-node UUID (0008 J3,
  `world_instantiation.py:89`); the old E1 deferral is closed.
- **Affect is solved.** `disposition_toward_player` no longer exists; NPCs carry a
  world-defined multi-axis `psychology` + `met_player` (ADR 0005). Every 0005 surface
  (scene block, psychology handler, `npc_director`) is **name-keyed** today — relevant
  to the identity migration below.

What remains broken or missing:

- **NPC identity is the display name.** `world_state.npcs` is keyed by `npc.name`
  (`world_instantiation.py:87`); the authored `slug` is dropped at instantiation;
  auto-created NPCs are keyed by whatever string the LLM passes to `invoke_npc`. Two
  "Guard"s collide; rename is impossible (the name *is* the key). Places already solved
  this exact problem (slug → runtime UUID + alias resolution, 0008 F7/F13).
- **NPC death is inert scaffolding.** The pre-hook reads `status`/`is_dead` sentinels
  (`npc_prehook.py:24-25`) that **no code path writes**. Combat tracks enemy HP
  server-side (`updater.py:207` `combat_damage`) but at HP ≤ 0 nothing happens — no
  defeated flag, no link to the NPC record.
- **No generic NPC writer** exists (`tools_world.py` has only the psychology tool).
- **The descriptive fields are hardcoded** (role/personality/motivation/secret/fear in
  `_create_npc_profile`) — against the P0 world-defined-vocabulary principle that 0008
  established and 0005 followed (psychology axes live in `taxonomy.yaml`).

---

## 2. Scope & boundaries

**In scope:** NPC identity (runtime UUID + resolution); the status model (lifecycle +
condition); world-defined descriptive traits (`npc_fields` in the world taxonomy); the
`update_npc` mutation tool and its field-write partition; removal/re-entry; the engine
death writer at HP ≤ 0; auto-create interplay; editor + prompt surfaces.

**Out of scope (owned elsewhere):**
- **NPC↔NPC relations → ADR 0002.** Removed NPCs keep their edges; stable UUIDs are a
  gift to the future relationship graph.
- **Affect → ADR 0005.** `update_npc` never writes `psychology`/`met_player`.
- **Off-screen autonomy + causes of off-screen death → ADR 0006.** The Director will
  write `lifecycle` through its queue; nothing is decided about it here.
- **Combat-system rework (thresholds, server-side damage mapping) → ADR 0003.** This ADR
  only *hooks* the existing HP-≤-0 moment; it does not touch resolution mechanics.

---

## 3. Decisions

> Legend: **Decided** = settled in interview. **TODO** = consciously deferred to
> implementation, with a note on *what* must be resolved.

### F. NPC identity — runtime UUID, mirror of 0008 *(new group, 2026-07-07)*

- **F1 — `world_state.npcs` keyed by runtime UUID (Decided).** uuid4 minted at campaign
  instantiation (exactly like place nodes: `slug_map`, "slugs never enter the save's
  reference graph"); auto-created NPCs get uuid4 at birth with `slug=None`. UUIDs are
  never authored, never editable, never shown to the LLM or the editor user. Rejected:
  slug-as-key (two identity conventions in one save; immutable key; ad-hoc dedup
  suffixes for auto-created); hardened name-as-key (no rename, no homonyms, punts the
  problem to 0002).
- **F2 — One shared NPC resolver, reject-with-candidates (Decided; refined by advisor
  review).** The LLM speaks names. A single resolver maps name → UUID by scanning
  `world_state["npcs"]` over each record's `slug` + `name` (small dict, no maintained
  index), scoped to living NPCs first; on ambiguity it rejects with disambiguated
  candidates (e.g. "Guard (Royal Palace)"). It shares only the reject-with-candidates
  **shape** with 0008 F7 — *not* the function or data source: `move_to` resolves place
  nodes via the **baseline** alias index (F13), which the updater handlers don't even
  receive; NPC resolution lives entirely in the overlay. Candidate labels are enriched
  with place names only in the tool layer (where the baseline is available);
  deterministic paths (updater handlers) resolve without labels. **Every** name-keyed
  path migrates to it — see the S1 atomic-conversion list in §4.
- **F3 — `name` becomes mutable (Decided; revises B2's old rationale).** With UUID keys
  the name is data, not identity: rename = identity reveal ("the hooded stranger" →
  "Malakar"), same record, same psychology, same history. Tool wording must frame rename
  as reveal, not re-cast. Rejected: keeping `name` blacklisted (forces a duplicate NPC
  on the reveal — a common fantasy beat — losing psychology and history).
- **F4 — Migration rung v6→v7 (Decided; refined by advisor review).** One rung, in
  order: **backfill `name` from the old dict key first** (instantiated records don't
  store a `name` field today — `world_instantiation.py:87` keys by it but never writes
  it inside; miss this and rekeyed records lose their display name), then rekey `npcs`
  by uuid4, fold descriptive fields into `traits` (G1), add `lifecycle="alive"` +
  `condition=None`, defensive `is_dead`/`status` lift (nothing writes them today), drop
  them. Instantiation itself starts writing `"name"` into the record. Pre-1.0, dev
  saves wiped (J2 precedent) — the rung is defensive normalization.

**TODO (F):** disambiguation-label format when the parent place has no name; resolver
behavior when *only* dead/removed NPCs match (candidates should say so).

### G. Record shape — typed engine contract + world-defined traits *(new group, 2026-07-07)*

- **G1 — Hybrid record (Decided).** A typed Pydantic model owns the **engine contract**:
  `slug`, `name`, `lifecycle`, `condition`, `location`, `faction`, `psychology` (0005),
  `met_player` (0005), `last_interactions`. Descriptive fields live in **`traits`**, a
  dict whose keys are declared by the world in a new **`npc_fields`** block of
  `taxonomy.yaml` (same pattern as 0005 psychology axes: world-defined, bundled default,
  tier-3 validation). Rejected: fully-fixed typed set (worlds can't add "honor_code" /
  "clan" — anti-P0); dedicated `npc_taxonomy.yaml` file (psychology already lives in
  `taxonomy.yaml`; two files for one domain).
- **G2 — Bundled default `npc_fields` (Decided).** `role`, `appearance`, `personality`,
  `motivation`, `background`, `ideal`, `bond`, `flaw`, `mannerisms`, `secret`,
  `dreads`. `dreads` **renames** the old `fear` descriptive field — `fear` is already a
  psychology **axis** (number); an identically-named string trait in the same record
  and prompt is ambiguous for the LLM.
- **G3 — Per-trait routing flag (Decided).** Every trait is always rendered in the
  **`npc_director` prompt** (the NPC playing itself). Each `npc_fields` entry carries a
  boolean **`scene`** (default `false`): when `true`, the trait is *additionally*
  rendered in the DM's `<npcs_present>` scene block. Bundled: `role` and `appearance`
  are `scene: true` (the DM narrates what the player sees), the rest `false`.
  `condition` is an engine field and is always in scene. Token guard: scene traits fall
  under the existing `<scene>` hard token cap (0008). Rejected: all-traits-to-director-
  only (the DM can't narrate appearance); all-traits-to-both (per-turn token bloat on
  BYOAK).
- **G4 — Flat authoring (Decided).** `npcs/*.yaml` stays flat (`role:` at top level, as
  today); the loader folds declared descriptive keys into `traits`, tier-3-validated
  against `npc_fields` (unknown key = validation error, like an unknown psychology
  axis). Filename stays the slug (0008 convention).
- **G5 — Editor prune-on-removal (Decided 2026-07-08).** Removing an `npc_field` from
  the taxonomy prunes its value from every authored NPC in the same save, behind a UI
  confirm showing the affected count. Tier-3 validation stays strict — an *imported*
  world carrying orphans still rejects (the editor's "no broken links possible"
  guarantee). This inherits and fixes a **live 0005 bug**: the editor iterates only
  current axes (`forms-collections.tsx:220`), so removing a psychology axis leaves its
  stale seed on authored NPCs and tier-3 (`world_validator.py:107`) then rejects the
  world at save — the axis path gets the same prune in S3. Rejected: validator
  strip-with-warning (silent data loss at load; hollows out referential integrity).

### A. NPC status model — lifecycle / condition *(revised 2026-07-07)*

- **A1 — Two orthogonal fields (Decided, 2026-06-21).** `lifecycle` (closed enum
  `{alive, dead, removed}`) + `condition` (transient physical/behavioural descriptor).
  Rejected: single mixed enum; `list[str]` of states.
- **A2 — `lifecycle` is the single source of truth (Decided).** The pre-hook's redundant
  `is_dead` OR `status` read collapses to `lifecycle` only; migration is defensive (F4).
- **A3 — Write ownership (Decided; the writer now exists — see H).** `lifecycle` is
  **engine-owned**: `update_npc` rejects it; the on-screen writer is the HP-≤-0 hook
  (H1), removal/re-entry are semantic tools (H3), off-screen is the 0006 Director.
  `condition` is DM-writable via `update_npc`; engine systems may also set it (no
  engine `condition` writer is built now — TODO).
- **A4 — `condition` is free-form text, length-capped (Decided, 2026-07-07).** Free
  string (e.g. "ferita al braccio, diffidente"), max chars in `saga.config.yaml`
  (std 14). No engine code branches on the *value* of `condition` — only on
  `lifecycle` — so a closed vocabulary adds tool-error friction without gain, and
  combinations ("injured AND fleeing") stay representable. No duration/tick now; the
  0008-G3 timed-overlay shape remains a noted future alignment. Rejected: engine enum
  (anti-P0); world-defined vocabulary (transient + combinatorial flavor — a closed list
  under-represents or explodes; extra editor surface).
- **A5 — Surfacing (Decided, 2026-07-07).** `condition` renders as a line in
  `<npcs_present>` next to the salient psychology axes (0005) and the `scene: true`
  traits (G3). `lifecycle` is never rendered — dead/removed NPCs are filtered from the
  scene and gated by the pre-hook.

### H. Lifecycle writers *(new group, 2026-07-07 — closes the old A3/C TODOs)*

- **H1 — Death is engine-written at HP ≤ 0, deterministically (Decided).** In the
  `combat_damage` handler: when an enemy combatant drops to ≤ 0 HP it is marked
  `defeated`; if its name resolves (F2) to a **unique living NPC at the current
  location**, that NPC gets `lifecycle="dead"`. On ambiguity or no match: defeated
  only, no NPC write, logged. No LLM decides the irreversible transition — aligned
  with D&D (dead = HP 0), with ADR 0003's server-side-damage direction, and
  hallucination-proof. Rejected: a `kill_npc` DM tool, even pre-hook-guarded (a
  mechanical pre-hook validates existence/presence, not narrative truth — residual
  hallucination on an irreversible write).
- **H2 — `kill_npc` engine-checked tool (Decided 2026-07-08 — reverses the 2026-07-07
  "no kill tool" call, on advisor evidence).** What flipped it: (i) `StartCombat.enemies`
  are free `{name, hp}` dicts (`tools_combat.py:14`) — mooks that rarely resolve to
  registered NPCs, so the HP-≤-0 writer alone covers little; (ii) the updater is a
  fire-path with no return channel — a DM narrating a death in prose leaves
  `lifecycle=alive` **silently**, the next turn's `<npcs_present>` re-lists the NPC and
  the DM contradicts its own narration. Silent desync is worse than visible
  hallucination. `kill_npc(name, cause)`: mechanical pre-hook — target exists, alive,
  resolves uniquely (F2), present at the current location; ambiguous/absent →
  reject-with-candidates. A pre-hook still cannot validate narrative truth: a
  hallucinated kill remains possible, but it is **visible in the fiction and bounded**
  — the owner accepts that trade over the silent desync. HP-≤-0 writer (H1) stays;
  `update_npc(lifecycle)` still rejects (A3).
- **H3 — `remove_npc` / `restore_npc` semantic tools (Decided).**
  `remove_npc(name, reason)`: alive→removed (departed merchant, exiled bandit).
  `restore_npc(name, location?)`: removed→alive (re-entry, C2). Mechanical pre-hook:
  target exists, correct source state; `dead` is terminal — restore on dead rejects.
  Reversible pair → hallucination is low-stakes and self-correcting. `update_npc`
  still never touches `lifecycle` (A3).

**TODO (H):** whether all-enemies-defeated should auto-end combat (today `end_combat`
is LLM-called — 0003 territory, boundary noted); engine `condition` writers (e.g.
combat → "injured").

### B. `update_npc` tool *(revised 2026-07-07)*

- **B1 — Excludes affect (Decided; reconciled with shipped 0005).** `update_npc` never
  writes `psychology` or `met_player` — those belong to `change_npc_psychology` and the
  0005 engine paths. Domain split: affect → 0005, facts → 0009, lifecycle → engine (H).
- **B2 — Exhaustive partition + test (Decided; contents now fixed).** Over the typed
  engine model (G1): **mutable** = `name` (F3), `condition`, `location`, `faction`, and
  every `traits.*` key by construction (traits are descriptive flavor); **immutable** =
  `slug`, `lifecycle`, `psychology`, `met_player`, `last_interactions`. A unit test
  asserts every Pydantic model field is in exactly one list and fails on any
  unclassified field (std 11) — the typed model is the canonical field set the
  2026-06-21 version said this test needed. Scope note (advisor): the test covers the
  engine model only; per-trait routing (`scene` flags) is world content and outside
  its guarantee.
- **B3 — Upsert, complementary to the pre-hook (Decided).** Create-if-missing + update;
  the pre-hook stays the reactive path (`invoke_npc` on an unknown name), `update_npc`
  the proactive one (introduce a fully-specified NPC before it speaks). Both go through
  the shared creation scaffold (D1).
- **B4 — Upsert typo guard: fuzzy reject-with-candidates (Decided 2026-07-08, closes
  the advisor's biggest hole).** A misspelling ("Gandolf" vs existing "Gandalf") is a
  resolver *miss*, not an ambiguity — without a guard the upsert silently creates a
  duplicate. Flow: resolve via F2 first; on miss, fuzzy-match (normalized similarity,
  threshold `npc.name_match_threshold` in `saga.config.yaml`, std 14) against existing
  `slug`+`name`; near-hit → **reject** listing the candidates and requiring an explicit
  `create: true` to force a genuinely new NPC with a similar name; clean miss → create
  directly (no friction on the legitimate path). Rejected: bare `create: true` flag
  alone (an LLM hallucinating the flag alongside the typo still duplicates; every
  legitimate create costs an extra round-trip); no guard (silent duplicates).

### C. Removed-NPC archive *(unchanged, mechanism now decided)*

- **C1 — No separate structure (Decided).** Removed NPCs stay in `world_state.npcs`,
  record intact, filtered from scene, gated by pre-hook.
- **C2 — `removed` and `dead` are orthogonal terminals (Decided).** `dead` irreversible;
  `removed` has re-entry — via `restore_npc` (H3), which closes this group's TODO.

### D. Auto-create interplay *(partially revised)*

- **D1 — Shared base scaffold (Decided).** Both creation paths (pre-hook and
  `update_npc` upsert) use one shared function: `name` + `lifecycle="alive"` +
  psychology axis defaults (0005) always present at birth; `condition` optional.
- **D2 — Detail levels × taxonomy defaults (Decided, 2026-07-07).** `minimal` = engine
  contract only (traits `{}`); `standard` = traits seeded with each `npc_fields`
  default; `rich` = same seeds + prompt guidance telling the npc_director to fill empty
  traits in character on first invocation (guidance, not schema). The three existing
  config values keep their meaning. Rejected: collapsing to two levels (breaking change
  on `npc_auto_create_detail` for marginal simplification).

### E. NPC `location` — **closed** *(2026-07-07)*

- **E1 — Resolved by 0008 J3.** `location` is a world-node UUID since 0008 S2
  (`world_instantiation.py:89`, `npc_prehook.py:31`). Nothing left to coordinate;
  `location` sits in the mutable whitelist (B2) and `update_npc` writes it through the
  0008 scoped place-resolution.

---

## 4. Sprint plan *(Decided, 2026-07-07)*

Mega-branch `adr/0009-npc-enrichment`; each sprint on a sub-branch merged into the ADR
branch; granular commits (one module + its tests per commit). Mirrors the 0005 cycle.

- **S1 — core**: UUID rekey + migration rung v7 (F1/F4); typed engine model (G1);
  `npc_fields` taxonomy block + bundled default + tier-3 validation (G1/G2/G4); shared
  resolver (F2); pre-hook cleanup (`lifecycle` only, drop `is_dead`) (A2); shared
  creation scaffold with the D2 levels (D1/D2) — which retires the hardcoded
  descriptive seeds incl. the residual `fear` trait (`npc_prehook.py:54-63`); B2
  exhaustiveness test. **Atomic-conversion rule (advisor findings 1-2): the rekey and
  the conversion of every name-keyed read/write land in this same sprint, or every
  dialogue turn mints ghost name-keyed records / the scene prints raw UUIDs.** Call
  sites: `npc_prehook.py`, `memory/updater.py:36` (`npc_psychology` setdefault),
  `dm_tools_executor.py:293/304`, `tools_world.py:181/185` (psychology tool),
  `npc_director.py:121`, `prompts/dm.py:26/147` (location filter + scene keys — keep
  rendering names while keyed by UUID). S3 adds only *new* rendering, no conversions.
- **S2 — mutation surface**: `update_npc` (upsert + partition + B4 fuzzy guard);
  `kill_npc`/`remove_npc`/`restore_npc` (H2/H3); HP-≤-0 death writer (H1); config
  knobs (`condition_max_chars`, `name_match_threshold` — std 14); tool descriptions
  (rename-as-reveal wording, F3).
- **S3 — surfaces**: `<npcs_present>` rendering (condition + scene-flagged traits +
  0005 salient axes) (A5/G3); `prompts/npc.py` full-traits rendering + rich-level fill
  guidance (G3/D2); world-editor `npc_fields` taxonomy section + traits-driven NPC form
  + prune-on-removal incl. the 0005 axis fix (G5); FE types + en/it strings.

Operational breakdown in §10.

---

## 5. Decided vs Open — quick index

**Decided:** F1–F4, G1–G5, A1–A5, H1–H3, B1–B4, C1–C2, D1–D2, E1 (closed), sprint plan
(§10). Advisor review (2026-07-08) folded: findings 1-2 → S1 atomic-conversion rule,
3 → B4, 4 → H2 reversal, 5-6 → F2 refinement, 7 → G5, 8-10 → D2/F4, 11 → B2 scope note.

**Open TODOs (implementation-time, no owner fork left):** disambiguation-label edge
cases (F, S1); all-defeated auto-end-combat + engine `condition` writers (H —
boundary/0003, revisit with playtest).

---

## 6. Rejected alternatives

- **Slug-as-key / hardened name-as-key** — rejected for runtime UUIDs (F1).
- **`name` immutable** — rejected; UUID keys make rename safe and narratively needed (F3).
- **Fully-typed fixed field set / dedicated `npc_taxonomy.yaml`** — rejected for the
  hybrid record + `npc_fields` in `taxonomy.yaml` (G1).
- **`fear` as a trait name** — rejected (collides with the 0005 `fear` axis) → `dreads` (G2).
- **All traits to npc_director only / all traits to both prompts** — rejected for the
  per-trait `scene` flag (G3).
- **Single overloaded `status` enum / `list[str]`; keeping `is_dead`** — rejected
  (A1/A2, 2026-06-21).
- **`condition` as engine enum or world-defined vocabulary** — rejected for free-form +
  cap (A4).
- **Engine-only death (no kill tool)** — adopted 2026-07-07, **reversed 2026-07-08** on
  advisor evidence (combat mooks rarely resolve to registered NPCs; prose-narrated
  deaths silently desync with no return channel) → engine-checked `kill_npc` (H2).
- **Bare `create: true` flag as the only upsert guard / no guard** — rejected for the
  fuzzy reject-with-candidates (B4).
- **Validator strip-with-warning on orphaned trait values** — rejected for editor
  prune-on-removal (G5).
- **`lifecycle` via `update_npc`; disposition via `update_npc`** — rejected (A3/B1).
- **Pure whitelist / pure blacklist** — rejected for the exhaustive partition + test (B2).
- **`update_npc` update-only / subsuming the pre-hook** — rejected for upsert +
  complementary (B3).
- **Separate `removed_npcs{}` store; removed-as-superset-of-dead** — rejected (C1/C2).
- **Per-path creation scaffolds** — rejected for the shared base (D1).

---

## 7. Consequences / risks

- **Positive:** NPC identity finally matches place identity (one convention per save);
  homonyms and renames become representable; NPC death stops being inert scaffolding
  and is hallucination-proof (deterministic HP ≤ 0); descriptive richness becomes world
  content (`npc_fields`) instead of engine schema, with prompt-token routing per trait
  (G3); the affect/facts/lifecycle write-domain split is enforced by partition + test;
  stable UUIDs pre-pave ADR 0002.
- **Trade-offs:** rung v7 rekey touches **every** name-keyed NPC surface, including the
  just-merged 0005 code (scene, psychology handler, npc_director) — mitigated by the
  S1 atomic-conversion rule (§4), the single shared resolver (F2), and the existing
  548-unit/129-FE suites; a silent NON-death is possible when the dying combatant's
  name is ambiguous at the location (H1 logs it — accepted over guessing, and the DM
  now has `kill_npc` to persist the death explicitly); `dead` stays terminal, so a
  hallucinated `kill_npc` is permanent — accepted as visible-and-bounded vs the silent
  desync of having no tool (H2).
- **Risks:** upsert duplicates now bounded by the B4 fuzzy guard (threshold tuning is a
  config knob, may need playtest calibration); prompt-token growth if worlds flag too
  many traits `scene: true` (bounded by the 0008 scene cap); fuzzy threshold too
  aggressive could reject legitimate new NPCs with similar names (`create: true`
  escape hatch exists).

---

## 8. Relationship to other ADRs

- **ADR 0002 (relationship graph)** — out of scope; runtime UUIDs give it stable
  entity references for free.
- **ADR 0003 (deterministic resolution)** — H1 aligns with its server-side-damage
  direction; all-defeated auto-end-combat is its territory.
- **ADR 0005 (multi-axis psychology)** — affect stays exclusively 0005's
  (`psychology`/`met_player` blacklisted); its name-keyed surfaces migrate to the F2
  resolver in S1; `dreads` renamed to avoid the `fear` axis collision.
- **ADR 0006 (AI Director)** — off-screen `lifecycle` writes through its queue; causes
  of off-screen death decided there.
- **ADR 0007 (Voyage directions)** — parent ADR.
- **ADR 0008 (world model)** — identity mirrors its slug→UUID instantiation (F1), the
  resolver mirrors F7, `npc_fields` follows its P0 world-defined-vocabulary pattern,
  `location` closed by its J3; `condition` may later adopt its G3 timed-overlay shape.

## 9. Notes / sources

Source: `scratch/research/voyage.md` §3.5. Decisions from the 2026-06-21 and 2026-07-07
design interviews (all calls by the project owner), grounded in the live post-0005/0008
code. An external advisor review (Opus, 2026-07-08, 11 findings) attacked the S0
decisions against the code; all findings are folded (see the §5 index) — including one
reversal (H2) and two hardened decisions (B4, G5) confirmed by the owner.

---

## 10. Operational plan

Follows the 0005/0008 cycle discipline: mega-branch `adr/0009-npc-enrichment` (created
at S0); each sprint on a sub-branch (`0009-s1`, `0009-s2`, `0009-s3`) merged into the
ADR branch with a merge commit; single PR to `main` after the full cycle + manual
playtest. Per sprint: `make test-infra-up` → failing test first (std 1/11) →
implementation → refactor; granular commits (one module + its tests per commit, std
10); a `CHANGELOG.md [Unreleased] ### Internal` entry lands with each sprint's final
commit; exit gate = unit + integration/playtest BE green, FE suite green, mypy/ruff
clean.

### S1 — core (pure backend; the atomic rekey)

Commit-level units, in dependency order:

1. `npc_fields` block in the taxonomy meta-schema + bundled default (G2, `dreads`) +
   tier-3 validation of authored flat fields → `traits` (G1/G4) + example-world update.
2. Typed NPC engine model + B2 partition (two frozensets on the model) + the
   exhaustiveness test.
3. NPC resolver (F2): scan of `world_state["npcs"]` over `slug`+`name`, living-first
   scoping, reject-with-candidates; unit-tested standalone (homonyms, dead-only
   matches, empty).
4. Instantiation writes `name` into the record + rekeys by uuid4; migration rung v6→v7
   (F4 order: backfill `name` → rekey → fold `traits` → lifecycle/condition →
   defensive `is_dead` lift).
5. **Same-commit-series conversion of every name-keyed call site** (advisor findings
   1-2; the sprint is not mergeable in between): `npc_prehook.py` (also: `lifecycle`
   as the only gate, A2), `memory/updater.py:36`, `dm_tools_executor.py:293/304`,
   `tools_world.py:181/185`, `npc_director.py:121`, `prompts/dm.py:26/147`. Regression
   test: a full dialogue turn on a rekeyed save mints **zero** new NPC keys and the
   scene renders names, not UUIDs.
6. Shared creation scaffold (D1) with the D2 levels (minimal/standard/rich seeded from
   taxonomy defaults — retires the hardcoded `_create_npc_profile` fields incl. the
   residual `fear` seed).

### S2 — mutation surface (tools + writers)

1. `update_npc`: upsert through the scaffold, partition enforcement (whitelist/
   blacklist rejects with the field lists as candidates, std 13), B4 fuzzy guard +
   `create: true` escape hatch.
2. `kill_npc` / `remove_npc` / `restore_npc` (H2/H3): mechanical pre-hook guards
   (exists / alive / unique / present; `dead` terminal), `narrative_instruction`-style
   result strings.
3. HP-≤-0 death writer in `combat_damage` (H1): `defeated` flag + unique-living-at-
   location resolve → `lifecycle="dead"`; ambiguous → log-only. Integration test with
   a registered NPC as combatant and with a mook.
4. Config: `npc.condition_max_chars`, `npc.name_match_threshold` in `saga.config.yaml`
   (std 14) + `condition` length enforcement in `update_npc`.

### S3 — surfaces (prompts + editor)

1. `<npcs_present>`: `condition` + `scene: true` traits next to the 0005 salient axes
   (under the 0008 scene token cap).
2. `prompts/npc.py`: full-traits rendering + the rich-level "fill empty traits in
   character" guidance (D2). Also fix a pre-existing 0008 leftover: the prompt renders
   `Location: {location}` — a raw node UUID since J3; resolve it to the place name
   from the baseline (or drop the line).
3. Editor: `npc_fields` section in the taxonomy form (add/rename/remove, `scene` flag,
   defaults; pre-0009 worlds get a "customize" seed of the bundled default, like 0005
   axes) + prune-on-removal with UI confirm (G5) **including the 0005 axis fix**.
4. Editor: NPC form driven by the world's `npc_fields` (replaces the fixed field set);
   `EditableWorld` types.
5. FE tests + en/it strings; export/import round-trip test with custom `npc_fields`.

### After the cycle

Manual playtest in a clean-context chat (homonym NPCs, rename-as-reveal, a kill + a
remove/restore, typo'd `update_npc`, custom `npc_field` in the editor), bugs fixed on
the ADR branch, then the single PR to `main` — same close-out as 0005/0008.
