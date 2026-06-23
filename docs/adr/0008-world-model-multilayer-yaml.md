# ADR 0008 — World model: multi-layer, file-authored worlds with a deterministic spatial graph

- **Status**: Proposed (direction + design decisions fixed via the 2026-06-15 design
  interview; **hardened by a competitive/online research pass + adversarial validation**
  on 2026-06-15 — see `scratch/research/adr0008_research.md`. Open design TODOs remain
  before this can move to Accepted; may still be revised.)
- **Date**: 2026-06-15
- **Context items**: Voyage analysis (`scratch/research/voyage.md`); research pass
  (`scratch/research/adr0008_research.md`); spun off from ADR 0007. Decisions come from a
  structured design interview (all choices by the project owner) and were then validated
  against prior art (CK3, The One Ring 2e, Unity/Godot/Bethesda, Foundry VTT, NetworkX,
  Naismith's rule, and 6 OSS AI-RPG engines).
- **Scope note**: this ADR fixes **what the world model IS at campaign start** — a
  detailed, deterministic, file-authored snapshot — plus the spatial/travel rules and the
  authoring surface. It deliberately stops at the **static starting photograph of the
  world**. The *engine that makes the world evolve* is ADR 0006 (Director); the *rich NPC
  model* is ADR 0009. This ADR is intentionally exhaustive so the eventual implementation
  (split into sprints **later, not here**) needs no second analysis. Items marked **TODO**
  or **Open assumption** are design decisions consciously deferred to implementation time.

---

## 1. Context

Today SAGA's world is a **flat dict** in `world_state["locations"]` — each location is a
node with a `description` and a `connections[]` list of names, plus a single
`meta.current_location` string (`backend/app/memory/world_state.py`,
`backend/app/ai/tools/tools_world.py::MoveTo`, scene rendering in
`backend/app/ai/prompts/dm.py`). NPCs carry a flat `location: str`. Worlds are seeded
from `templates/*/template.yaml` via `campaign_service.build_initial_world_state` into
the campaign `world_state` JSONB (with a `schema_version` migration system, currently
v4). The turn loop replaces the whole column each turn (`turns.py`:
`campaign.world_state = new_world_state`). There is **no spatial hierarchy, no
coordinates, no travel distance/time**, and no separation between a reusable authored
world and a per-campaign save.

The Voyage analysis (ADR 0007) showed a competitor that independently arrived at a
**multi-level hierarchy** with canonical **coordinates** and **travel time in turns**,
representing a world as a **multi-file artifact** edited like a codebase
("multi-file world edits", `[📊 PAYLOAD]`-verified). This matches the authoring
experience SAGA wants: detailed, layered, editor-authored, deterministic, data-sovereign
worlds. Evidence caveat: Voyage's hierarchy/tool names are `[💬 NARRATOR]`-level; the
research pass confirmed that **most SAGA decisions stand on independent prior art**, and
the one most load-bearing on Voyage (multi-file world) is the `[📊 PAYLOAD]`-verified one.

---

## 2. Scope & boundaries

**In scope:** the world as a layered, file-authored asset; the node/hierarchy model; the
spatial/coordinate model; the travel/movement rules; the per-node parameter model; the
**authored seeds** for a living world (faction agendas, economy, status overlay schema);
light world-placed items; the in-game world editor; and integration points (`move_to`,
`<scene>`, runtime persistence).

**Out of scope (other ADRs):**
- **The simulation engine** moving the world off-screen over elapsed game-time → **ADR
  0006 (Director)**. This ADR only *authors the potential energy* and *persists deltas*.
- **The rich NPC model** → **ADR 0009**. **This ADR excludes NPCs.**
- **Per-turn state reconciliation** (state-audit) → **ADR 0007 §1**.
- **A full item catalog** → a future ADR. Only *light* world-placed loot/stock here.

**Framing:** ADR 0008 = the **detailed, deterministic starting photograph** of the
world. Static richness now; life later.

---

## 3. Decisions

> Legend: **Decided** = settled in the interview/validation. **Refined** = hardened by
> the research pass. **TODO / Open assumption** = deferred to implementation.

### A. Hierarchy & node model

- **A1 — Recursive typed node (Decided).** The world is a tree of a single node type
  carrying a `kind`, with **variable depth** and **skippable levels** (a lone building in
  the wilderness can be a `site` directly).
- **A1b — `max_depth` hard cap (Refined).** Variable depth gets a hard cap in
  `saga.config.yaml` (spirit of std 19 / no open-ended structures); tree-walk validation
  and rendering are bounded.
- **A2 — Recommended `kind` set (Decided as starting taxonomy; final enum is TODO A-i).**
  - **Map-scale (carry coordinates):** `world` → `region` → `area` (optional) → `site`.
  - **Interior (adjacency graph, no coordinates):** `building` → `room`.
- **A3 — Coordinate boundary rule (Decided).** A node is a **map node** (has coordinates)
  until you "enter" a structure; from there down it is **interior** (an adjacency graph).
- **A3b — Explicit `scale: outdoor|interior` flag (Refined; resolves old TODO A-ii).**
  The map-vs-interior nature is an **explicit flag on the node**, NOT derived from `kind`
  alone, because `building` can be either (isolated tower = outdoor map node; house in a
  city = interior). Coordinates are required iff `scale == outdoor`.
- **A4 — Local frames for authoring + a composed GLOBAL coordinate transform (Decided —
  GLOBAL chosen over the "authored-edges-only" alternative).** Each map-scale parent
  defines the local coordinate space of its **direct children** (nested maps: city map =
  city's children in its local frame; region map = region's sites in the region frame —
  **zero duplication**, no separate map artifact). **In addition, a global world
  transform is composed at load** (`global = parent_offset + child_local * parent_scale`,
  recursively) so a node's world-space position is always defined. This makes
  **cross-region coordinate distance computable** (needed by the travel engine for the
  default travel-time, F-ii) and supports a single zoomed-out world map. Rationale for
  choosing GLOBAL: the owner wants a real, deterministic, distance-aware world map; the
  global frame removes the A4-vs-F4 contradiction the validator found.
- **A5 — Multi-world readiness (Decided).** Single `world` root for v1, but roots are a
  **list** in code (length 1 now) → "add a world/dimension" is later a single action with
  **no schema refactor**. Inter-world travel (portals) is **deferred**.
- **A6 — Id duality: authored slugs → runtime UUIDs (Refined).** Authored YAML uses
  **human-readable slugs** (`id`, `parent_id`, and edge endpoints in `edges/` all
  reference slugs — clean diffs, hand-traceable). At instantiation each node gets a
  **stable runtime UUID** (like Bethesda FormIDs); the slug→UUID map is built during
  instantiation, and the **save (`world_baseline`/`world_overlay`) and the travel graph
  reference UUIDs only**, never display names — renames in the World asset must not break
  a frozen save's references.

**TODOs (A):**
- **TODO A-i:** finalize the `kind` enum (closed enum required by the Pydantic
  discriminated union, E1); decide whether `area` is kept or merged.
- **TODO A-ii:** the global-transform composition details (offset/scale per level) and
  how it interacts with per-level `coordinate_scale` (B-i).

### B. Coordinates & spatial model

- **B1 — Hybrid coordinates (Decided).** Coordinates at map levels; adjacency for
  interiors.
- **B2 — 2D `(x, y)` (Decided); per-level scale + global transform (Refined).** Each
  map-scale parent declares a `coordinate_scale` (e.g. region: 1 unit ≈ 10 km; city:
  1 unit ≈ 10 m); the global transform (A4) composes these. Exact unit model is **TODO
  B-i** (a hard prerequisite for the travel-time formula, F-ii).
- **B3 — No Z axis (Decided).** Elevation is **not** a coordinate. `elevation_m` (meters,
  absolute) + `terrain` (closed enum: road/trail/wilderness/forest/swamp/mountain/desert/
  arctic/coastal) are node/edge attributes feeding the travel-time formula (Naismith,
  F-ii) and flavor.

**TODOs (B):**
- **TODO B-i:** the coordinate-scale/unit system (`units_per_km` per level) and frontend
  map rendering (prior art: Leaflet `CRS.Simple` per-level image overlays + bounds +
  drill-down; or Pixi.js).
- **TODO B-ii:** finalize the `terrain` vocabulary and `elevation_m` ranges.

### C. World as a reusable asset vs the campaign save

- **C1 — Asset/save split (Decided).** A **World** is a reusable authored asset (a
  per-entity YAML tree, §D) in a **world library in the game home**. A **Campaign** is a
  **save** instantiated from a World; at runtime the game reads/writes only the save
  state, never the World YAML. (Prior art: Unity ScriptableObject→Instantiate, Godot
  PackedScene, Bethesda ESM→ESS.)
- **C2 — N independent campaigns per World (Decided).**
- **C3 — Frozen saves (Decided).** Editing a World after instantiation does **not** affect
  existing saves. **C3b (Refined):** the save header stamps `source_world_id` +
  `world_version_at_instantiation` at creation (cheap; keeps C3, lets a save be
  identified, enables a future opt-in re-sync without refactor).
- **C4 — Templates replaced by Worlds (Decided).** `templates/` is **removed**; ship **a
  single** example World.
- **C5 — Scenario/opening as a thin block in the World (Decided).** A small optional
  `scenario` section (opening narration + initial quests + DM persona) makes a World
  playable out of the box; multi-scenario-per-world is **deferred** (reachable without
  refactor).
- **C6 — Export/import as a zip (Decided).** Editor "export world" → zip of the YAML
  tree; import = upload zip → validate (before placement) → place in the library as if
  editor-created. The save is exported separately as JSON.
- **C7 — Runtime persistence split: `world_baseline` vs `world_overlay` (Decided —
  replaces the earlier "single column, duplication accepted").** The instantiated world
  is stored in **two JSONB stores**: `world_baseline` (the static authored tree, written
  **once** at instantiation, never touched by the turn loop) and `world_overlay` (the G3
  status overlay + all runtime deltas + clock/combat/narrative, written **every turn**).
  The turn loop reads both and writes **only the overlay**. Rationale: the validator
  showed that today's whole-column rewrite (`turns.py`) plus a large authored tree causes
  PostgreSQL **TOAST write amplification** (the entire compressed value + WAL rewritten
  every turn, proportional to world size). Splitting keeps the static content out of the
  per-turn write path. This stays consistent with D1 (JSONB owns the runtime).

**TODOs (C):**
- **TODO C-i:** the `scenario` block schema and how it seeds the `campaign` row.
- **TODO C-ii:** world-library on-disk layout in the game home; World slug/versioning.
- **TODO C-iii:** export-zip structure + import validation/placement.
- **TODO C-iv:** exact column/shape for `world_baseline` / `world_overlay` and how
  reads merge them (overlay overrides baseline).

### D. Source of truth & file organization

- **D1 — Files seed → JSONB owns the runtime (Decided).** Authored YAML **instantiates**
  the world into JSONB (`world_baseline` + initial `world_overlay`) at campaign creation;
  at runtime only JSONB is read/written. (Rejected: files-as-runtime-truth + lazy-load
  deltas — dual-source reconciliation not justified.)
- **D2 — One file per entity, directory tree (Option B) (Decided).** One YAML per region,
  per site, per building, etc. Clean diffs, single-entity overrides; "file sprawl" is a
  non-issue because users author via the editor, not by hand.
- **D2b — Edges live in a top-level `edges/` collection, NOT in entity files (Refined;
  resolves the D2-vs-F5 contradiction).** Travel edges cross the containment tree, so
  they cannot live inside an entity's file. They are a first-class top-level collection
  (`edges/…yaml`) referencing endpoint ids. (Prior art: NavMesh/graph-DB separate
  connectivity from scene hierarchy.)
- **D2c — The character rulebook is a sibling top-level collection (Noted 2026-06-23, per ADR
  0010-A2).** The World tree also carries a top-level `rulebook/` collection (attributes, skills,
  and trait/ability categories-as-folders) — the per-world character rules — alongside
  `regions/`, `edges/`, and `scenario.yaml`. Its **shape** is owned by **ADR 0010**; 0008 owns
  only that it is an authored, instantiated-once asset (a **frozen `rulebook` JSONB store** at
  runtime, mirroring the `world_baseline` lifecycle, C7), loaded by the same
  directory-convention loader (D3, category = folder).
- **D3 — Directory-convention loader, no manifest (Decided).** Folder structure + per-file
  `id` + `parent_id` (for the skip case) resolve the hierarchy; loader walks the tree
  (`rglob`), builds an `{id: node}` registry, and **eagerly detects duplicate ids**.
  **D3b (Refined):** the convention is documented precisely (TODO D-i) and a **startup
  integrity check** compares expected-convention vs actual files (so the editor and
  loader never drift silently). (Prior art: Jekyll/Hugo/dbt/Kustomize.)
- **D4 — The world library is a git repository (Refined; see I5).** Enables atomic
  multi-file commits + free audit history; aligns with Data Sovereignty.

**TODOs (D):**
- **TODO D-i:** exact directory layout + naming convention (incl. `edges/`, `factions/`,
  `encounters/`, `scenario.yaml`).
- **TODO D-ii:** id/reference resolution rules and the `parent_id` skip semantics.
- **TODO D-iii:** instantiation mapping (YAML tree → `world_baseline` JSONB), UUID
  assignment (A6), and the new `schema_version`.

### E. Per-node parameter model

- **E1 — Typed core + bounded free bag, via a Pydantic discriminated union (Decided +
  Refined).** Each `kind` is its own Pydantic submodel (discriminated on `kind`) with its
  own required fields and `extra="forbid"` on the core; plus
  `params: dict[str, int|float|str|bool]` — a **closed bag of primitives** for custom
  knobs (the "middle ground" the owner asked for). (Prior art: Foundry VTT `system.*`
  typed vs `flags.*` open.)
- **E2 — Mandatory-by-kind validation (Decided).** Required fields per kind, enforced by
  Pydantic **at instantiation** (not only at load) to prevent the schema-drift seen in
  competitor repos.
- **E3 — Engine-computed vs LLM-flavor partition (Decided — resolves the "percentage of
  what?" fragility).** The parameter catalog (E-i) is split into:
  - **(a) Engine-computed fields** — anything the engine or the Director (0006) computes
    on (economy drain/regen, encounter difficulty, travel) **must** have a defined formula
    + reference quantity in `saga.config.yaml`. Absolute where needed (e.g. `population`).
  - **(b) LLM-flavor fields** — narrative/atmosphere descriptors; **percentages (0–100,
    `Field(ge=0,le=100)`) and qualitative scales are fine here.**
  - Numeric guardrails (recommended range + hard min/max, std 14) apply to both.

**TODOs (E):**
- **TODO E-i (major):** the per-kind parameter catalog, partitioned per E3. Prior art to
  draw from: NEQ `loca_schema.json` (`dangerLevel` enum, `dcChecks` "Skill DC N",
  `doors{lockDC,breakDC,locked}`, `traps{detect/disable/trigger DC}`, `monsters{min,max}`);
  open-tabletop-gm settlement (`population` abs, `wealth` enum, `lawAndOrder` 1–5); ai_rpg
  `baseLevel`. Depends on A-i.
- **TODO E-ii:** Pydantic models location (`backend/app/models/world.py`) + the
  referential-integrity validator (`backend/app/core/world_validator.py`).

### F. Travel & movement

- **F1 — Travel = a single narrated, clock-advancing action (Decided).** A "travel
  montage": DM narrates, clock advances by travel-time, optional route-dependent
  encounters interrupt. No multi-turn tedium. (Prior art: The One Ring 2e journeys.)
- **F2 — No instant fast-travel, ever (Decided).** Travel always costs game-time.
- **F3 — Route-graph as the travel source of truth; coordinates for the map + default
  distance (Decided).** Reachability/travel-time governed by an explicit **edge graph**;
  coordinates (now global, A4) give a **default** distance; authored edges win.
- **F4 — Edge schema (Decided shape; exact fields TODO F-i).** Each edge:
  `{id, from_id, to_id, mode (land|sea|mountain-pass|river|air), travel_time (authored, or
  computed default), terrain, encounter_table (ref), conditions[] (season/status/
  item-required), directed (bool)}`. (Prior art: ai_rpg `LocationExit`.)
- **F5 — Topology encodes real geography (Decided).** A sea ⇒ no direct land edge (route
  via `port → ship edge → port`); a mountain chain ⇒ a slow `mountain-pass` edge or a
  detour. The **travel graph is independent of the containment tree** (near-but-other-
  region sites can share a short edge).
- **F6 — Route-dependent encounters (Decided).** Encounters come from the traversed
  edge's encounter table.
- **F7 — `move_to` = simple name/id with SCOPED resolution; reject-with-candidates on
  ambiguity (Decided + Refined).** The DM passes a name/id; the engine resolves with
  **scoped precedence** (current interior → current site → current region → global). On a
  unique match: resolve. On ambiguity (every world has many "Tavern"/"Market"): **reject
  with a structured `{error: ambiguous_location, candidates:[…]}`** so the DM re-calls
  with the right one — **never guess silently** (silent wrong resolution = invisible world
  corruption). Local move (adjacent) vs travel (distant) is distinguished by whether a
  hierarchy boundary is crossed.
- **F8 — Invalid moves validated & rejected with a narratable reason (Decided).** Computed
  via the graph: unknown place / no land route (need a ship) / impassable now
  (season/status). (Prior art: NetworkX `has_path` + `subgraph_view` diffing.)
- **F9 — Travel-time ↔ clock; turns ≠ days (Decided).** `move_to` knows the cost; the
  clock advances via `advance_time`. **Elapsed game-time** (not turn count) feeds ADR
  0006's world evolution.

**TODOs (F):**
- **TODO F-i:** finalize the edge schema; edges live in `edges/` (D2b).
- **TODO F-ii:** the default travel-time formula — **Naismith/Scarf**
  (`equiv_distance = dist + 7.92·elevation_gain_m; time = equiv / base_speed`) with
  terrain multipliers (road .75 … swamp 2.0 … mountain 2.5) and mode speeds (foot 4,
  horse 7, ship 6 km/h), all in `saga.config.yaml`. **Blocked on B-i** (`units_per_km`).
  Authored `travel_time` always overrides.
- **TODO F-iii:** encounter-table format — two layers (per-edge check freq/DC + weighted
  table, `2d8` civilized / `d20` wild); `once:true` entries persist a
  `consumed_encounters[]` per edge in `world_overlay`; resolution integrates the existing
  `request_dice` / `start_combat`.
- **TODO F-iv:** the scoped-resolution + ambiguity protocol details (alias index built at
  load; ids are UUIDs, A6).
- **TODO F-v:** pathfinding/runtime — **NetworkX `DiGraph`** (one-way via `directed`) +
  `subgraph_view(filter_edge=…)` for mode/condition filtering; graph rebuilt from JSONB
  per request (50–200 nodes → microseconds); mid-journey interruption state held in
  `world_overlay.pending_travel`.

### G. Living-world seeds (authored here, simulated in ADR 0006)

- **G1 — Faction agendas (Decided).** Factions authored with **goals / rivals /
  resources** (fuel for the Director). **Refined schema** (prior art: ai_rpg `Faction`):
  `goals[]`, `relations: {faction_id: {status: allied|neutral|hostile|rival, notes}}`
  (rivals = a relation status, not a separate array), `reputation_tiers[{threshold, label,
  perks[], penalties[]}]`, `resources[]` (typed per E3, see G2).
- **G2 — Economy/resource seeds (Decided).** Settlements/factions author initial
  resources; the **simulation (drain/regen) is the Director's job** (0006). Per E3,
  engine-consumed resource fields carry a reference quantity + formula in config.
- **G3 — Structured per-node status overlay (Decided; lives in `world_overlay`).** Each
  node may hold a persistent status (`status`, `description`, `duration_minutes|null`,
  `applied_at`, `modifiers{field: delta}`) overriding the authored baseline. **G3b
  (Refined):** the overlay also carries **`edge_overrides`** (add/remove/modify edges) so
  a destroyed bridge actually removes an edge from the travel graph. (Prior art: ai_rpg
  `statusEffects[]` with duration/tick/expire — the validator called this the strongest
  design in the ADR.)

**TODOs (G):** G-i faction-schema finalization; G-ii economy-seed schema (types/units,
reference quantities); G-iii status-overlay + `edge_overrides` schema and the tick/expire
pass (coordinated with ADR 0006).

### H. World-placed items (light only)

- **H1 — Light authored loot/stock per node (Decided).** A light list of notable items /
  loot / shop stock per node. A full item catalog (definitions, properties, crafting) is a
  **future ADR**. Player inventory unchanged.

**TODO H:** the light loot/stock schema and its relation to `add_item`/`remove_item`.

### I. In-game world editor (authoring surface)

- **I1 — Manual structured UI; AI creator-agent deferred (Decided).** v1 writes validated
  YAML; a Voyage-style AI creator-agent is deferred (BYOAK cost; AI-generated worlds in
  the OSS repos accumulate schema drift needing reconciler passes).
- **I2 — v1 scope = create-world wizard + per-entity editing (Decided).**
- **I3 — Editor edits the World asset (home); gameplay changes the save (Decided).**
  In-session live world editing is deferred.
- **I4 — Validated references + atomicity (Decided).** Three-tier validation: (1) YAML
  parse, (2) Pydantic per-kind, (3) a **referential-integrity pass** over the full graph
  (cross-file refs can't be validated declaratively). The UI prevents broken refs **by
  construction** (id pickers, not free text).
- **I5 — Atomicity via git commits (Decided — chosen over temp-dir+journal).** The world
  library is a git repo (D4); each editor "save" validates then **commits** the changed
  files — a commit is atomic by definition, gives free audit history, and rollback is
  `git reset`. (Rejected alternative: temp-dir + per-file `os.replace` + commit journal +
  startup recovery — more code, no audit history; the filesystem is **not** natively
  atomic across multiple files, especially on Windows, so a plain multi-file write is
  unsafe.)

**TODOs (I):** I-i the exact validation rule set + git-commit flow (staging, message,
failure handling); I-ii the wizard/per-entity edit surface; I-iii the deferred AI
creator-agent's router/`AICallType` integration if/when built.

### J. Integration with the existing engine

- **J1 — Expanded `<scene>` block, spine-only default + hard token cap (Decided +
  Refined).** The scene block surfaces the hierarchy (breadcrumb `World > Region > Site >
  Building`, current node full detail, exits, travel options with time/mode/danger, node
  status). **Default is spine-only** (ancestor **names** only + current node full +
  immediate exits), with a hard `scene_context_max_tokens` cap in `saga.config.yaml` —
  richer verbosity is explicit opt-in. Rationale: on BYOAK the operator pays every
  context token every turn; "world always in full context" was ~500–1500 tok/turn
  uncontrolled. (Prior art: structured "you are here" blocks outperform prose for LLM
  navigation.)
- **J2 — No migration (Decided).** No old saves exist (test Docker data deleted). New
  campaigns only; the flat `locations` dict + `meta.current_location` string are removed.

**TODOs (J):** J-i exact `<scene>` rendering + config knobs (`max_breadcrumb_depth`,
`show_travel_options`, `max_travel_options`, `include_node_status`,
`description_max_chars`, `scene_context_max_tokens`); J-ii rework of `tools_world.MoveTo`,
the `dm.py` scene builder, `campaign_service.build_initial_world_state`, and the
world-state schema/migrations; J-iii how the NPC `location` field addresses the new
hierarchy (coordinated with ADR 0009).

---

## 4. Decided vs Open — quick index

**Decided/Refined:** A1, A1b, A2, A3, A3b, A4 (global transform), A5, A6, B1, B2, B3,
C1–C7 (C7 = baseline/overlay split), D1, D2, D2b, D3, D3b, D4, E1, E2, E3, F1–F9, G1, G2,
G3, G3b, H1, I1–I5, J1, J2.

**Open TODOs before Accepting (may still be revised):** A-i/ii, B-i/ii, C-i/ii/iii/iv,
D-i/ii/iii, **E-i (major: per-kind parameter catalog, partitioned per E3)**, E-ii,
F-i/ii/iii/iv/v, G-i/ii/iii, H, I-i/ii/iii, J-i/ii/iii.

**Single biggest open item: E-i** — depends on finalizing the `kind` enum (A-i); a
primary objective of the parameter-design pass (prior art catalogued in the research note).

---

## 5. Rejected alternatives

- **Fixed-depth/named hierarchy** — rejected for the recursive typed node (A1).
- **Coordinates everywhere / true 3D** — rejected (B1, B3); interiors are adjacency;
  elevation is an attribute (Naismith handles time).
- **Local-only frames with no global transform** — rejected (A4): made cross-region
  distance undefined; the owner wants a deterministic distance-aware world map.
- **Authored-edges-only (no coordinate default at all)** — considered as the A4 fix but
  rejected in favour of the global transform (keeps the coordinate-derived default usable
  cross-region).
- **Single `world_state` JSONB column** — rejected (C7): TOAST write amplification on
  every turn; replaced by baseline/overlay split.
- **Files-as-runtime-truth + lazy deltas** — rejected (D1).
- **Per-layer files (Option A) / manifest loader** — rejected (D2, D3).
- **Edges embedded in entity files** — rejected (D2b): they cross the tree.
- **Instant fast-travel / step-by-step multi-turn travel** — rejected (F1, F2).
- **Pure coordinate-geometry travel** — rejected (F3, F5).
- **Silent name resolution** — rejected (F7): reject-with-candidates instead.
- **AI-first editor / AI creator-agent in v1** — rejected (I1): BYOAK cost.
- **Temp-dir + journal atomic writes** — rejected (I5): git commits chosen.
- **Percentages as engine inputs** — rejected (E3): engine fields need formula+reference.
- **"World always in full context"** — rejected (J1): spine-only default + token cap.
- **Keeping `templates/` alongside Worlds** — rejected (C4).

---

## 6. Consequences / risks

- **Largest of the three Voyage spin-off refactors.** Touches the world persistence schema
  (now split baseline/overlay), templates→Worlds, `move_to`, a new travel system
  (NetworkX graph + Naismith time + encounter tables), the `<scene>` builder, and adds an
  editor + a git-backed world library.
- **Strong upside** for the "Living World" and "Data Sovereignty" pillars; pairs with ADR
  0006 (the Director moves the off-screen world this represents) and ADR 0007 §1.
- **Risks (with mitigations now in the decisions):** TOAST write amplification → C7
  split; cross-region distance → A4 global transform; cross-tree edges → D2b; multi-file
  atomicity → I5 git; name ambiguity → F7; false determinism of percentages → E3; BYOAK
  scene token cost → J1. Remaining big risk: E-i (large, balance-sensitive) → dedicated
  parameter-design pass.
- **New dependency:** NetworkX (pathfinding) — small, standard, fits the Python stack.

---

## 7. Relationship to other ADRs

- **ADR 0006 (AI Director)** — owns the simulation engine evolving the world over elapsed
  game-time; consumes the model, agendas, economy seeds, and status overlay (incl.
  `edge_overrides`) defined here. Not superseded.
- **ADR 0007 (Voyage directions)** — this is its spun-off "world model" item; §1
  (state-audit) reconciles state held here; the BYOAK lens drives I1 and J1.
- **ADR 0009 (NPC enrichment)** — owns NPCs (excluded here); J-iii coordinates the NPC
  address into this hierarchy.

## 8. Notes / sources

Sources: `scratch/research/voyage.md` (competitor analysis) and
`scratch/research/adr0008_research.md` (the 2026-06-15 research pass — 6 OSS engines +
online prior art + adversarial validation). Key prior art cited there: CK3 province
graph; The One Ring 2e journeys; Unity ScriptableObject / Godot PackedScene / Bethesda
ESM-ESS; Foundry VTT typed-vs-flags; NetworkX; Naismith's rule; ai_rpg, NeverEndingQuest,
open-tabletop-gm. Exhaustive per the owner's instruction; sprint breakdown deferred to
implementation time.
</content>
