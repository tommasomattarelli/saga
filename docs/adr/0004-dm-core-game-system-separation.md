# ADR 0004 — DM core vs game system; per-campaign tone & overrides

- **Status**: Proposed (direction 2026-06-09; expanded in place by the 2026-07-13 design
  pass — every fork closed by owner interview, re-anchored on what 0003/0010 already
  decided. Flips to Accepted after implementation + playtest. S1 has **no gate**; S2 is
  sequenced after the 0003 implementation.)
- **Date**: 2026-06-09; design pass 2026-07-13.
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork C; owner
  interview 2026-07-13. Absorbs the `prompt-as-yaml` backlog line as its S2 vehicle.

Legend: **Decided** = settled by owner. **Refined** = shape fixed, exact values/wording at
implementation. **TODO** = consciously open.

## 1. Context

The June draft assumed the "game system" lived in the prompts and could be factored into a
loadable module. The 2026-07 design passes changed the substance under it (grounded
2026-07-13):

- **The mechanical system became engine + data.** Resolution is engine-side (0003: 6
  literal difficulty levels, fixed bands, statblocks — the `dm.yaml:46` "DC guide
  10/15/20/25" is already obsolete by design); content rules (skills, items, abilities,
  npc/shop classes) live in **world-defined rulebooks** (0010/0015). There is nothing left
  for a "loadable system module" to hold.
- **Tone half-exists.** Four authored `PERSONA_PRESETS` (grimdark/heroic/dark_fantasy/
  horror), per-campaign `persona_preset` + free `persona_xml` columns, and worlds shipping
  their own persona (`scenario.dm_persona` → `campaign_service.py:59`). The draft's numeric
  knobs (darkness/pacing/lethality/magic) never existed.
- **`dm.yaml` is one blob**: ~90% universal GM craft + hand-written tool obligations
  (several already scheduled to die with 0003: `start_combat`/`end_combat`/`apply_damage`)
  + `death_mode_prompts` that 0003 explicitly folds into campaign difficulty. `npc.py`
  prompts are inline Python (the prompt-as-yaml TODO).
- No `config_override`, no `writing_style_notes` columns exist.

## 2. Decisions

### A. Ambition — the system IS engine + rulebook (Decided)

Acknowledge the new reality instead of building the module the draft imagined: the "game
system" is the 0003 engine (d20, 6 levels, bands — config-tuned) plus the 0010/0015 world
rulebooks (data). What 0004 owns is the **prompt-layer factoring**: the DM prompt becomes a
composition —

```
<dm_core>   universal GM craft (yaml): no player-puppeting, prose rules,
            momentum, passive turns, language mirroring — system-clean
<engine>    generated: tool obligations composed from the ACTIVE tool groups
            (each tool/group carries its co-located obligation snippet),
            0003 contracts (6 levels, advantage) — never hand-duplicated
<flavor>    persona (preset | custom | world-shipped) + <style> + world blocks
```

Multi-TTRPG stays an honest **predisposition** (clean prompts + rules-as-data keep the door
open at zero cost), not a porting contract nobody exercises. Rejected: *full `game_system`
porting contract* (dice convention/health model as a loadable spec — 0003 already hardwired
d20 in the engine; a speculative contract with zero consumers is guaranteed wrong);
*dropping the multi-system ambition* (closing a door that costs nothing to keep open).

### B. Tone = personas + writing style, no numeric knobs (Decided)

Three of the draft's four knobs already have owners: **lethality** → campaign difficulty +
`death_mode` (0003); **magic prevalence** → world authoring (a low-magic world is low-magic
by content, not by slider); **darkness** → exactly what personas do in prose. The remainder
(pacing, verbosity, register) becomes a new nullable **`writing_style_notes`** column,
injected as a `<style>` block ("tight pacing, short paragraphs, no baroque adjectives") —
prose style is deliberately kept out of the persona (world-voice ≠ prose rules). Numeric
knobs are **rejected**: they duplicate existing owners and can contradict the persona in
the same prompt (grimdark persona + `darkness: 1`); each knob is wording to tune × values ×
languages. The draft's `system_prompt_addendum` is **dropped as redundant** — `persona_xml`
already is the free per-campaign injection (verified: composed before `<instructions>`).
Composition: persona and style always compose (never either/or); world-shipped persona
lands in `persona_xml` at creation and user edits override it (existing behavior, kept).

### C. Per-campaign `config_override`: whitelisted JSONB (Decided)

New nullable `campaigns.config_override` column, merged with precedence **campaign > yaml >
defaults** (mirrors the router hierarchy). Guardrails:

- **Explicit whitelist** of overridable gameplay paths (starts small, grows on demand:
  `director.enabled`, `director.every_turns`, `recall.limit`, `party_autonomy`, commerce
  numerics…). Key outside the list → structured 422 at write (std 6). Engine invariants
  (0003 clamps/bands) and anything security-adjacent are never whitelisted.
- **Merge is a pure per-request function** — the shared/cached global config loader is
  never mutated (no cache poisoning).
- **Re-validated on campaign import** against the current whitelist — lapsed keys dropped
  + logged.

