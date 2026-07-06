# ADR 0008 — World model: multi-layer, file-authored worlds with a deterministic spatial graph

- **Status**: Proposed (direction + design decisions fixed via the 2026-06-15 design
  interview; **hardened by a competitive/online research pass + adversarial validation**
  on 2026-06-15 — see `scratch/research/adr0008_research.md`. **Implementation-planning
  interview 2026-07-06**: resolved J-iii (NPC interim addressing), added the read-only
  world map (B4), fixed the sprint split (§9). **Sprint 0 design pass 2026-07-06
  (same-day interview): closed every open TODO** — headline revision: **world-defined
  vocabularies (P0)** replace the fixed kind/terrain enums. Ready for Accepted on owner
  sign-off.)
- **Date**: 2026-06-15 (updated 2026-07-06)
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
  (split into sprints in §9) needs no second analysis. All formerly-open TODOs were
  closed in the 2026-07-06 Sprint 0 design pass.

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
> the research pass. **Revised/Resolved (S0)** = changed or closed in the 2026-07-06
> Sprint 0 design pass. No open TODOs remain.

### P0. World-defined vocabularies — the engine-contract pattern (Decided S0)

**No hardcoded taxonomy anywhere.** Kinds, terrains, travel modes, faction relation
labels are **authored per world** in `taxonomy.yaml` — free names, as many as the
creator wants. The engine contract: **each vocabulary entry carries the numeric or
structural fields the engine consumes** (`scale` on kinds, `travel_multiplier` on
terrains, `speed_kmh` on modes, `stance` on faction relations). **The engine reads the
numbers and flags, never the names.** SAGA owns only the **meta-schema** (the Pydantic
models that validate `taxonomy.yaml` itself) plus a **default taxonomy** shipped with
the example World that creators copy and adapt. This supersedes the fixed kind set (old
A2) and the fixed terrain enum (old B3), and replaces the per-kind discriminated union
(old E1) with meta-schema + dynamic validation.

### A. Hierarchy & node model

- **A1 — Recursive typed node (Decided).** The world is a tree of a single node type
  carrying a `kind`, with **variable depth** and **skippable levels** (a lone building in
  the wilderness can be a `site` directly).
- **A1b — `max_depth` hard cap (Refined).** Variable depth gets a hard cap in
  `saga.config.yaml` (spirit of std 19 / no open-ended structures); tree-walk validation
  and rendering are bounded.
- **A2 — Fully custom kinds via the world taxonomy (Revised S0; closes old TODO A-i).**
  Kinds are **not** a SAGA enum: each World declares its own in `taxonomy.yaml` — free
  names, **at least one**, each `{name, scale: outdoor|interior, params: [...]}` (per
  P0). The old recommended set (`world/region/area/site/building/room`) survives only as
  the **default taxonomy of the example World**. **Containment is free** — any kind may
  contain any kind; the only structural rules are (a) an `interior` node can never
  contain an `outdoor` node, and (b) the `max_depth` cap (A1b).
- **A3 — Coordinate boundary rule (Decided).** A node is a **map node** (has coordinates)
  until you "enter" a structure; from there down it is **interior** (an adjacency graph).
- **A3b — `scale` is a fixed property of the kind (Revised S0).** Declared once per kind
  in the taxonomy; every node inherits it — no per-node override, no ambiguity. The old
  "building can be either" concern dissolves: with unlimited custom kinds the creator
  defines `isolated_tower` (outdoor) and `house` (interior) as distinct kinds.
  Coordinates are required iff the kind's `scale == outdoor`.
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

- **A7 — Global transform = translation + uniform scale, no rotation (Resolved S0; closes
  old TODOs A-i/A-ii).** `global_km = parent_global_km + child_local × km_per_unit(parent)`,
  composed recursively at load and cached. Child frames never rotate — no use case for
  RPG maps, pure added complexity. A-i is closed by A2 (custom kinds).

### B. Coordinates & spatial model

- **B1 — Hybrid coordinates (Decided).** Coordinates at map levels; adjacency for
  interiors.
