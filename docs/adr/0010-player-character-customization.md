# ADR 0010 — Player-character customization (per-world rulebook, items, skill progression)

- **Status**: Proposed (direction fixed by the 2026-06-23 interview; **the 2026-07-12 design
  pass closed every structural fork** — items/inventory/placements added to scope, progression
  numbers fixed, the resolution seam re-grounded on the expanded ADR 0003, the clean-restart
  assumption **revised to rung+seed**. Remaining TODOs are numeric defaults and explicitly
  marked). Supersedes the earlier "WIP" stub. **Active abilities → ADR 0012.**
- **Date**: 2026-06-23; design pass 2026-07-12.
- **Context items**: Voyage analysis (`scratch/research/voyage.md` §3bis, direct in-game
  observation 2026-06-22, + §3.6/§4); spun off from ADR 0007; design interviews 2026-06-23 and
  2026-07-12 (all calls by the project owner), grounded live in `core/dice.py`,
  `core/dm/dm_tools_executor.py`, `core/npc_scaffold.py`, `ai/tools/tools_inventory.py`,
  `models/campaign.py`, FE `class-presets.ts`; ADR 0003 (expanded 2026-07-12).
- **Scope note**: defines the **per-world character rulebook** (attributes, resources, skills,
  trait-bundles, **items**), the **character runtime** (typed sheet, layers, progression,
  equipment), **item placements** in the world, and **NPC inventory pools**. Resolution math +
  statblock → **0003**. Active abilities + the structured-input rail design → **0012** (first
  rail slice implemented here, S4). World container/authoring machinery → **0008**. NPC record
  core → **0009**. Affect → **0005**.

---

## 1. Context

**Grounding (live code, re-verified 2026-07-12):**

- `character_data` is a free untyped dict (JSONB), seeded by the FE at creation. The dice
  mis-keying bug that made ability scores inert is **fixed** (commit `80fe1ec`, H1 landed);
  the three-convention drift and the untyped schema remain.
- **No skill/proficiency concept anywhere**; no progression. `request_dice` still carries the
  hardcoded six-stat enum (its `difficulty`-based rework is 0003-D, landing before this ADR).
- Inventory is `{name, description, quantity}` free-form (`tools_inventory.py`) — flavor only,
  mechanically inert. No item concept, no equipment, no placement.
- **The clean-restart assumption of 2026-06-23 is stale**: worlds (library + editor), campaigns
  and two world-state migration rungs (v6→v7 0005/0009) now exist and are worth preserving.
  Revised in §H.

**Voyage (§3bis):** fully world-defined character system — attributes, resources, skills
(Level+XP under attributes), trait-bundles, abilities — nothing hardcoded, creation as a chain
of bundle choices.

**ADR 0003 (expanded 2026-07-12)** now owns the unified resolver (6 difficulty levels + draws,
bands, advantage, the **character-modifier clamp `[-5, +11]`**), server-side damage (weapon
classes × tier), the armor hook (DR%), heal/hazard % classes, and the NPC statblock. This ADR
fills the seams 0003 left: the sheet that produces the modifier, the items that declare the
classes, the progression that grows the numbers.

---

## 2. Scope & boundaries

**In scope:** rulebook storage + layout; kind catalog (Attribute / Resource / Skill /
Trait-bundle / **Item**); unified modifier layers; skill + character progression (all numbers);
the resolution feed into 0003 (formula, weapon skills); typed `character_data` + prompt
projection; equipment (UI rail slice); item **placements** in the world; **NPC inventory
pools**; migration.

**Out of scope:** active abilities + full rail (**0012**); resolution/damage math + statblock
templates (**0003**); commerce/prices/shops (**future ADR**, noted in TODO.md); companion
promotion (**future companion ADR** — see §I8); multi-scenario (gated 0008-C5).

---

## 3. Decisions

> Legend: **Decided** / **Refined** / **TODO**. Sections A–H carry the 2026-06-23 base
> (updated where the 2026-07-12 pass changed them); §I (items) and §L (numbers) are new.

### A. Rulebook storage & layout

- **A1–A4 (Decided, unchanged).** 0008 owns container/authoring/storage; the rulebook is a
  separate top-level `rulebook/` collection in the World tree; frozen `rulebook` JSONB column
  at instantiation (0008-C3 pattern); character instance stays in `character_data`.
