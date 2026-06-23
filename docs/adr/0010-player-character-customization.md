# ADR 0010 — Player-character customization (per-world rulebook + skill progression)

- **Status**: Proposed (direction + decisions fixed via the 2026-06-23 design interview,
  grounded in the live code; **fine mechanics remain explicit TODOs**, may still be revised).
  Supersedes the earlier "WIP, nothing decided" stub. **Active abilities are spun off to
  ADR 0012.**
- **Date**: 2026-06-23
- **Context items**: Voyage analysis (`scratch/research/voyage.md` §3bis — **direct in-game
  observation** 2026-06-22 — plus §3.6/§4); spun off from ADR 0007 (2026-06-15); deep design
  interview 2026-06-23 (all choices by the project owner), grounded in `core/dice.py`,
  `core/dm/dm_tools_executor.py`, `ai/prompts/dm.py`, `models/campaign.py`, and the frontend
  `class-presets.ts` / `character-sheet-parts.tsx`.
- **Scope note**: defines the **per-world character rulebook** and the **character runtime**
  (sheet, progression, resolution feed). Active abilities → **ADR 0012**. Resolution
  thresholds + damage → **ADR 0003**. World authoring/storage machinery → **ADR 0008**.
  Affect/disposition → **ADR 0005**.

---

## 1. Context

**Grounding (live code, 2026-06-23):**