- **B2 — 2D `(x, y)`; canonical unit = km, `km_per_unit` per frame (Revised S0; closes
  old TODO B-i).** The world-root frame is **1 unit = 1 km**. Each outdoor parent
  declares `km_per_unit` for its children's local frame (region 10, city 0.01, …); the
  global transform (A4/A7) composes everything into km. Cross-region distance is real
  km; Naismith speeds are already km/h — no conversion layer.
- **B3 — No Z axis; custom terrain vocabulary (Revised S0 per P0; closes old TODO
  B-ii).** Elevation is **not** a coordinate: `elevation_m` (meters, absolute) is a
  node/edge attribute. `terrain` references the **world's own vocabulary**
  (`taxonomy.yaml: terrains: [{name, travel_multiplier}]` — names free, multiplier is
  the engine contract). Both are **optional with world defaults**
  (`taxonomy.yaml: defaults: {terrain, elevation_m}`) — authoring stays light, Naismith
  degrades gracefully.

- **B4 — Read-only world map in the play screen (Decided 2026-07-06).** The player gets a
  navigable, per-level map view (pan/zoom, drill-down along the hierarchy) rendered from
  the map-scale coordinates. **v1 rendering is parchment + pins**: a paper/parchment
  texture background with node pins and travel edges drawn over it — a map, not a bare
  graph — uniform across all levels. **Authored map images are deferred**: the node
  schema **reserves an optional `map_image` field now** (plus image-bounds calibration)
  so adding illustrated per-level maps later (Leaflet `CRS.Simple`-style image overlay +
  pins) is purely additive — no schema refactor, but no asset pipeline (binaries in the
  zip, image serving, bounds calibration) in this cycle. (Rejected for v1: authored image
  + parchment fallback — pulls the whole asset pipeline into an already-large cycle;
  image-only with hidden map tab — wizard-created worlds would have no map at all.)

Map-view drill-down/interaction details land with Sprint 4 (§9) — UI detail, not a
design TODO.

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

- **C8 — `scenario.yaml` schema (Resolved S0; closes old TODO C-i).**
  `opening: {narration, start_location (slug), time_of_day, weather}` +
  `initial_quests[]` (name/description/objectives) + `story_arcs[]`
  (name/trigger/description) + optional `dm_persona`. Instantiation seeds the campaign:
  `start_location` → player position UUID, quests seeded, narration = first message.
  Everything else the old `template.yaml` carried is **not** ported into scenario — it
  lives in the proper collections (`nodes/`, `factions/`, `npcs/`) or dies with
  `templates/` (C4).
- **C9 — Game home = `~/.saga/`, worlds in `~/.saga/worlds/` (Resolved S0; closes old
  TODO C-ii).** No game-home concept exists in the code today — this creates it.
  Overridable via `SAGA_HOME` env + a `saga.config.yaml` key; created lazily on first
  use; Docker mounts it as a volume. World identity/versioning: `world.yaml` carries
  the meta block (name, author, version, tags) — C3b stamps `version` into the save at
  instantiation. (Rejected: XDG per-OS paths — three paths to document/debug for a
  self-hosted tool; inside the install dir — update/reinstall endangers user worlds,
  against Data Sovereignty.)
- **C10 — Export/import mechanics (Resolved S0; closes old TODO C-iii).** Export = zip
  of the World directory as-is. Import = unzip to temp → full three-tier validation
  (I4) → **slug collision with the library rejects with a clear message** (user renames
  in the UI) → placed in the library → git init/commit (I5/I5b).
