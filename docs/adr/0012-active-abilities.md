# ADR 0012 — Active abilities (player-triggered special moves with cooldown)

- **Status**: Proposed (spun off from **ADR 0010** on 2026-06-23; trigger / ownership /
  cooldown fixed via the design interview; **resolution mechanics, Power semantics and the
  ability-point economy remain explicit TODOs**, may still be revised).
- **Date**: 2026-06-23
- **Context items**: Voyage analysis (`scratch/research/voyage.md` §3bis — **direct in-game
  observation** 2026-06-22); design interview 2026-06-23 (all choices by the project owner);
  grounded in `ai/tools/tools_special.py`, `core/dm/dm_tools_executor.py`, `models/campaign.py`.
- **Scope note**: this ADR owns the **active-ability system** — a player-triggered "special
  move" with a cooldown. It is the sibling of **ADR 0010** (configurable rulebook + skills +
  progression + resolution feed): 0010 owns the attribute/skill core, 0012 owns active
  abilities. The **resolution** of an ability's effect (Power → outcome/damage) is owned by
  **ADR 0003**; this ADR fixes the *invocation* model and defers the *effect math* to 0003.

---

## 1. Context

Voyage exposes (§3bis, observed in-game) **active abilities** distinct from skills: each has a
**Power** (e.g. 8, 6) and a **Cooldown in actions** (e.g. 3 / 10), gated by an **Ability Points**
economy, themed to the character's class/talents (Assassinate, Shadow Step, Shadowcloak…). They
are **special moves**, not narrative-breaking superpowers.

SAGA today has **no ability concept** — `tools_special.py` has only `request_dice` and
`invoke_npc`; there is no player-side action type beyond free-text. Greenfield.

This system was originally being absorbed into ADR 0010 mid-interview; on review it is a
**distinct paradigm** (player-triggered, cooldown, a *new structured input path*, an ability-point
economy) and was **spun off here** by decision, consistent with SAGA's ADR-boundary discipline
(world → 0008, affect → 0005, off-screen → 0006).

---

## 2. Decisions

> Legend: **Decided** / **TODO**.

- **A1 — Ability is a rulebook kind (Decided).** Defined per-world in the 0010 rulebook,
  following the 0010-B1 pattern (typed core + E1/E3): `{id, name, description(flavor), power,
  cooldown, cost?(resource ref), granted_by}`. Lives in the same frozen `rulebook` store
  (ADR 0010-A3).
- **A2 — Player-only trigger; the DM has NO `use_ability` tool (Decided — the crux).** An
  ability is invoked **only** by the player (a UI toggle, like a video-game ability button).
  The DM **cannot** fire abilities — there is no `use_ability` tool in the DM's set, so the LLM
  never decides to deploy a special move. The engine enforces **cooldown + cost** at invocation.
  Rejected: a DM-invokable ability tool (hands special moves to the model; breaks the
  player-agency framing).
- **A3 — The OUTCOME is adjudicated by DM + engine, not an auto-effect (Decided — resolves the
  applicability/gating gap).** The **trigger** is deterministic/player-only; the **outcome**
  (does it land, damage, narration) is resolved **normally** (DM narration + engine rules), so
  an ability **can fail** and **cannot bypass** narrative plausibility or plot protection — the
  normal resolution **is** the gate. *"Special move, not superpower."* This is the abilities
  counterpart of 0010's "skill: DM arbitra". The exact effect math (Power → outcome/success) is
  a **TODO coordinated with ADR 0003**. Rejected: a guaranteed deterministic effect that the DM
  merely narrates (would let a player auto-kill a plot-critical NPC / teleport out of a sealed
  room — even Voyage gates this, §3.9).
- **A4 — Cooldown in turns/actions (Decided; from 0010-D5).** `cooldown_remaining` ticks down
  **each player turn**; using an ability **is** a turn. The engine **rejects** a use that is on
  cooldown with a structured error (`{error: ability_on_cooldown, remaining: N}`, std 6/13,
  F7-style). Cooldown state is stored in `character_data` (0010-A4) and ticked engine-side.
  Rejected: cooldown in game-time minutes (a long `advance_time` would reset combat cooldowns —
  unnatural); per-ability unit (deferred; two tick paths).
- **A5 — Abilities are granted by bundles and/or ability-point unlock (Decided direction).**
  `grants_abilities` on Trait-bundles (0010-B3) grant abilities at creation; an **ability-point
  economy** can unlock/upgrade more. The ability-point earn/spend rules are a **TODO**, linked
  to the character-level-up effect (0010-G, soft TODO).
- **A6 — An ability may cost a resource (Decided).** `cost` references a Resource (0010-B4);
  the engine deducts it at invocation (alongside the cooldown gate).

**Consequence — a new structured player-input path.** Ability use is a **player input type**
distinct from free-text action (API + frontend): the player toggles an ability → the backend
validates cooldown/cost (+ applicability, A3) → the DM narrates the resolved result. The frontend
may grey out on-cooldown abilities for UX, but the **backend is the authority**.

**TODO (0012):** `Power → effect/success` model (coordinate ADR 0003); the **ability-point**
earn + spend rules (coordinate 0010-G); the **input-path** API/FE shape; how an ability
**targets** (and the applicability checks that back A3).

---

## 3. Decided vs Open

**Decided:** A1–A6 (+ the new-input-path consequence).

**Open TODOs:** Power/effect resolution (→ 0003); ability-point economy (→ 0010-G); the
structured-input API + frontend; ability targeting + applicability gate.

---

## 4. Rejected alternatives

- **A DM-invokable `use_ability` tool** — rejected; player-only trigger (A2).
- **A guaranteed deterministic effect the DM only narrates** — rejected; the outcome is
  adjudicated (A3), so abilities can't break the narrative / plot protection.
- **Cooldown in game-time minutes** / **per-ability unit** — rejected for turn-based (A4).

---

## 5. Relationship to other ADRs

- **ADR 0010 (player-character customization)** — **parent**; the Ability kind, the frozen
  `rulebook` store, the `character_data` cooldown state, and the turn-based unit all come from
  0010. Ability-point ↔ 0010-G (char level-up).
- **ADR 0003 (deterministic combat resolution)** — owns `Power → effect/outcome` (A3 TODO);
  0010-E4 already lists the Power→effect ask to 0003.
- **ADR 0007 (Voyage directions)** — grand-parent direction (PG customization).

## 6. Notes / sources

`scratch/research/voyage.md` §3bis (direct in-game observation 2026-06-22). Decisions from the
2026-06-23 interview (all calls by the project owner), grounded in `ai/tools/tools_special.py`,
`core/dm/dm_tools_executor.py`, `models/campaign.py`.
