# Changelog

All notable changes to SAGA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This log is curated by hand — it is not a dump of `git log`. Add entries under
`[Unreleased]` as you work; on release, replace `[Unreleased]` with the version
and date and open a fresh `[Unreleased]` on top. Historical session/sprint notes
predating this file live in `docs/archive/changelog/`.

## [Unreleased]

### Changed
- The `data-theme` forcing effect duplicated across four pages
  (game-view, campaign-select, new-campaign, auth) collapsed into a single
  `useForcedTheme` hook that restores the previous theme on unmount (R-03).
- Redundant types/casts dropped: the `CampaignWithClass` intersection (the base
  `CharacterData` already carries `archetype`) and the inline companion cast in
  `CompanionBar` (`world_state.companions` is already typed `CompanionData`) (R-05, R-08).
- `ActionInput` gained a client-side length guard: native `maxLength` caps the
  textarea at 500 chars with a live counter near the limit (F-M4); the unused
  `campaignId` prop was dropped (R-10). Backend `sanitize_player_input` remains
  the authoritative guard.
- `NarrativeStream` (338 lines) split into `player-action.tsx`, `turn-block.tsx`
  (segment + progressive dice-reveal logic) and a thin `narrative-stream.tsx`
  shell (81 lines, rule 12). Stale tests realigned to current copy; `DmLoading`
  given a `data-testid` so the loading state asserts on the component, not its
  rotating flavour text (F-M7).
- `CharacterSheet` split: presentational body + `StatSigil`/`HpBar` extracted to
  `character-sheet-parts.tsx`, dropping the component from 306 to 88 lines (rule 12).
  Ability sigils now derive from the character's own `abilities` map, including
  non-core entries, instead of a hardcoded six-stat list (F-L3); redundant
  `Record<string, number>` casts dropped.
- Documentation synced to the post-refactor reality: root `README.md` and
  `docs/AGENTIC_ARCHITECTURE.md` corrected — turn transport is REST+JSON (not SSE/WebSocket),
  Redis removed, embedding dimension fixed to 384, and resolved audit items (god-file split,
  dead-code removal, DB session lifecycle A-3, security hardening) reframed from
  "planned / known violations" to done.
- DM prompts (`BASE_DM_PROMPT`, `DEATH_MODE_PROMPTS`) externalized to
  `app/ai/prompts/dm.yaml`; assembly logic stays in Python, output unchanged (B-M6).
- `build_context()` split into focused helpers (`_load_history`,
  `_load_batch_summaries`, `_recall_memories`); behaviour unchanged (B-M5).
- Documentation and contribution conventions established: hand-curated
  `CHANGELOG.md`, append-only ADRs in `docs/adr/`, a `docs/README.md` index, and a
  Session Protocol + Commit Convention in `CLAUDE.md`. `CLAUDE.md` rules
  restructured into behavioral principles + numbered engineering standards.
  Market/production research moved to `docs/archive/research/`.
- Unit tests reorganized into `app/`-mirroring subpackages
  (`tests/unit/{api,ai,core,memory,security,services}/`); pure relocation, no
  logic change. Legacy `test_pr2_*`/`test_pr3_*` names dropped for descriptive ones.
- ADR 0008 (world model) expanded from a WIP direction-stub into a detailed
  `Proposed` design record, via a design interview + a research pass (6 OSS engines,
  online prior art, adversarial validation). Fixes the hierarchy/node model,
  spatial+route-graph travel, the World-asset-vs-save split (`world_baseline` /
  `world_overlay`), the per-kind parameter model, living-world seeds, and the in-game
  editor; open TODOs catalogued. Research kept locally in `scratch/research/`.

### Added
- Frontend E2E golden path via Playwright (`e2e/golden-path.spec.ts`,
  login → campaigns → game) with `/api` mocked in-browser — no backend/Docker
  (F-L9, ADR 0011). A backend-real + Docker variant is deferred.
- Coverage floor in `vite.config.ts` (`thresholds`: 80/80/70/80) as an
  anti-regression gate; current frontend coverage is ~82/84/73/82.
- Zustand stores (`game`, `auth`, `ui`) wrapped in the `devtools` middleware,
  gated on `import.meta.env.DEV` (F-L2). `ThemeOverride` is now exported once from
  `ui-store` and imported by `settings-drawer` instead of being re-declared (R-12).