- **C11 — Column shapes (Resolved S0; closes old TODO C-iv).** New JSONB column
  `world_baseline` on `campaigns` — `{nodes (by UUID), edges, taxonomy, factions,
  encounters, scenario, slug_map}` — written once at instantiation. **The existing
  `world_state` column IS the overlay, no rename**: today's writers
  (npcs/quests/combat_state/clock) stay untouched; it gains `node_status`,
  `edge_overrides`, `player_position`, `consumed_encounters`, `pending_travel`. The
  merge lives in a **single accessor module** — every reader (scene builder, tools,
  combat) goes through it; no caller merges the two stores by hand (the ability-score
  mis-keying bug came from three divergent read conventions — never again).

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
- **D3 — Directory-convention loader; the directory tree IS the world tree (Revised
  S0).** A node with children = a **directory** containing `_node.yaml`; a leaf = a
  single file. **Directory position is the parent — `parent_id` is removed** (one
  source of truth; the old "skip case" needs no field: skipping levels is just nesting
  whatever kind under whatever kind, per A2 free containment). Loader walks the tree
  (`rglob`), builds a `{slug: node}` registry, **eagerly rejects duplicate slugs**.
  **D3b (Refined):** a **startup integrity check** compares expected-convention vs
  actual files (so the editor and loader never drift silently). (Prior art:
  Jekyll/Hugo/dbt/Kustomize.)
- **D3c — Filename IS the slug (Resolved S0; closes old TODO D-ii).** `karak.yaml` →
  slug `karak`; directory `taverna/` → slug `taverna` (its `_node.yaml` carries no id).
  No `id` field inside files — no id-vs-filename drift possible; rename = rename the
  file. Slugs are kebab-case, **globally unique within the World** (edges, scenario,
  and NPCs reference them cross-file). (Rejected: `id` field wins over filename —
  reintroduces exactly the drift D3b guards against.)
- **D4 — The world library is a git repository (Refined; see I5).** Enables atomic
  multi-file commits + free audit history; aligns with Data Sovereignty.

- **D5 — World directory layout (Resolved S0; closes old TODO D-i).**

  ```
  my_world/
    world.yaml       # root node + meta (name, author, version, tags)
    taxonomy.yaml    # kinds + terrains + travel_modes + defaults (P0)
    scenario.yaml    # C8
    rulebook/        # ADR 0010 (shape owned there)
    edges/           # D2b — outdoor travel edges
    factions/        # G1
    encounters/      # F-iii — encounter tables
    npcs/            # minimal flat records (D6)
    nodes/           # the world tree (D3): dirs + _node.yaml / leaf files
  ```

- **D6 — `npcs/` stays minimal, ADR 0009 owns the rich model (Resolved S0).** One file
  per NPC with **today's flat shape** (name, role, location — a node slug, → UUID at
  instantiation per J3 —, personality, motivation, secret, disposition, optional
  `faction` slug). Zero invention here; 0009 enriches the record later.
- **D7 — Instantiation mapping (Resolved S0; closes old TODO D-iii).** Walk the
  directory → registry → three-tier validation (I4) → assign a UUID per node/edge (A6)
  → write `world_baseline` (C11 shape, including the `slug_map` and an **alias index**
  slug+display-name → UUID for F7 resolution) → seed `world_state` from `scenario.yaml`
  (C8). The campaign `world_state` **`schema_version` bumps to v5** (new shape; no
  migration of old saves, J2).

### E. Per-node parameter model

- **E1 — Typed base + taxonomy-driven params, via meta-schema (Revised S0 per P0 —
  replaces the per-kind discriminated union).** Custom kinds make a static discriminated
  union impossible. Instead: **Pydantic validates the meta-schema** (`taxonomy.yaml`
  itself — `KindDef`, `TerrainDef`, `ModeDef`, `ParamDef{name, type, required, min,
  max}`) plus a **single generic `Node` model** for the SAGA-owned base fields
  (`extra="forbid"`); each node's `params` bag is then **validated dynamically against
  its kind's `ParamDef`s** (type/required/range). Params stay a closed bag of primitives
  (`int|float|str|bool`). (Prior art: Foundry VTT `system.*` typed vs `flags.*` open —
  now with the "system" part world-authored.)
- **E1b — Base node schema (Resolved S0).** SAGA-owned fields on every node: slug (from
  the filename, D3c), `kind`, `name`, `description`; outdoor-only: `position {x, y}`,
  optional `elevation_m` / `terrain` (defaults per B3), `km_per_unit` (if it has outdoor
  children), reserved `map_image` (B4); everything: `params {}` (per taxonomy),
  `items []` (H1), interior-only: `exits []` (F10).