- **A5 (Refined, unchanged).** World-scoped now; per-scenario layer gated on 0008-C5.
- **A6 — Directory layout (Decided 2026-07-12).** Scalar kinds in single files, bundle/item
  categories as folders (0008-D3: category = folder, `_category.yaml` meta):

  ```
  worlds/<slug>/rulebook/
    attributes.yaml
    resources.yaml
    skills.yaml
    progression.yaml        # curves, tier→grant, weights override, char thresholds
    bundles/
      races/_category.yaml + nord.yaml …
      classes/…  backgrounds/…
    items/
      weapons/…  armor/…  consumables/…
  ```

  The editor scaffolds "New category" for bundles and items alike.

### B. Kind catalog

- **B1 — Kinds (Decided; Item added 2026-07-12).** Attribute, Resource, Skill, Trait-bundle
  (unchanged from 2026-06-23), **Item (§I)**; Ability → 0012. Each a typed Pydantic submodel,
  tier-3 validated, engine-computed vs LLM-flavor partitioned.
- **B2/B3 (Decided, unchanged).** `parent_attribute` on Skill; Trait-bundle generic, category
  = folder, `_category.yaml` creation-slot rules.
- **B4 — Resources (Decided; shapes fixed 2026-07-12).** `hp` becomes one Resource among many.
  **Structured patterns, never free-formula strings** (parser + weak validation rejected):
  `max_formula: {base, plus?: {attribute: <ref>, per_point: k}}`;
  `regen: none | full_on_rest | per_player_turn: n`. `hp` defaults `regen: none` — healing
  goes through 0003 (heal tool / self-heal rail). **Dual-shape seam (explicit):** player HP =
  this Resource; NPC HP = the plain statblock int (0003-B3, no sheet) — 0003's single
  damage-apply function reads/writes both through one accessor, never two code paths.

### C. Unified modifier layers

- **C1/C2/C3 (Decided, updated).** Everything is `{base, layers[]}`, effective = base + Σ,
  uniformly for attributes/skills/resources; layers carry provenance. **Update 2026-07-12**:
  the "0003 circumstance modifier" hook mentioned in June is **superseded** — 0003-A5 replaced
  numeric circumstance with binary advantage/disadvantage; layers serve creation bundles,
  **equipped items (§I)**, buffs/status (durations → 0012). Clamp granularity (C3, settled):
  attribute base within kind `min/max`, effective clamped at kind max; skill at `max_level` +
  the global **+6 bonus guardrail** (config); resource `0..max`; the **total** modifier
  entering the resolver clamped `[-5, +11]` by 0003-A6.

### D. Skill progression (numbers fixed 2026-07-12)

- **D1/D2/D3 (Decided, unchanged frame).** XP auto-granted on the roll, engine-owned, no LLM
  tool; grant = f(outcome tier) in the dice post-hook; VALUE → rulebook, GUARDRAIL → config.
- **D4 — Default numbers (Decided).** `tier_xp_grant`: crit 5 · full 3 · partial 2 · soft 1 ·
  hard 1 · fumble 0 (learn-from-failure kept, fumbles teach nothing). XP curve
  **exponential**: `xp_to_next = base·growth^(level-1)`, default `base 5, growth 1.6` (steep:
  early levels fast, mastery a real journey). Skill bonus = **stepped table** in the rulebook
  (author-readable, no formulas): lvl 1→0, 2-3→+1, 4-5→+2, 6→+3, 7→+3, 8→+4, 9→+5, 10→+6.
  All rulebook values, playtest-tunable without code.
- **D5 — Anti-farm: XP decay on consecutive use (Decided).** Consecutive rolls on the same
  skill halve the grant progressively (`grant × 0.5^(n-1)`, **rounded down, floor 0**);
  counter resets on a different-skill roll **or on location change** ("scene" is not an engine
  concept — these two are). The roll itself is **never** touched (rejected: success penalty
  after N uses — punishes legitimate sequences like a stealth mission, breaks the
  deterministic-odds story, unexplainable in UI). Config knob for the decay factor.
- **D6 — Skill level-up feeds character XP (Decided).** Each skill level-up grants a small
  flat char-XP (`char_xp_per_skill_levelup`, default 3, rulebook) — using skills nourishes the
  character level alongside the DM's milestones (G).

### E. Resolution seam with ADR 0003 (re-grounded 2026-07-12)