- `character_data` is a **free untyped dict** (JSONB, `models/campaign.py:48`, "denormalized
  for fast access"), seeded from the **frontend** at creation (`campaign_service`). No
  canonical schema.
- The ability-score system is **half-wired and inconsistently keyed**: the FE sends
  `abilities: {strength:16, dexterity:12, …}` (full lowercase names, `class-presets.ts`); the
  **dice resolver** reads `abilities.get("DEX", abilities.get("dex", 10))`
  (`dm_tools_executor.py:217`) → matches neither `"dexterity"` → **falls back to 10 → modifier
  +0 on every check** (ability scores inert); **combat** reads
  `abilities.get("DEX", abilities.get("dexterity", 10))` (`combat_graph.py:35`) → matches; the
  **prompt** reads flat `char_data["dex"]` (`dm.py:71`) → never populated → abilities never
  rendered. Three conventions, one of which makes checks ignore the sheet entirely.
- `request_dice` carries `stat: str` hardcoded to "STR, DEX, CON, INT, WIS, CHA"
  (`tools_special.py:14`); `modifier = (score-10)//2` (D&D, fixed six stats).
- **No skill/proficiency concept anywhere** — no progression, no `update_skill`. Greenfield.

**Voyage (direct in-game observation, §3bis):** a fully **world-defined** character system —
attributes, resources (Health/Magicka/Stamina), skills (Level+XP, hung off attributes),
races/classes/talents/backgrounds (modifier bundles), active abilities (Power+Cooldown).
Nothing hardcoded (Skyrim's attribute set ≠ the default world's). Character creation = a chain
of modifier-bundle choices; the sheet is **run-independent** (reusable, D&D-style).

**Clean-restart assumption (load-bearing):** there are **no live worlds/saves** — we restart
clean. So **no migration**; we choose the canonical schema freely. *If saves ever need
preserving, every "no migration" decision below must be revisited.*

This ADR makes the character system match that ambition: a per-world rulebook + a typed,
progressable sheet, replacing the inert hardcoded six-stat dict.

---

## 2. Scope & boundaries

**In scope:** where the rulebook lives + the 0008↔0010 boundary; the character-system kind
catalog (Attribute/Resource/Skill/Trait-bundle); the unified modifier-layer model; skill
progression; the resolution feed (the `request_dice` contract + the modifier formula); the
typed `character_data` schema + per-turn prompt projection; the immediate mis-keying fix.

**Out of scope (owned elsewhere):**
- **Active abilities** (player-triggered, cooldown, ability points, Power) → **ADR 0012**.
- **Resolution thresholds** (bands vs DC) + **outcome→damage** → **ADR 0003**.
- **World authoring surface + asset/save storage machinery** → **ADR 0008**.
- **Affect/disposition** → **ADR 0005**.
- **Multi-scenario** (per-scenario creation options) → gated behind **ADR 0008-C5**.

---

## 3. Decisions

> Legend: **Decided** = settled in the interview. **Refined** = hardened. **TODO** =
> consciously deferred to implementation, with a note on *what* must be resolved.

### A. The 0008↔0010 boundary + rulebook storage

- **A1 — Boundary (Decided).** **0008** owns the *container* (the World asset), the *authoring
  surface*, the *storage machinery*, and the *spatial kinds* (region/site/…). **0010** owns the
  *character-system kind schemas* + the *character runtime*. They meet in the shared E1 pattern,
  not in the kind catalogs (disjoint). One line: *0008 = container + authoring + storage; 0010
  = character meta-model + runtime; the rulebook is an authored block in the World whose shape
  0010 defines.*
- **A2 — Rulebook is per-World, a separate top-level collection (Decided).** The rulebook lives
  as a separate top-level `rulebook/` collection in the World file tree (sibling to `regions/`,
  `edges/`, `scenario.yaml`), consistent with **0008-D2b** (cross-cutting concerns get a
  top-level collection, like `edges/`). **Category = the containing folder** (directory
  convention, **0008-D3**); no `category:` field. The in-game editor's "new category" action
  scaffolds a subfolder. The example World ships conventional folders (`races/`, `classes/`…)
  but they are **not privileged**. Rejected: folding the rulebook into the location tree (it's
  cross-cutting, not a location — initial proposal, withdrawn); a **shared/reusable rulebook
  library** referenced by Worlds (Foundry "game system" model) — more powerful + enables reuse,
  but adds a second library + reference resolution + dual versioning + dual snapshot; **deferred
  as a future alignment**, reachable without refactor precisely because the rulebook is already
  an isolated collection.
- **A3 — Runtime storage: a frozen `rulebook` JSONB column (Decided).** At instantiation the
  authored rulebook is written **once** into a `rulebook` JSONB store (frozen per **0008-C3**,
  like `world_baseline`), read-but-not-written per turn. The save embeds its rulebook snapshot
  so editing the World later doesn't change the save. Rejected: folding into `world_baseline`
  (loses concern-separation + independent loadability, though same lifecycle); a separate
  library (A2).
- **A4 — Character instance in `character_data`, no split (Decided).** The sheet + mutable
  progression stays in the existing `character_data` column (0010 owns its shape, §F). The
  0008-C7 baseline/overlay split was motivated by **TOAST write-amplification** on a *large*
  per-turn-rewritten world tree; `character_data` is **small** → that pressure doesn't apply.
  Noted as a future option if it grows. Rejected: a static/runtime split mirroring
  baseline/overlay (premature); folding into `world_overlay` (conflates character with world,
  breaks the run-independent-character idea).
- **A5 — Scope: world-scoped now, modular for multi-scenario (Refined).** The whole rulebook is
  world-scoped (one scenario per World per **0008-C5**). The per-scenario creation-option layer
  (Voyage's scenario-specific background/training; the many story-starts per world) is a
  **future alignment**, reachable without refactor — *designed-for*, not built. Latent
  dependency: it un-blocks only when 0008-C5 un-defers multi-scenario.

**TODO (A):** exact `rulebook/` directory layout (coordinate **0008 TODO D-i**); the editor
"new category" action name; the shared-rulebook-library future alignment.

### B. The character-system kind catalog

- **B1 — 0010 owns the kinds, reusing 0008-E1/E3 (Decided).** Each kind is a Pydantic submodel
  (typed core + closed params bag + **mandatory-by-kind validation at instantiation**, E1),
  partitioned **engine-computed vs LLM-flavor** (E3). The kinds:
  - **Attribute** `{id, name, default, min, max}`
  - **Resource** `{id, name, max_formula(ref), regen_rule, min, max}`
  - **Skill** `{id, name, parent_attribute(ref), start_level, xp_curve(ref), max_level}`
  - **Trait-bundle** `{category(=folder), name, description(flavor), modifiers[]{target_kind,
    target_id, delta}, grants_abilities?[]}`
  - (**Ability** kind → **ADR 0012**.)
- **B2 — Skill→Attribute is an explicit parent relation (Decided).** `parent_attribute` ref
  (Sneak under dexterity, §3bis), used by the resolution formula (§E) and UI grouping.
- **B3 — Trait-bundle is one generic kind; category = folder (Decided).** Race / class /
  talent / background / affiliation / deity are **not** distinct kinds — one **Trait-bundle**
  kind, the category materialized by the **containing folder** (0008-D3 directory convention).
  Each category folder carries a small `_category.yaml` meta `{display_name, min_select,
  max_select, order}` for creation-slot rules (race = 1, talents = 0..n). Rejected: fixed
  distinct kinds Race/Class/Background (a world couldn't add affiliations/deities without code —
  contradicts the Skyrim observation + max-customization); a `category:` field inside each file
  (redundant with the folder, against D3); hybrid core-fixed + generic (two mechanisms,
  arbitrary "core" line).
- **B4 — Resource boundary: schema 0010, damage 0003 (Decided).** 0010 owns *which* resources
  exist + their max/regen schema; **0003** owns combat **damage** to them. Today's special-cased
  `hp` becomes "one Resource among many".

**TODO (B):** the per-kind field catalog (coordinate **0008 TODO E-i**); the `xp_curve` /
`max_formula` / `regen_rule` exact shapes; whether resources need their own regen tick
(coordinate 0008-G3).

### C. Unified modifier-layer model

- **C1 — Everything is a layer (Decided).** Each engine-computed sheet value is
  `{base, layers[]}`; a layer is `{source, target, delta, permanence}`; **effective = base +
  Σ applicable layers**. **One** mechanism for permanent creation modifiers (race/class) and
  temporary effects (buffs/status/circumstance). Gives provenance for display (Voyage shows
  "Nord +2"), reversibility, and a native hook for **0008-G3** (duration/tick/expire) and
  **0003** (circumstance modifier). Cost: recompute on read (trivial at character scale).
  Rejected: bake-all (irreversible, no provenance, still needs a second temp-system → two
  mechanisms); hybrid bake-perm/layer-temp (loses bundle provenance, re-derive on change).
- **C2 — The layer model applies uniformly to attributes, skills, AND resources (Decided).**
  Bundles modify all three ("Sneak +5", "Health +30"). So **Skill** is `{base_level (from XP),
  xp, layers[]}` (`effective_level = base_level + Σ layers`), not just `{level, xp}`;
  **Resource** is `{current, max, layers[]}`.
- **C3 — The hard-max guardrail clamps the EFFECTIVE value (Decided).** Stacked layers cannot
  push a value past its hard cap (base 14 +2+2+3 vs max 20 → clamped to 20). Base stays within
  the authored creation range; effective is clamped (a buff at the cap is wasted — standard).
  **TODO:** confirm clamp granularity per kind.

### D. Skill progression

- **D1 — XP auto-granted on the roll, engine-owned (Decided).** When `request_dice` uses a
  skill, the engine grants XP to that skill — deterministic, no LLM tool, zero token cost
  (std 8/19). A skill used in pure narration without a roll doesn't gain XP (acceptable: stakes
  resolve via dice). Rejected: a DM `update_skill` tool (token cost + LLM-driven mechanic,
  against std 8); both (double-write to one XP field).
- **D2 — Grant = f(outcome tier), post-resolution hook (Decided).** The grant amount scales with
  the 6-tier outcome (0003's ladder), computed in the dice post-hook
  (`dm_tools_executor.py::_handle_dice`, where the tier is already known). A crit grants more
  than a poor success. Default success-scaled; the `tier → grant` map is a per-world **rulebook**
  value (config-bounded). The "learn from failure/challenge" philosophy is expressible via the
  same map.
- **D3 — Curve + cap in the rulebook; bounds in config (Decided).** The XP curve (default
  per-rulebook formula + optional per-skill override) and `max_level` live in the **rulebook**
  (per-world). `saga.config.yaml` holds only the hard min/max envelope. This is the
  **cross-cutting principle**:
  > **VALUE → rulebook (per-world); GUARDRAIL → `saga.config.yaml` (global).**

  Level-up is automatic + engine-owned at threshold; the level's effect on resolution → §E.

**TODO (D):** the default curve shape + grant map; the `tier → grant` exact values (rulebook).

### E. Resolution seam with ADR 0003

- **E1 — Boundary (Decided).** 0010 owns **"sheet → modifier"**; **0003** owns
  **"modifier → outcome"** (bands/DC) and **"outcome → damage"**. They meet at `request_dice`.
  With the rulebook-weighted formula (E3), **0003 stays agnostic** to how the modifier is
  composed.
- **E2 — `request_dice` contract rework (Decided).** The `stat: STR|DEX|…` enum becomes
  `skill | attribute: id` (world-defined ids; carries `skill` when one applies, else
  `attribute`). The engine resolves `skill → parent_attribute` (B2) + sums layers (§C). The
  passed id is **validated against the rulebook**; unknown → **reject-with-candidates**
  (F7-style, std 6/13). This sanitizes the mis-keying **by design** (§H).
- **E3 — Modifier formula: rulebook-weighted (Decided).**
  `modifier = w_attr · attr_mod + w_skill · skill_mod(level)`, weights per-world
  (config-bounded), **default skill-significant** (honours the "skill must matter, not
  cosmetic" constraint). Attribute-heavy (D&D) or skill-heavy (Elder Scrolls) is a per-world
  choice. Rejected: fixed additive (no per-world tuning); skill-primary fixed (attributes
  near-irrelevant for skilled checks).
- **E4 — Coordination asks to ADR 0003 (Decided as asks; the 0003 edit is the follow-up).**
  0003 (Proposed) must: (a) generalize "modifier = character stat + circumstance" →
  "modifier = sheet-produced value (0010) + circumstance"; (b) accept `skill | attribute` id in
  place of the `stat` enum; (c) (with 0012) map ability **Power → server-side effect**.
  **ADR-writing order**: finish 0010, then the surgical 0003 edit. **Implementation order**:
  0003 (resolution frame) first, then 0010 plugs in.

**TODO (E):** default weights; the `skill_mod(level)` curve.

### F. Typed `character_data` + prompt projection

- **F1 — `character_data` becomes a typed Pydantic model (Decided).** Replaces the free dict
  (the same typed-record pressure as 0009-B2, the same E1 discipline). Shape = the layer model
  (§C) over the kinds (§B). Field catalog = **TODO**.
- **F2 — Per-turn prompt = compact projection + identity (Decided).** The `<character>` block
  carries: **identity labels** (name, gender, race/class/background, condition), **effective
  stats** (layers summed), **relevant/top skills**, **resources** current/max, inventory (and,
  via 0012, **ready abilities**). **Not** per-turn: layer breakdown, xp-to-next, numeric
  cooldown, and the **long backstory** — the backstory folds into `global_summary` / is set at
  creation, not re-injected raw. Projection depth = config knob (std 14 / ADR 0007). Rejected:
  full sheet every turn (token cost on BYOAK, mostly noise); scene-adaptive projection
  (selection logic to build/test, risks hiding a useful skill — a future refinement).
- **F3 — Frontend consequence (Decided as a consequence/TODO).** World-defined
  attributes/skills/resources + the creation chain make the FE character sheet **and the
  creation UI fully dynamic**, replacing the hardcoded `CLASS_PRESETS` (warrior/rogue/mage) and
  `KNOWN_ABILITIES`. Substantial FE work, recorded here (the stub's open-question #4).

### G. Character-level XP (soft)

- **G1 — Soft TODO, leaning captured (TODO).** Character-level XP (distinct from per-skill XP)
  is **under-observed** (we saw "Level 1, 235/1000 XP" + "0 Ability Points", never a level-up).
  **Leaning:** a **DM-triggered tool that does NOT pass the value** — the DM signals the *when*
  (optionally a qualitative magnitude), the **backend assigns a deterministic bounded value**
  (server-side roll in a rulebook range). Keeps the *when* expressive (narrative judgment, more
  frequent than quest-only) and the *value* engine-owned (resolves std 8). **Symmetric with §D**:
  skill-XP = auto-on-roll; char-XP = DM-trigger / engine-value. Level-up **effect** candidates
  (decide at implementation, all retained): **ability points** (→ 0012), **attribute points**,
  **resource-max increase**, **ability unlock**. Not blocking; separable from the core.

### H. Mis-keying fix — now, decoupled

- **H1 — Land a minimal `fix(dice)` now, independent of 0010 (Decided).** The live bug —
  `request_dice` reads `abilities.get("DEX", abilities.get("dex", 10))` while the FE stores full
  lowercase names (`"dexterity"`) → **modifier +0 on every check, ability scores inert** —
  persists through playtesting until 0010 ships (gated behind 0001/0003/0008, i.e. far off). A
  tiny **key-alignment** fix (align the dice reader to the FE's keys, or normalize) makes
  ability scores work in checks **immediately**. Thrown away when F1 retypes `character_data`,
  but minuscule. Tracked as a detailed **NOW** item in `TODO.md`.

---

## 4. Decided vs Open — quick index

**Decided:** A1–A4 (+A5 Refined), B1–B4, C1–C3, D1–D3, E1–E4, F1–F3, H1.

**Open TODOs (may still be revised):** `rulebook/` directory layout + editor action name +
shared-library alignment (A); per-kind field catalog + curve/regen shapes (B); clamp
granularity (C); default curve + `tier→grant` values (D); default weights + skill curve (E);
`character_data` field catalog (F); **char-level XP source + effect** (G, soft); the
**coordinated 0003 edit** (E4); the **per-scenario layer** (gated 0008-C5); **active abilities
entirely** (→ 0012).

---

## 5. Rejected alternatives

- **Rulebook folded into the location tree** — rejected; it's cross-cutting, gets a top-level
  collection (A2, per 0008-D2b).
- **Shared/reusable rulebook library (Foundry "game system")** — rejected *for now*; per-World,
  shared as a future alignment (A2).
- **Folding the rulebook into `world_baseline`** / **character into `world_overlay`** — rejected;
  frozen `rulebook` column + `character_data` (A3/A4).
- **Fixed distinct kinds Race/Class/Background** / **a `category:` field** — rejected for one
  generic Trait-bundle, category = folder (B3).
- **Bake-all** / **hybrid bake-perm + layer-temp** — rejected for unified layers (C1).
- **A DM `update_skill` tool** / **both auto + tool** — rejected; XP auto-on-roll (D1).
- **Fixed additive** / **fixed skill-primary** modifier — rejected for rulebook-weighted (E3).
- **Full sheet in the prompt every turn** / **scene-adaptive projection** — rejected for compact
  projection + identity (F2).
- **Curve/cap in `saga.config.yaml`** — rejected; value → rulebook, only bounds → config (D3).
- **Deferring the mis-keying fix to 0010** — rejected; minimal fix now (H1).

---

## 6. Consequences / risks

- **Positive:** the character system becomes **fully per-world configurable** (matching ADR 0007's
  "maximum configurability") with a single **typed** sheet that ends the free-dict drift and the
  inert-ability bug; the **unified layer model** serves creation bundles, buffs, status (0008-G3)
  and circumstance (0003) with one mechanism + free provenance/reversibility; the **value→rulebook
  / guardrail→config** principle cleanly splits per-world content from global safety; **0003 stays
  agnostic** to the formula, so the two ADRs decouple at `request_dice`.
- **Trade-offs:** a new `rulebook` JSONB column + a three-store read merge (rulebook + baseline +
  overlay); a substantial **frontend** rebuild (dynamic sheet + creation UI, F3); effective-value
  recompute on read (cheap at PG scale); the typed `character_data` adds validation surface.
- **Risks:** the **clean-restart assumption** (no migration) is load-bearing — if saves ever must
  be preserved, the schema decisions need revisiting; designing on a **per-world rulebook** with
  many open numeric TODOs (curves, weights, grants) risks balance drift — mitigated by the
  config guardrail envelope + the growing XP curve + `max_level`; the **0003 dependency** (E4)
  means resolution isn't fully specified until the coordinated 0003 edit lands.

---

## 7. Relationship to other ADRs

- **ADR 0003 (deterministic combat resolution)** — the resolution seam (§E); 0003 needs the **E4
  edit** (sheet-produced modifier, `skill|attribute` id, Power→effect). Implementation order:
  0003 first.
- **ADR 0005 (multi-axis psychology)** — affect/disposition out of scope.
- **ADR 0007 (Voyage directions)** — **parent ADR**; this is its PG-customization spin-off.
- **ADR 0008 (world model)** — owns the container/authoring/storage; the rulebook is a top-level
  collection (A2, per D2b/D3), stored in a frozen column (A3, per C3/C7); the E1/E3 pattern is
  reused (B1); scope is gated on **C5** (A5, multi-scenario).
- **ADR 0012 (active abilities)** — **spun off** from this ADR (§2, §G); shares the rulebook
  Ability kind, the `character_data` store, and the turn-based cooldown unit.

## 8. Notes / sources

`scratch/research/voyage.md` §3bis (**direct in-game observation** 2026-06-22) + §3.6/§4.
Decisions from the 2026-06-23 design interview (all calls by the project owner), grounded in the
live code: `core/dice.py`, `core/dm/dm_tools_executor.py`, `ai/prompts/dm.py`,
`models/campaign.py`, frontend `class-presets.ts` / `character-sheet-parts.tsx`.
