# ADR 0013 — Frontend visual redesign: clean modern dark (Voyage-informed, own identity)

- **Status**: Accepted (2026-07-06, after Sprint 1 + Sprint 2 owner sign-off).
- **Date**: 2026-07-04
- **Context items / sources**:
  - `scratch/ui-map/01-04` — 4 current-state UI maps (design system, onboarding, play screen, narrative/combat) + bug lists, reconciled against real screenshots by a prior agent pass.
  - `scratch/research/ui-redesign.md` — font pairing, dark-mode a11y checklist, bespoke dice concepts.
  - `~/Schermate` — SAGA screenshots + **Voyage** (Latitude/AI Dungeon) reference screenshots.
  - Foundation already landed: commit `750a2ac` (dark neutral tokens + system fonts).

## Context

The current UI — "Grimoire / Illuminated Parchment" — is both a **usability liability** and a **defect surface**. The ui-map pass documented, against real renders: near-invisible login inputs (all hairlines on `--gold-deep`, dark-on-dark), a **semi-transparent character modal** bleeding the game screen through it, illegible ability scores, an **orphan red bar** on the play screen, a **dead Settings theme picker**, cryptic unlabeled toolbar icons, and a polarizing **archaic voice** ("What dost thou do?", "Word of Passage"). The owner rejects the *direction itself* — not only the execution — as alienating and "strange", and the UI is the single thing an end user perceives: a strange or illegible UI loses users regardless of engine quality.