- **E1 (Decided).** 0010 owns "sheet → modifier"; 0003 owns "modifier → outcome → damage".
  The E4 asks of June are **answered** by the expanded 0003: clamp `[-5, +11]` (A6),
  `skill|attribute` ids (its D contract, swap lands with this ADR), armor DR% + item classes
  + the single damage-apply reducer hook (B6/B7b).
- **E2 (Decided, unchanged).** `request_dice` takes `skill | attribute: id`, world-defined,
  validated, reject-with-candidates.
- **E3 — Formula + weights (Decided, numbers fixed).**
  `modifier = w_attr·attr_mod + w_skill·skill_bonus`, **default weights 1.0/1.0** in
  `saga.config.yaml`, per-world rulebook override within config bounds (D3 principle). Budget
  splits the 0003 clamp exactly: attribute ≤ +5 (`(score-10)//2`, score cap 20) + skill ≤ +6
  = +11.
- **E5 — Weapon skills close the combat seam (Decided 2026-07-12).** A weapon Item may
  declare `skill: <ref>` (e.g. `one_handed`, world-defined); `attack` then resolves with the
  **full E3 formula** (parent attribute + that skill) and **grants XP to that skill** (D1,
  decay included). No skill ref / unarmed / improvised → fallback to pure attribute via
  0003's `weapon_class_to_stat`. Without this, combat skills could never exist or progress.
- **E6 — DEX modulates player defense (Decided 2026-07-12; math owned by 0003).** Player
  `defense` = default + threshold shift from DEX mod (±1 level max; e.g. mod ≥ +4 → +1,
  ≤ −2 → −1; thresholds config). Dex-is-king risk accepted with mitigations: high threshold,
  ±1 cap, and the STR path compensates (heavy weapons 1d12 + DR-flavored heavy armor). The
  example rulebook must respect this balance; playtest tunes the thresholds.

### F. Typed `character_data` + prompt projection

- **F1 — Schema (Decided, catalog fixed 2026-07-12).**

  ```
  character_data (Pydantic):
    identity    {name, bundles[refs], …}     # bundle refs = provenance/display
    attributes  {id: {base, layers[]}}
    skills      {id: {xp, base_level, layers[]}}
    resources   {id: {current, layers[]}}    # max computed from formula + layers
    inventory   [ItemRecord]                 # §I — typed records, never strings
    equipped    {slot: item_uuid}            # UI rail only (§I6)
    abilities   {id: {cooldown_remaining, level, unlocked}}   # 0012
    defense     <level>                      # 0003 base; DEX shift E6; armor = DR not defense
    progression {char_xp, char_level, ability_points, attribute_points}
  ```

- **F2/F3 (Decided, unchanged).** Compact prompt projection (identity + effective stats + top
  skills + resources + inventory + ready abilities); fully dynamic FE creation/sheet replacing
  `CLASS_PRESETS`.

### G. Character-level XP (Decided 2026-07-12 — was soft TODO)

- **G1 — DM signals *when*, engine owns *how much*.** New DM tool
  `grant_progress(magnitude: minor|major|milestone, reason)` — no values ever; the engine
  draws XP from the rulebook range of that magnitude. Level thresholds exponential (×1.6,
  same family as skills).
- **G2 — Level-up effects.** **+1 ability point every level** (spend rules → 0012); **+1
  attribute point every 5 levels** (spent from the UI, raises an attribute base within its
  kind range; the A6 clamp and kind max cap the outcome). Two char-XP sources only:
  `grant_progress` (story milestones) + D6 (skill mastery).

### H. Migration (REVISED 2026-07-12 — supersedes the clean-restart assumption)

- **H2 — Rung + seed, no wipe (Decided).** The June "clean restart, no migration" premise is
  void (live worlds/saves + the 0009 rung precedent). Instead: `character_data` gets a
  **typing rung** (old `abilities` dict → `attributes{base}`, `hp` → resource, inventory
  strings → ad-hoc flavor `ItemRecord`s; skills/progression born empty); worlds without
  `rulebook/` get the **bundled default rulebook seed** on load (the 0005/0009 "customize"
  pattern); the example world ships an authored rulebook (S1).
- **H1 (Done).** The mis-keying dice fix landed independently (commit `80fe1ec`).

### I. Items, inventory, equipment, placements (new, 2026-07-12)

