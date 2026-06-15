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

### Added
- ADRs 0007-0010 from the Voyage (Latitude/AI Dungeon) competitive analysis:
  adopted directions in 0007 (hybrid state-audit pass — not full two-pass — and
  maximum configurability of memory + per-subsystem models); WIP direction-setting
  records for the multi-layer YAML world model + in-game editor (0008), NPC
  enrichment (0009), and player-character customization (0010). 0008-0010 are WIP
  (nothing decided, pending deep analysis); the source analysis is kept locally in
  `scratch/research/`.
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
- Recall embedding is now computed before the turn's DB session opens, so no
  embedding API call runs inside an open session (B-M1, rule 15).

### Removed
- Residual function-level dead code: `ProcessedTurn`/`StreamEvent`
  (`core/engine.py`, pre-LangGraph leftovers), `get_user_campaigns`/
  `get_active_campaign` (`services/campaign_service.py`), and `register_provider`
  (`ai/providers/base.py`) — all with zero callers.
- Stale WebSocket integration tests (`test_websocket_sync.py`): the WS transport
  was replaced by REST, and the tests only asserted tautological status codes.
- Dead config fields with zero readers (`config.py` + `.env.example`):
  `cloudflare_r2_*`, `app_mode`, `default_language`, `telemetry_enabled`.

### Security