This is 0007-§2's "max configurability **with mandatory guardrails**" applied per-campaign.
Rejected: *free merge* (campaign-overridable engine invariants); *YAGNI deferral* (the
Director/party/recall knobs are exactly the per-campaign wishes already designed —
deferring means designing this again in three months).

### D. Factoring mechanics & sequencing (Decided)

- **D1** — the `prompt-as-yaml` backlog line is absorbed here as the S2 vehicle: every
  prompt (incl. inline `npc.py`) moves to yaml files in one prompts directory.
- **D2** — tool obligations are **generated from the active tool groups** (dynamic
  `tool_groups` already exist): each tool/group carries its obligation snippet co-located
  with its definition, composed in **deterministic order** (provider prompt-cache
  friendly). Hand-written obligation prose in the blob goes away — it desyncs at every
  tool churn. Exact snippet wording Refined (and rewritten by 0003's implementation
  anyway).
- **D3** — `death_mode_prompts` belong to 0003 (folded into difficulty); 0004 does not
  touch them.
- **D4 — sequencing (binding)**: S2 (prompt factoring) lands **after the 0003
  implementation** — 0003 rewrites half the blob (DC guide, combat obligations, death
  prompts); factoring first would mean rewriting twice. S1 (tone + override) is standalone
  and ungated.
- Length caps (config) on `persona_xml` / `writing_style_notes` — free system-prompt
  injection is bounded; posture note: self-hosted single-user, the player IS the author
  (the world-zip persona surface pre-exists this ADR).

## 3. Decided vs Open — quick index

**Decided**: A (factoring, no porting contract), B (personas + `writing_style_notes`, no
knobs, addendum dropped), C (whitelisted `config_override`, pure merge, import
re-validation), D1-D4.
**Refined**: whitelist v1 exact list, snippet wording, `<style>`/`<dm_core>` block shapes,
length-cap values.
**TODO**: none open beyond Refined — the multi-TTRPG door is a stance, not a work item.

## 4. Rejected alternatives (with reasons)

- **Loadable `game_system` module / porting contract** — superseded in substance by 0003
  (engine) + 0010 (rulebook data); speculative spec with no consumer.
- **Numeric tone knobs (darkness/pacing/lethality/magic)** — three of four have owners
  (0003 difficulty, world authoring, personas); knob-vs-persona contradictions in one
  prompt; wording surface × values × languages.
- **`system_prompt_addendum`** — redundant with the existing `persona_xml` free injection.
- **Free config merge** — engine invariants and sensitive keys must not be
  campaign-overridable.
- **Deferring config_override (YAGNI)** — the per-campaign knobs it serves are already
  designed (0006/0014/0002); deferral = same design later.
- **Dropping multi-TTRPG** — keeping prompts system-clean costs nothing.

## 5. Consequences

- **Positive**: campaigns get tonal identity through one coherent language (authored
  prose: persona + style) instead of two competing ones; per-campaign tuning becomes safe
  by construction (whitelist); prompt content stops desyncing from the tool registry;
  every prompt becomes data (yaml), which the tuning pass (dedicated TODO) will thank;
  multi-TTRPG stays possible for free.
- **Trade-off**: two more campaign columns (nullable — no rung, no save breakage) and one
  more merge point in the config path (pure, tested).
- **Trade-off**: obligation snippets add structure to tool definitions — every new tool
  must ship its prompt snippet (a discipline, but the alternative is the current blob
  drift).
- **Trade-off**: S2 waits on 0003's implementation — accepted to avoid double rewrite.

## 6. Relationship to other ADRs

- **0003** — owns resolution contracts and the death/difficulty prompts; S2 factoring
  composes *around* what its implementation writes; the obsolete DC guide dies there.
- **0007 §2** — config_override is its "max configurability with guardrails" applied
  per-campaign; the whitelist is the guardrail.
- **0010/0015** — rulebooks are the data half of the "system"; nothing here duplicates
  them.
- **0006/0014/0002** — their per-campaign knobs (`director.*`, `party_autonomy`,
  `recall.*`) are the whitelist's first customers.
- **Prompt tuning pass (TODO)** — tuning operates on the factored yaml blocks this ADR
  produces; it is content work, explicitly not this ADR's scope.

## 7. Implementation plan (fixed)

- **S1 — Tone + override (no gate).** Migration: `writing_style_notes` +
  `config_override` (nullable); whitelist validation + structured rejects; pure merge
  function (campaign > yaml > defaults) + tests on precedence; `<style>` block injection;
  addendum concept retired (no column ever existed); import re-validation; length caps;
  minimal UI (two text fields + settings panel).
- **S2 — Prompt factoring (after 0003 implementation).** `dm_core` yaml split (system-
  clean wording pass); obligation snippets co-located with tools/groups + deterministic
  composition from active groups; `npc.py` → yaml; single prompts directory; regression:
  composed prompt equivalence tests per tool-group combination.

## 8. Notes / sources

Survey sources (2026-06-09): open-tabletop-gm SKILL.md/system.md split, aidm DNA axes,
ai_rpg writing_style_notes. Design pass grounded in code (presets.py, campaign model,
dm.py persona composition, campaign_service.py:59 world persona, dm.yaml blob,
tool_groups.py) — no external validation needed; every fork resolved on first principles
against the 0003/0010 decisions that ate the draft's original subject.