Decision: **redesign to a clean, modern, broadly-palatable dark UI**, informed by **Voyage** (Latitude's AI RPG — a direct competitor doing exactly this well) but with **SAGA's own identity**. This is a **re-skin on the existing tokenized React architecture, NOT a rewrite**: routing, auth, state stores, API client, component decomposition, responsive work and test coverage are assets to keep. The token system (`tokens.css` + `tailwind.config.ts` mapping Tailwind classes through CSS custom properties) means changing token *values* moves most screens at once.

## Decisions

Legend: **Decided** · **Refined/TODO** (settled in the build).

### A. Direction & approach
- **A1 (Decided)** — Pivot away from the Grimoire identity → clean modern dark, Voyage-informed, own identity.
- **A2 (Decided)** — **Dark-only.** Drop the light theme, the per-screen `useForcedTheme` hardcoding (`campaign-select`/`new-campaign`/`auth` = dark, `game-view` = light), and the non-functional Settings theme picker (`data-theme-override`, set in `App.tsx:132-134`, consumed by no stylesheet — ui-map §7). Reversible later via tokens.
- **A3 (Decided)** — Re-skin on the existing token system, not a rewrite.
- **A4 (Decided)** — Adopt Voyage-style **game chrome** (owner-named): serif narration + sans UI; labeled icon **pills** (Character / Journal / Settings / Map / Chat); character **avatar with level bar**; **color-coded speaker names**; **turn dividers**; **tabbed character modal** (Stats / Inventory / Skills / Traits / Abilities); big **input pill**; campaign **card grid** (retire the "Shelf of Tales" book-spine metaphor).
- **A5 (Decided)** — Build sequencing: **vertical slice first** (the play screen) → owner sign-off → propagate the approved patterns to the other screens.

### B. Foundation (tokens / fonts)
- **B1 (Decided)** — Fonts: `@fontsource-variable/newsreader` (serif, narration — opsz axis, built for on-screen reading) + `@fontsource-variable/instrument-sans` (sans, UI — weights 400-700, no accidental thin text on dark). **Self-hosted / bundled, no CDN** (drops the Google Fonts `<link>`; offline-safe, fits self-host). Backup: Source Serif 4 + Inter.
- **B2 (Decided)** — Neutral near-black palette per the a11y checklist: never pure black/white; bg ~`#121212–#1a1a1a`, text ~`#e0e0e0–#f0f0f0`; body ≥4.5:1 (aim 7:1 for long reads), UI/large ≥3:1; serif weight ≥400 on dark; reading measure 60-75ch; line-height 1.5-1.65. `750a2ac` landed starting values; final palette refined in build.
- **B3 (Decided in build)** — Accent/signature: **verdigris `#8fb8ac`** (bright variant `#a9cec2`) — a desaturated oxidized-bronze green, ink-like rather than neon; picked by the owner over slate indigo after two mock rounds (first round teal/violet rejected as glowing "AI-slop"). Used sparingly: active nav, dice tier/verdict, primary action. Wired as `--accent`/`--accent-bright` with `--gold`/`--gold-bright` kept as aliases.

### C. Atmosphere
- **C1 (Decided)** — **Strip it.** Remove the film-grain noise overlay, the vignette, and the 3D page-turn route transition; mood-layer off (or reduced to a near-invisible tint). Reversible if a touch is missed later.

### D. Voice & i18n
- **D1 (Decided)** — **English-first, plain modern voice.** Re-voice the English copy (drop archaisms), and route hardcoded strings (e.g. `action-input.tsx` "What dost thou do?") through i18n. **Keep the i18n layer and the `it` locale** (Italian translation pass deferred — see debt below). Default language = English.

### E. Dice (the signature)
- **E1 (Decided in build)** — **Tier arc**, plain (no crit split-flap): a slim inline gauge of the 6 outcome tiers; click Roll → marker sweeps and lands on the outcome tier; raw roll + verdict beneath; success lands accent, failure blood; crits get typographic weight only. Owner-picked over ink-stamp card and "tier arc + split-flap on crits" mocks. Calm, always-legible, CSS-cheap, no full-screen interrupt.

### F. Brand mark
- **F1 (Decided)** — Clean "SAGA" **wordmark** in the new sans; retire the ornate SagaSeal (which also carries a near-black rendering bug).

### Bugs this redesign closes (from ui-map)
Invisible login inputs · semi-transparent character-modal layering · illegible stats · orphan red bar (`CompanionBar` `bg-red-600` + legacy Tailwind palette) · dead theme picker · cryptic unlabeled toolbar icons → labeled pills.

## Decided vs Open

- **Decided**: A1–A5, B1–B2, C1, D1, F1; B3 (verdigris `#8fb8ac`) and E1 (tier arc) settled in the build.
- **Out of scope / parked**: the **player-input-as-inspiration** gameplay model (raised during this interview — the DM reframes the player's action as an *attempt* with an always-uncertain outcome, input as inspiration not truth) → **its own future ADR**; it conflicts with the backlog's "WorldBuilder accept-not-reject / player co-author" direction and is a gameplay-mechanics call, not a UI one (closest existing: ADR 0003). Also parked: the **`getTurns` empty-render** functional bug (a 4-turn campaign renders the zero-turns empty state because the turns fetch no-ops silently and its error is never surfaced) — a data/fetch fix, adjacent but separate.

## Rejected alternatives

- **Keep-and-fix the Grimoire identity** (just fix contrast + bugs) — rejected: the owner rejects the *direction* (archaic voice, heavy fantasy), not only the execution; a contrast pass wouldn't cure the alienation.
- **Full rewrite from scratch** — rejected: discards the good, expensive-to-rebuild architecture (routing/auth/state/API/tests) to change what is mostly skin + copy; a re-skin reaches the same visible outcome at a fraction of the cost and risk.
- **Keep the light theme / a real theme toggle** — rejected: owner wants dark ("schermo nero"); the current theme system is half-broken (dead picker + per-screen forced theme); dark-only is a genuine simplification. Reversible later.
- **Clone Voyage closely** — rejected for "inspired, own identity" (own cool accent, own fonts, bespoke dice) to avoid being derivative of a competitor.
- **Inter as the UI sans** (research backup) — rejected for Instrument Sans, a touch more character than the ubiquitous default.
- **Figma / Figma-MCP mockups first** — rejected: no dedicated designer, direction already decided, a real tokenized app exists; iterating in real code with headless-screenshot verification is faster and higher-fidelity. HTML/Artifact mocks cover any "explore a wild direction" need.

## Consequences

**Positive**: a legible, broadly-palatable, modern dark UI that fixes the documented defects; keeps the architecture + tests; offline-safe self-hosted fonts; a simpler single-theme system (removes `useForcedTheme` + the dead picker); a distinctive-but-not-strange identity (own cool accent + bespoke dice).

**Trade-offs / risks**:
- **Tests (std 11)**: ADR 0011's mocked golden-path E2E and the component tests key off DOM structure / classes / copy — the redesign will break selectors and text assertions; they must be updated in lockstep.
- **i18n debt**: the `it` locale falls behind under English-first; needs a translation pass before Italian is shippable.
- **Reversibility**: re-adding a light theme later means repopulating token theme overrides + a real picker.
- **Bundle**: self-hosting two variable fonts adds asset weight (acceptable; variable fonts are compact and offline is a feature).
- **Scope**: a full-app re-skin is large; the vertical-slice-first sequencing (A5) contains it and provides an approval gate.

## Relationship to other ADRs

- **ADR 0007 (Voyage-adopted directions)** — adopts Voyage's *backend/architecture* directions (state-audit pass, configurability, turn-editing). THIS ADR adopts Voyage's *UI/visual* language. Complementary, distinct scope; neither supersedes the other.
- **ADR 0011 (frontend E2E: mocked golden path)** — impacted (selectors/copy change); not superseded; tests updated as part of the build.
- **ADR 0010 (PC customization) / 0012 (active abilities)** — the character sheet + abilities UI are touched here; the new tabbed character modal + abilities panel must accommodate them (Voyage's Abilities panel is a good reference).

## Notes

Sources: `scratch/ui-map/01-04`, `scratch/research/ui-redesign.md`, `~/Schermate` (SAGA + Voyage screenshots). Foundation started in `750a2ac`. Work proceeds on branch `redesign/ui-dark-a`.