- ADRs 0007-0010 from the Voyage (Latitude/AI Dungeon) competitive analysis:
  adopted directions in 0007 (hybrid state-audit pass — not full two-pass — and
  maximum configurability of memory + per-subsystem models); WIP direction-setting
  records for the multi-layer YAML world model + in-game editor (0008), NPC
  enrichment (0009), and player-character customization (0010). 0009-0010 are WIP
  (nothing decided, pending deep analysis); the source analysis is kept locally in
  `scratch/research/`. (0008 has since been expanded — see Changed.)
- Integration tests for the player-action endpoint's previously untested paths:
  DM-graph failure → clean 500 with no half-written turn, missing/inactive
  campaign guards, dice-roll flattening, and the background helpers'
  commit/error-swallow behaviour (`turns.py` coverage 80% → 99%).
- ADRs 0002-0006 from the multi-repo research session (NeverEndingQuest + 6 OS
  projects): relationship graph + recall enrichment, deterministic combat
  resolution (fixed thresholds + server-side damage + symmetric enemy/hero),
  dm_core/game_system separation, multi-axis NPC psychology, and the v2.5 AI
  Director layer. All `Proposed` (direction-setting, pre-implementation).
  `TODO.md` restructured with the derived backlog (keepers, fork follow-ups,
  deferred secondaries).

### Fixed
- Frontend `tsc -b` (and `npm run build`) restored: `tsconfig.json`
  `ignoreDeprecations` was set to the invalid `"6.0"` for TS 5.7 → `"5.0"`.
- Frontend test setup now bootstraps the i18n instance and a `window.matchMedia`
  stub in `setupTests.ts`, unblocking i18n-dependent and `SettingsDrawer`-mounting
  suites (and the V8 coverage reporter that previously crashed on `matchMedia`).
- Stale frontend test assertions realigned to the sprint-2 UI copy (login-form,
  new-campaign, campaign-select, game-view); test-only, components unchanged.
- Recall embedding is now computed before the turn's DB session opens, so no
  embedding API call runs inside an open session (B-M1, rule 15).

### Removed
- Contract-orphaned frontend code removed (cross-stack audit): the
  `suggested_actions` turn field + its "Possibilities" chip UI (backend hardwires
  `None`, never emitted), and the `"companion"` `CombatantInfo` type variant
  (backend combat only emits `player`/`enemy`). `archetype` was checked and
  **kept** — the FE-supplied value is persisted verbatim by the backend and drives
  the campaign book-spine colour.
- Frontend unused dependencies dropped: `@radix-ui/react-popover`, `clsx`,
  `lucide-react` (zero imports in `src/`).
- Frontend dead API/type surface removed: unused `schemas/campaign.ts`, the
  never-called save/settings/export client functions (`getSaves`, `createSave`,
  `loadSave`, `getSettings`, `updateApiKeys`, `exportCampaign`) and the orphaned
  `SavePoint` interface.
- Frontend module-private symbols un-exported (`CLASS_SPINE_COLORS`, `AuthLabel`,
  `ClassPreset`, `clampPercent`, `JournalTurn`, i18n default), unused `abilityModNum`
  helper deleted, narrowing each module's public surface to what is actually imported.
- Frontend `schemas/turn.ts` sub-schemas un-exported (only `TurnResponseSchema`
  is consumed externally); unused `TurnResponseParsed` and `DeathEvent` types removed.
- `Modal` un-exported (used only internally by `ConfirmModal`). Frontend `knip`
  now reports zero unused files/exports/dependencies.
- Dead `diceAnimationEnabled` wiring removed (ui-store field/setter, dice-roller
  branch, `saga.config.yaml` key): the F-L4 toggle was never given a UI control, so
  the setter had zero callers and the skip-animation branch was unreachable. Dice
  animation is now unconditional; re-add with a real settings toggle when wanted.
- Residual function-level dead code: `ProcessedTurn`/`StreamEvent`
  (`core/engine.py`, pre-LangGraph leftovers), `get_user_campaigns`/
  `get_active_campaign` (`services/campaign_service.py`), and `register_provider`
  (`ai/providers/base.py`) — all with zero callers.
- Stale WebSocket integration tests (`test_websocket_sync.py`): the WS transport
  was replaced by REST, and the tests only asserted tautological status codes.
- Dead config fields with zero readers (`config.py` + `.env.example`):
  `cloudflare_r2_*`, `app_mode`, `default_language`, `telemetry_enabled`.

### Security
