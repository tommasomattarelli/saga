# SAGA v0.1.0-beta.1 — 2026-06-23

First public beta of SAGA — an AI-driven tabletop RPG engine with an AI Dungeon Master, semantic memory, and a living world.

## Highlights

### Gameplay
**Bugfixes**
- Ability scores now affect dice checks — every check previously rolled at a flat +0 regardless of your character's stats.

### Installer
**New**
- Native no-Docker installer for Windows/macOS/Linux: double-click `install_saga.bat` and play. It provisions a portable Postgres+pgvector bundle, builds the app, and creates a desktop shortcut; the database starts and stops with the app.

### UI
**Improvements**
- The action input is capped at 500 characters with a live counter near the limit.

### Internal

#### Added
- ADR 0010 (player-character customization) advanced from a "WIP, nothing decided" stub to
  **Proposed**, via the 2026-06-23 design interview grounded in live code + direct in-game
  observation of Voyage (`voyage.md` §3bis). Defines a **per-world rulebook** (a top-level
  `rulebook/` collection in the World, frozen `rulebook` JSONB column) owning the
  character-system kinds (Attribute/Resource/Skill/generic Trait-bundle, category=folder); a
  **unified modifier-layer model** (one mechanism for creation bundles + buffs/status/
  circumstance); **skill progression** (XP auto-granted on the roll, scaled by outcome tier,
  curve/cap in the rulebook); the **resolution seam with 0003** (`request_dice` reworked to
  carry a world-defined `skill|attribute` id, rulebook-weighted modifier formula, 0003 stays
  agnostic); and a **typed `character_data`** with a compact per-turn prompt projection. The
  cross-cutting principle **value→rulebook / guardrail→config** is recorded. Active abilities
  were spun off to ADR 0012.