- **E2 — Mandatory-by-kind validation (Decided).** Required params per kind (declared in
  the taxonomy), enforced **at instantiation** (not only at load) to prevent the
  schema-drift seen in competitor repos.
- **E3 — Engine-computed vs LLM-flavor partition (Decided; expressed via the P0 engine
  contract).** Engine-consumed values are the **numeric fields on vocabulary entries**
  (`travel_multiplier`, `speed_kmh`, `stance`, resource `quantity`, `elevation_m`) —
  always absolute numbers with ranges, never percentages-of-nothing. Custom `params` are
  LLM-flavor by definition (the engine ignores names it doesn't know); percentages and
  qualitative scales are fine there. Numeric guardrails (recommended range + hard
  min/max, std 14) apply to both.
- **E4 — Code locations (Resolved S0; closes old TODO E-ii).** Meta-schema + Node models
  in `backend/app/models/world.py`; the referential-integrity validator in
  `backend/app/core/world_validator.py`.

Old **TODO E-i** (the SAGA-owned per-kind parameter catalog) is **dissolved by P0**: no
central catalog exists — its replacement is (a) the meta-schema, (b) the engine
contract, (c) the **default taxonomy shipped with the example World** (the old A2 kind
set + the 9-terrain vocabulary + foot/horse/ship modes as copyable defaults).

### F. Travel & movement

- **F1 — Travel = a single narrated, clock-advancing action (Decided).** A "travel
  montage": DM narrates, clock advances by travel-time, optional route-dependent
  encounters interrupt. No multi-turn tedium. (Prior art: The One Ring 2e journeys.)
- **F2 — No instant fast-travel, ever (Decided).** Travel always costs game-time.
- **F3 — Route-graph as the travel source of truth; coordinates for the map + default
  distance (Decided).** Reachability/travel-time governed by an explicit **edge graph**;
  coordinates (now global, A4) give a **default** distance; authored edges win.
- **F4 — Edge schema (Resolved S0; closes old TODO F-i).** One YAML per edge in
  `edges/` (D2b), filename = edge slug (D3c). Fields: `from` / `to` (node slugs),
  `mode` (ref to the world's `travel_modes`, P0), `terrain` (ref, optional → default),
  `travel_time` (optional authored override), `distance_km` (optional override of the
  coordinate default), `encounter_table` (ref, optional), `encounter_chance` (optional),
  `conditions[]` (season/status/item-required), `directed` (bool, default false).
  Mode/terrain/table refs are validated in tier 3 (I4). (Prior art: ai_rpg
  `LocationExit`.)
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

- **F10 — Interior adjacency = `exits[]` on the room node (Resolved S0).** Interior
  nodes list `exits: [{to: slug, locked?, hidden?, notes?}]` toward sibling rooms —
  local and readable (open the room's file, see where it leads); a special
  `to: outside` exit surfaces at the parent node. `edges/` stays outdoor-only
  (cross-tree, D2b); the runtime graph (F13) merges both. (Rejected: interior adjacency
  in `edges/` — understanding one tavern means opening N edge files; adjacency matrix
  in the building file — rooms stop being self-contained, against D2.)
- **F11 — Travel-time formula split app/world (Resolved S0; closes old TODO F-ii).**
  **Naismith/Scarf** — `equiv_km = distance_km + elevation_coeff · elevation_gain_m;
  time = equiv_km / (speed_kmh · terrain_multiplier)`. The **formula + elevation
  coefficient (7.92) live in `saga.config.yaml`** (app-level physics); the **world
  customizes only its vocabularies** — terrain multipliers and mode speeds in
  `taxonomy.yaml` (P0). Distance default = global-km euclidean (A4/B2); authored
  `travel_time`/`distance_km` always override. (Rejected: per-world elevation
  coefficient — an obscure knob no creator understands; extreme
  multipliers/speeds already express "strange" worlds.)
- **F12 — Encounter tables in `encounters/`, per-table custom dice (Resolved S0; closes
  old TODO F-iii).** One YAML per table: `dice` (the table's own roll, e.g. `2d8` —
  nothing hardcoded, P0), `entries: [{roll: [min,max], type: event|combat, description,
  once?}]`. Edges reference `encounter_table` + `encounter_chance` (F4). `once: true`
  entries persist per-edge `consumed_encounters[]` in the overlay (C11); resolution
  integrates the existing `request_dice` / `start_combat`. (Rejected: tables inline in
  edges — zero reuse across edges sharing a road.)
- **F13 — Resolution + pathfinding runtime (Resolved S0; closes old TODOs F-iv/F-v).**
  The **alias index** (slug + display name → UUID) is built at instantiation into
  `world_baseline` (D7); scoped precedence walks **current node → its ancestors →
  global** (kind names are custom, so scoping is structural, not name-based). Runtime:
  **NetworkX `DiGraph`** (one-way via `directed`) + `subgraph_view(filter_edge=…)` for
  mode/condition filtering; graph rebuilt per request from baseline edges + interior
  `exits` + overlay `edge_overrides` (50–200 nodes → microseconds); mid-journey
  interruption state in `world_state.pending_travel`.

### G. Living-world seeds (authored here, simulated in ADR 0006)

- **G1 — Faction agendas; relations = numeric stance + custom label (Revised S0 per
  P0).** One YAML per faction in `factions/`: `name`, `description`, `goals[]`,
  `relations: {faction_slug: {stance: -10..+10, label: str}}` — **the engine/Director
  reads the stance number; the label is free narrative text** (no
  allied/neutral/hostile enum, consistent with P0),
  `reputation_tiers[{threshold, label, perks[], penalties[]}]`, `resources[]` (G2).
  (Prior art: ai_rpg `Faction`; rivals = a low stance, not a separate array.)
- **G2 — Economy/resource seeds, minimal shape (Resolved S0).** `resources:
  [{name, quantity, notes?}]` on factions/settlements — custom name + **absolute
  numeric quantity** (the seed the Director will consume) + optional notes. Drain/regen
  formulas are **ADR 0006's job**, not authored here; richer typing arrives there
  without refactor. (Rejected: `regen_rate`/units now — designs the Director's
  interface before the Director exists.)
- **G3 — Structured per-node status overlay (Decided; lives in `world_overlay`).** Each
  node may hold a persistent status (`status`, `description`, `duration_minutes|null`,
  `applied_at`, `modifiers{field: delta}`) overriding the authored baseline. **G3b
  (Refined):** the overlay also carries **`edge_overrides`** (add/remove/modify edges) so
  a destroyed bridge actually removes an edge from the travel graph. (Prior art: ai_rpg
  `statusEffects[]` with duration/tick/expire — the validator called this the strongest
  design in the ADR.)

- **G4 — Overlay shape + expiry (Resolved S0; closes old TODO G-iii).** Per-node status
  as already decided in G3 (`status`, `description`, `duration_minutes|null`,
  `applied_at`, `modifiers{field: delta}`) + `edge_overrides[]` (add/remove/modify,
  G3b), both in `world_state` (C11). **Expiry is applied on `advance_time`** (elapsed
  game-time, F9); richer per-tick simulation is coordinated with ADR 0006 when the
  Director lands.

### H. World-placed items (light only)

- **H1 — Light authored loot/stock per node (Decided; schema Resolved S0).**
  `items: [{name, qty?, notes?}]` on **any** node (rooms included) — pure text, the DM
  narrates them and uses the existing `add_item`/`remove_item`. A full item catalog
  (definitions, properties, crafting) is a **future ADR**; it will add an optional
  `ref` field, no refactor. Player inventory unchanged.

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
- **I5b — Repo-local git identity (Refined 2026-07-06).** `git commit` fails on a machine
  with no global `user.name`/`user.email` (the casual-installer audience). At library
  initialization SAGA sets a **repo-local** identity default (e.g. `SAGA World Editor
  <saga@localhost>`) — never touches the user's global git config.

- **I6 — Save flow + failure handling (Resolved S0; closes old TODO I-i).** Editor save
  = three-tier validation (I4) → write files → `git add` → commit with an auto message
  (`editor: update <slug>`); any failure after write = rollback via `git checkout`. The
  validation rule set is exactly I4's three tiers — no fourth invented.
- **I7 — v1 edit surface (Resolved S0; closes old TODO I-ii; built in Sprint 5).**
  Create-world wizard (name + meta, copies the **default taxonomy** for the creator to
  adapt, creates the root node) + per-entity forms driven by the taxonomy's `ParamDef`s;
  references via **id pickers only** (I4, broken refs prevented by construction).
- **I-iii (stays deferred):** the AI creator-agent's router/`AICallType` integration
  if/when built (I1).

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

- **J3 — NPC interim addressing = node UUID (Decided 2026-07-06; resolves old TODO
  J-iii).** NPCs today carry a flat `location: str` matched by name
  (`core/dm/npc_prehook.py`) — it breaks the moment flat locations are removed, and ADR
  0009 (which owns the rich NPC model) is not implemented, so this cannot be wholly
  deferred. Interim: `NPC.location` becomes a **node UUID**, resolved through the same
  scoped resolution as `move_to` (F7) — the save stays UUID-only per A6, no third
  addressing convention, and 0009 inherits the field already correct. (Rejected: authored
  slug — reintroduces the slug-in-save duality A6 eliminated; name string via alias
  index — fragile on renames and ambiguity.)

- **J4 — Scene knobs (Resolved S0; closes old TODO J-i).** All in `saga.config.yaml`
  (std 14): `max_breadcrumb_depth`, `show_travel_options`, `max_travel_options`,
  `include_node_status`, `description_max_chars`, `scene_context_max_tokens`. The
  breadcrumb renders ancestor **names** up the chain (kind names are custom, P0 — the
  spine is structural, not kind-labeled). Rework surface (old J-ii, now implementation
  work, §9 S2–S3): `tools_world.MoveTo`, the `dm.py` scene builder,
  `campaign_service.build_initial_world_state`, world-state schema v5 (D7).

---

## 4. Decided vs Open — quick index

**Decided/Refined/Resolved:** P0 (world-defined vocabularies), A1, A1b, A2 (custom
kinds), A3, A3b (scale on kind), A4 (global transform), A5, A6, A7 (transform math),
B1, B2 (km canonical), B3 (custom terrains), B4 (read-only map, parchment+pins v1),
C1–C7 (C7 = baseline/overlay split), C8 (scenario), C9 (game home), C10 (zip), C11
(columns), D1, D2, D2b, D2c, D3 (dir-as-tree, no parent_id), D3b, D3c (filename=slug),
D4, D5 (layout), D6 (npcs minimal), D7 (instantiation, schema v5), E1 (meta-schema),
E1b (base node), E2, E3, E4, F1–F9, F10 (interior exits), F11 (formula split), F12
(encounters), F13 (resolution+pathfinding), G1 (stance+label), G2, G3, G3b, G4, H1,
I1–I5, I5b, I6, I7, J1, J2, J3 (NPC interim = node UUID), J4.

**Open:** nothing design-blocking. Deferred by explicit decision: multi-scenario (C5),
portals/inter-world travel (A5), authored map images (B4), AI creator-agent (I1/I-iii),
in-session live world editing (I3), full item catalog (H1), Director simulation
formulas (G2/G4 → ADR 0006), rich NPC model (D6 → ADR 0009), rulebook shape (D2c → ADR
0010).

---

## 5. Rejected alternatives

- **Fixed-depth/named hierarchy** — rejected for the recursive typed node (A1).
- **SAGA-owned `kind` enum + per-kind Pydantic discriminated union** — rejected (P0/A2/E1,
  S0): the owner wants fully creator-defined taxonomies; the old recommended set survives
  only as the example World's default taxonomy.
- **Fixed terrain / travel-mode / relation-status enums** — rejected (P0, S0): custom
  vocabulary entries carrying engine-contract numbers instead.
- **`parent_id` field** — rejected (D3, S0): directory position is the only parent source.
- **`id` field inside node files** — rejected (D3c, S0): filename is the slug.
- **Per-node `scale` override** — rejected (A3b, S0): scale binds to the kind; unlimited
  custom kinds cover the "building can be either" case.
- **XDG per-OS paths / library inside the install dir** — rejected (C9, S0).
- **Renaming `world_state` to `world_overlay`** — rejected (C11, S0): churn on every
  existing writer for zero functional value.
- **NPCs inside node files / rich NPC schema here** — rejected (D6, S0): flat records,
  ADR 0009 owns the model.
- **Encounter tables inline in edges** — rejected (F12, S0): no reuse.
- **Frame rotation in the global transform** — rejected (A7, S0).
- **dulwich (pure-Python git)** — rejected (S0): git binary in the Docker image + fail-fast
  message when missing at editor save.
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
  scene token cost → J1. The old E-i risk (central parameter catalog) is dissolved by
  P0; its residue: **dynamic validation is more code than a static discriminated union**
  (a meta-schema layer + a param-checking pass), and a bad creator-authored taxonomy is
  now possible — mitigated by the meta-schema guardrails (types/ranges required) and the
  copyable default taxonomy.
- **New dependency:** NetworkX (pathfinding) — small, standard, fits the Python stack.
  Runtime binaries: git (already an installer-managed dependency; added to the backend
  Docker image, C9/I5b — read paths never need it, only editor saves).

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
open-tabletop-gm. Exhaustive per the owner's instruction; sprint breakdown fixed in §9
(2026-07-06).

---

## 9. Implementation plan (fixed 2026-07-06)

**Branch model:** one long-lived ADR branch `adr/0008-world-model` off `main`; each
sprint runs on its own sub-branch (`0008/s1-models-loader`, …) and merges into the ADR
branch; a single PR lands the whole cycle on `main` at the end.

- **Sprint 0 — design pass (no code). DONE 2026-07-06** (same-day interview): closed
  every open TODO; headline revision **P0 — world-defined vocabularies** (custom kinds,
  terrains, modes; meta-schema replaces the discriminated union). Committed directly on
  the ADR branch, no sub-branch.
- **Sprint 1 — models + loader.** Meta-schema + generic Node models (E1/E1b/E4), dynamic
  param validation (E2), directory-convention loader (D3/D3c/D5), three-tier validation
  (I4), edges/encounters/factions/npcs collections (F4/F12/G1/D6), the single example
  World with the default taxonomy (C4/P0). Pure backend, no DB changes.
- **Sprint 2 — instantiation + persistence.** Game home + world library (C9, git-init +
  repo-local identity I5b, git in the Docker image), `world_baseline` column + Alembic
  (C7/C11, single merge-accessor), slug→UUID instantiation + alias index (A6/D7, schema
  v5), `scenario.yaml` → the campaign row (C5/C8), `templates/` removed (C4), FE
  campaign creation switches from template picker to World picker, NPC `location` →
  node UUID (J3).
- **Sprint 3 — travel + runtime.** NetworkX graph + condition filtering (F13), `move_to`
  scoped resolution + reject-with-candidates (F7/F8), Naismith travel time (F11), edge
  encounters (F12), clock integration (F9), status overlay + `edge_overrides` + expiry
  (G3/G3b/G4), the new `<scene>` block (J1/J4).
- **Sprint 4 — read-only world map (FE).** Parchment+pins per-level map in the play
  screen (B4): pan/zoom, drill-down, travel edges; consumes Sprint 2/3 data only.
- **Sprint 5 — editor.** Create-world wizard + taxonomy-driven per-entity forms (I2/I7),
  git-commit save flow (I5/I6), export/import zip (C6/C10).

Sprints 1–3 are backend-vertical and individually mergeable to the ADR branch; the cycle
is shippable to `main` after Sprint 3 if needed (example world playable without map or
editor), but the intended PR includes all six.
</content>