- **I1 — The "mega-class" Item: two levels, every inventory entry is a record (Decided).**
  Rulebook `items/` holds authored **definitions** (legendary uniques and commons alike:
  steel sword, coins, healing potion). The runtime **instance** is a typed `ItemRecord`
  (uuid, name, `source: <rulebook-ref> | adhoc`, quantity, mechanical fields) — the 0009
  record pattern applied to objects; **no naked strings**, even a plain wooden stick is a
  (flavor-only) record. Item mechanical surface: `weapon_class` / `armor_reduction` (DR class,
  0003-B6) / `heal_class` (consumables, 0003-B7b) / `skill` ref (E5) / `modifiers[]` (C-layers
  while equipped) / `equip_slot` / `consumable` / `grants_abilities` (0012).
- **I2 — Ad-hoc items may carry bounded classes (Decided).** `add_item` on an unknown name
  creates an ad-hoc record; the DM may classify it **once at creation** (enum classes only,
  validated — never numbers). Strictly better than 0003's per-attack classification:
  persistent, auditable, correctable. Known-name resolution follows the 0009 pattern
  (resolver + typo guard reject-with-candidates); the resolve-or-create lives **inside the
  tool executor** (like `validate_or_create_npc`), no new turn hook.
- **I3 — Two tools, not one modal (Decided).** `add_item` / `remove_item` stay separate
  (flat schemas beat a `mode:` param for the LLM; consistent with 0009's granular tools);
  both reworked for records. Rejected: single `manage_inventory`.
- **I4 — Placed items in the world (Decided, in scope, S4).** Authored nodes may carry
  `placed_items: [{item: <ref>, hidden?, …}]` (0008 tree, tier-3 validated, editor support).
  Overlay holds the per-placement state machine: `placed → taken → dropped(node)`;
  `consumed/broken` terminal. Pickup mints the inventory instance.
- **I5 — Conservation follows provenance (Decided).** **Authored/placed items are conserved**
  (dropped → they land on the current node, findable forever). **Ad-hoc/common items are
  not** (drop = narration, record leaves inventory; the DM can recreate). Full world-tracking
  of every stick rejected as overlay bloat for zero payoff.
- **I6 — Equipment is a UI rail action (Decided).** Equip/unequip is a structured player
  action (the 0012 rail — **first slice implemented in this ADR's S4**: equip + `use_item`
  consumables per 0003-B7b), engine applies/removes the item's C-layers and DR; the DM
  narrates but **cannot** change equip state. Stackables carry `quantity`; equippables are
  quantity 1. Item consumption/equip injects a fact into the DM turn context (the DM must
  know you drank the potion).
- **I7 — Currency is just an item (Decided).** Coins = stackable rulebook item. Prices,
  shops, trading = **out of scope → future commerce ADR** (TODO.md).
- **I8 — NPC inventories from class pools (Decided).** Every NPC gets an inventory:
  **authored** NPCs list explicit item refs in their world YAML; **auto-created** NPCs draw
  from the **item pool of their `npc_class`** (taxonomy `npc_classes` — the statblock-template
  half is 0003-B3's; this ADR adds the `items:` pool half: guard → armor+helmet+sword,
  commoner → a few coins). Pools declared in taxonomy but **inert until this ADR's S4** (items
  must exist first; 0003 ships templates-without-pools). Death/theft → the engine **transfers
  the record** to the player inventory (deterministic loot). **Known limit (accepted):** the
  NPC statblock does not react to inventory changes — a disarmed guard still hits
  `damage_class: medium`; narration covers it, a "weapon lost → unarmed" micro-rule is a
  future knob. NPC **skills/abilities: none** (statblock stays the whole NPC sheet; a boss's
  signature move is a trait the DM narrates through normal `attack`). Rationale beyond combat:
  **uniform NPC schema** (traits+psychology+statblock+inventory, however sparse) is the
  prerequisite for the companion vision — recruiting promotes *content* (a generated full
  mini-sheet: skills, abilities, well-defined equipment), never *schema* (→ companion ADR,
  TODO.md).

---

## 4. Decided vs Open — quick index

**Decided:** A1–A6, B1–B4, C1–C3, D1–D6, E1–E3 + E5–E6, F1–F3, G1–G2, H2, I1–I8, sprint plan
(§7). **H1 done** (commit `80fe1ec`).