- ADR 0012 (active abilities): the player-triggered "special move" system spun off from 0010 —
  player-only trigger (the DM has no `use_ability` tool), cooldown in turns engine-enforced,
  outcome adjudicated by DM+engine (not an auto-effect, so it can't bypass plot protection),
  Power→effect deferred to ADR 0003, ability-point economy a TODO.
- `voyage.md` §3bis: the Voyage **character model** captured from direct in-game observation
  (new `[👁️ IN-GAME]` evidence level) — creation flow + a real Skyrim character sheet
  (world-defined attributes/resources/skills-with-XP, race/class/talent/background modifier
  bundles, active abilities with Power+Cooldown).
- `installer-smoke.yml` workflow (manual `workflow_dispatch` + weekly schedule):
  end-to-end installer smoke on `windows-latest` (provisions the published bundle,
  starts the backend, probes `/`) and `ubuntu-latest` (PGDG apt + the sh installer).
  Kept off the PR path because it is slow and downloads the bundle. Installer
  scripts are organized under `install/windows/` and `install/linux-macos/`.
- Native Windows installer under `install/` (no Docker, no admin): `install_saga.bat`
  bootstrapper (ensures Git, clones) hands off to `install_saga.ps1` (portable
  Node + user-scope uv + a pinned portable Postgres+pgvector bundle, generated
  secrets, `uv sync` + `npm build`, desktop shortcut). `start_saga.ps1` is the
  coupled launcher (Postgres up → backend serving API + SPA → Postgres down on
  exit); `uninstall_saga.ps1` removes everything; `build_bundle.ps1` assembles the
  Postgres+pgvector bundle for maintainers. Consumes the bundle from a configurable
  URL; the published Release asset is a prerequisite to run it end-to-end (ADR 0000).
  Linux/macOS counterparts (`install_saga.sh`, `start_saga.sh`, `uninstall_saga.sh`)
  mirror the flow, sourcing Postgres+pgvector from the OS package manager. CI
  syntax/lint-checks both the PowerShell and the sh scripts; end-to-end smoke is
  deferred until the bundle is published.
- GitHub Actions CI (`.github/workflows/ci.yml`), runs on PR (the push-to-`main`
  trigger was dropped to avoid a duplicate run on merge; `main` is protected):
  backend lint (`ruff check`/`format --check`), type-check (`mypy`) and dead-code
  scan (`vulture --min-confidence 80`) + unit tests; backend integration
  + playtest against a `pgvector/pgvector:pg16` service container; the full
  frontend pipeline (lint, vitest, knip, build); a Docker build smoke; and a
  parse-check of the installer PowerShell scripts. No AI keys are needed — every
  LLM call on the test path is mocked (ADR 0000).
- Backend can serve the built frontend SPA itself (FastAPI `StaticFiles` with an
  index.html fallback for client routes), enabled via `SAGA_FRONTEND_DIST` and
  mounted last so `/api` keeps precedence. Off by default, so dev and Docker
  (Vite dev server) are unaffected — used only by the native installer (ADR 0000).
- ADR 0000 (distribution & deployment architecture): the foundational,
  pre-first-release deployment decision. Two-tier distribution — Docker
  `compose up --build` for technical users, and a native no-Docker casual
  installer (Windows `.bat` first) that provisions a pinned portable
  Postgres+pgvector bundle and serves the built frontend via FastAPI (single
  process, no runtime Node). A single launcher starts/stops Postgres together with
  uvicorn (on-demand, no Windows service, no admin). Backend logic
  unchanged; SQLite/softening pgvector explicitly rejected. CI runs on PR + push
  with a pgvector service container and no AI keys.
- Backend is now `mypy`-clean and type-gated. A `[tool.mypy]` config over `app/`
  (pydantic plugin, `pgvector` import override, `types-PyYAML`/`types-python-jose`
  stubs); provider SDK `list[dict]`↔`TypedDict` boundaries and the pydantic
  `computed_field` limitation use targeted `# type: ignore[code]`, ORM forward-refs
  use `TYPE_CHECKING`. Enforced by a `backend-mypy` pre-push hook and in CI — the
  counterpart of the frontend `tsc` gate. A `vulture` dead-code scan likewise joins
  CI as the backend counterpart of the frontend `knip` gate (0 findings today).
- Frontend E2E golden path via Playwright (`e2e/golden-path.spec.ts`,
  login → campaigns → game) with `/api` mocked in-browser — no backend/Docker
  (F-L9, ADR 0011). A backend-real + Docker variant is deferred.
- Frontend test coverage raised to ~95% (from ~82%): new tests for `NPCBubble`,
  `Typewriter`, `ConfirmModal`, `MoodLayer` + atmospheric overlays, `RegisterForm`,
  `JournalDrawer`, `App` ProtectedRoute redirect, and `SettingsDrawer`.
- Coverage floor in `vite.config.ts` (`thresholds`) as an anti-regression gate,
  ratcheted to 90/82/78/90 (current ~95/85/83/95). Remaining gaps: `client.ts`
  401 interceptor and `turn-block` progressive-reveal branches.
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

#### Removed
- The unused `redis` dependency (no `redis_url` setting, no imports anywhere in
  the app); the stale `REDIS_URL` entry was also dropped from `.env.example`.
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

#### Changed
- The casual installer checks out the pinned release tag (`REF`, default the current
  release; override with `SAGA_REF`) instead of `main` HEAD, so users get the published
  release rather than in-development code (`install_saga.bat` / `install_saga.sh`).
- ADR 0009 (NPC enrichment) expanded from a "WIP, nothing decided" stub to **Proposed**
  via a design interview grounded in the live code. Decided: split the overloaded NPC
  `status` into `lifecycle` `{alive,dead,removed}` (engine-owned) + a DM-owned `condition`
  descriptor, eliminating the redundant `is_dead` reader; `update_npc` as an upsert tool
  that **excludes** disposition (kept with ADR 0005) and gates writes through an exhaustive
  whitelist⊎blacklist partition + an exhaustiveness test; removed-NPC re-entry as a
  `lifecycle` value (no separate archive store). Boundaries drawn to ADR 0002/0005/0006 and
  the previously-silent ADR 0008 seam (`location` address deferred to 0008-J-iii). Surfaced
  that NPC death/removal is currently read-only scaffolding with no writer.
- `Makefile` made cross-platform: detects the OS and uses PowerShell on Windows
  and `sh` elsewhere (the `test-all` env-var injection and `clean` cache removal
  branch per shell). Windows behaviour is unchanged; Linux/macOS contributors can
  now use the same targets. CI does not depend on `make` — it runs explicit steps.
- `docs/AUDIT_APRIL_2026.md` archived to `docs/archive/` now that the whole
  backlog (backend + frontend) is closed/deferred; references in `docs/README.md`
  and `AGENTIC_ARCHITECTURE.md` updated.
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


#### Fixed
- Frontend `tsc -b` (and `npm run build`) build break resolved properly: dropped
  the deprecated `baseUrl` (slated for removal in TS 7.0) and the unused `@/*`
  `paths` alias, so `ignoreDeprecations` is no longer needed at all — future-proof
  for TS 6/7 instead of the earlier `ignoreDeprecations` value juggling.
- Frontend test setup now bootstraps the i18n instance and a `window.matchMedia`
  stub in `setupTests.ts`, unblocking i18n-dependent and `SettingsDrawer`-mounting
  suites (and the V8 coverage reporter that previously crashed on `matchMedia`).
- Stale frontend test assertions realigned to the sprint-2 UI copy (login-form,
  new-campaign, campaign-select, game-view); test-only, components unchanged.
- Recall embedding is now computed before the turn's DB session opens, so no
  embedding API call runs inside an open session (B-M1, rule 15).
