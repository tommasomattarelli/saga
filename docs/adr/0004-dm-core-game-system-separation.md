# ADR 0004 — Separate DM core from game system; per-campaign tone

- **Status**: Proposed
- **Date**: 2026-06-09
- **Context items**: Research session 2026-06-09 (NEQ + 6 OS repos) — Fork C

## Context

SAGA's GM behaviour and its D&D-specific rules are entangled: dice/resolution,
stat assumptions, and "how to be a good DM" all live mixed in the prompts
(`app/ai/prompts/`) and tool layer. Two limitations:

1. **Single-system lock-in.** Supporting another TTRPG (Pathfinder 2e, VtM,
   Cyberpunk) would mean forking prompts and tools, not adding a module.
2. **Fixed tone.** Every campaign runs the same narrative register. There's no
   per-campaign knob for darkness, pacing, lethality, magic prevalence, or prose
   style, and no place to inject homebrew framing.

open-tabletop-gm separates a system-agnostic GM persona (`SKILL.md`) from a
loadable `system.md` rulebook, with a minimal porting contract (dice convention,
ability scores, health model, primary resource, conditions). aidm parameterises
*tone* via numeric DNA axes mapped to textual directives; ai_rpg exposes
`writing_style_notes` / preamble and a per-game config override.

## Decision

1. **`dm_core` vs `game_system`.** Factor the DM into universal GM principles
   (`dm_core` — pacing, fairness, narration craft; system-agnostic) and a
   **loadable `game_system`** holding the rules (dice convention, stats, health,
   resources, conditions, advancement). D&D-like ships as the reference system;
   the contract is deliberately minimal so a new system can start with the five
   core mappings and iterate. This predisposes SAGA for multi-TTRPG without
   committing to porting any specific system now.
2. **Per-campaign tone parameters.** A small set of campaign-level knobs
   (darkness / pacing / lethality / magic, ~5-8) injected into the DM prompt as
   textual directives. The `game_system` stays fixed (D&D-like); only the *register*
   varies per campaign. Defaults in `saga.config.yaml` (std 14).
3. **Per-campaign overrides.** `system_prompt_addendum` and `writing_style_notes`
   fields on the campaign, plus a `config_override` (JSONB) merged over
   `saga.config.yaml` at campaign load — so a campaign can tune knobs and add
   homebrew framing without touching global config.

## Consequences

- **Positive**: multi-system becomes an additive module, not a fork; campaigns
  gain tonal identity and homebrew framing at low cost; tone/override are
  config-first and per-campaign.
- **Trade-off**: a refactor of the prompt/tool layer to honour the core/system
  split — real work, sequenced after the combat (ADR 0003) and NPC (ADR 0005)
  changes that touch the same rules surface.
- **Trade-off**: more configuration surface (global + per-campaign override).
  Mitigated by a documented precedence order (campaign override > global yaml >
  defaults) mirroring the existing router override hierarchy.

## Notes

The `game_system` contract aligns with ADR 0003: dice convention + health model
are exactly the deterministic pieces being formalised there. Multi-system is the
long-horizon payoff; the immediate, shippable slice is the per-campaign tone
parameters + overrides, which stand alone even if multi-system never ships.