**Open TODOs:** `grant_progress` magnitude XP ranges (rulebook defaults, S3) · `_category.yaml`
creation-slot fine rules · per-world override of 0003 damage-class dice (D3-consistent
alignment, default config) · shared-rulebook-library alignment (A2, future) · per-scenario
layer (gated 0008-C5) · commerce ADR · companion-promotion ADR (mini-sheet generation on
recruit) · "weapon lost → unarmed" micro-knob (I8).

---

## 5. Rejected alternatives

June set unchanged (location-tree rulebook; shared library *for now*; baseline/overlay folds;
fixed Race/Class kinds; bake-all layers; `update_skill` tool; fixed formula weights; full-sheet
prompt; curve in config; deferred mis-keying fix). Added 2026-07-12: free-formula strings for
resources (parser + weak validation); success-penalty anti-farm (punishes legitimate play,
dirties deterministic odds); items as equippable Trait-bundles (consumables don't fit) and
mechanics-only-from-rulebook (improvised loot stays inert); single modal inventory tool;
world-tracking ad-hoc drops; NPC full sheets / NPC abilities (A2 0012 holds; statblock is the
NPC sheet); wipe-based migration (0009 rung precedent); numeric authored NPC level (duplicates
statblock classes — threat display is *derived*).

---

## 6. Consequences / risks

- **Positive:** fully per-world character system with typed sheet; one layer mechanism for
  bundles/items/buffs; items close 0003's open consumers (weapon/armor/heal classes) and make
  loot, theft and placed treasure deterministic; progression is engine-owned end-to-end (no
  LLM numbers anywhere: grants, draws, decays all config/rulebook); uniform NPC schema readies
  companions.
- **Trade-offs:** substantial FE rebuild (dynamic creation/sheet + inventory/equip UI); a
  three-store read merge (rulebook + baseline + overlay); record growth in inventories
  (mitigated: stacking, dead-unnamed prune 0003, ad-hoc non-conservation I5).
- **Risks:** balance drift across many rulebook numbers (mitigated by config guardrail
  envelope + the A6 clamp); DEX-is-king (E6 mitigations, playtest-tuned); rung complexity on
  `character_data` (mitigated: 0009 rung precedent + the typing rung is mostly mechanical).

---

## 7. Implementation plan (fixed; prerequisite: 0003 S1–S2 landed)

Five sprints on one branch, each leaving the suite green and the game playable:

- **S1 — Rulebook core:** kind meta-schemas (incl. Item defs) + `rulebook/` loader + tier-3 +
  frozen column + example-world rulebook + config guardrails + default-rulebook seed (H2).
- **S2 — Character runtime:** typed `character_data` + rung (H2) + layer engine + creation
  from bundles (API) + resolver feed (E2 ids, E3 formula, E5 weapon skills, E6 DEX shift).
- **S3 — Progression:** XP auto-on-roll + decay + level-ups + `grant_progress` + char-XP (D6)
  + attribute points.
- **S4 — Items:** ItemRecords + add/remove rework + **rail first slice** (equip + `use_item`
  per 0003-B7b) + placements (loader/overlay/pickup) + NPC pools (I8) + editor sections.
- **S5 — FE:** dynamic creation chain + sheet + inventory/equip UI + playtest → PR → Accepted.

## 8. Relationship to other ADRs

- **0003** — the resolver/damage frame this plugs into: clamp A6, weapon classes (items
  declare them, E5 skills), armor DR% (I1 `armor_reduction` + its reducer hook), heal classes
  (consumables + self-heal rail), statblock templates (`npc_classes` taxonomy — 0003 owns the
  statblock half, this ADR the item-pool half), DEX defense shift (E6, math in 0003).
- **0012** — sibling; owns the rail *design* + abilities; this ADR implements the first rail
  slice (S4) and feeds it ability points (G2) and `grants_abilities` items.
- **0009** — record patterns reused (resolver, typo guard, scaffold); NPC inventory field
  extends its engine contract (B2 partition update).
- **0008** — container/authoring/storage; placements ride nodes + overlay; `npc_classes` in
  taxonomy; editor sections.
- **0005 / 0007** — unchanged (affect; parent direction).

## 9. Notes / sources

`scratch/research/voyage.md` §3bis. Interviews 2026-06-23 + 2026-07-12 (every fork closed by
the project owner; notable owner calls: exponential ×1.6 XP curve, XP-side anti-farm over roll
penalties, items-for-everything "mega-class", NPC class pools, rung over wipe). Grounded in the
live code listed in the header; no external validation research needed (tabletop mechanics +
verified code + owner taste).
