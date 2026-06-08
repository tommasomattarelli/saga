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
- DM prompts (`BASE_DM_PROMPT`, `DEATH_MODE_PROMPTS`) externalized to
  `app/ai/prompts/dm.yaml`; assembly logic stays in Python, output unchanged (B-M6).
- `build_context()` split into focused helpers (`_load_history`,
  `_load_batch_summaries`, `_recall_memories`); behaviour unchanged (B-M5).
- Documentation and contribution conventions established: hand-curated
  `CHANGELOG.md`, append-only ADRs in `docs/adr/`, a `docs/README.md` index, and a
  Session Protocol + Commit Convention in `CLAUDE.md`. `CLAUDE.md` rules
  restructured into behavioral principles + numbered engineering standards.
  Market/production research moved to `docs/archive/research/`.

### Added

### Fixed
- Recall embedding is now computed before the turn's DB session opens, so no
  embedding API call runs inside an open session (B-M1, rule 15).

### Removed
- Residual function-level dead code: `ProcessedTurn`/`StreamEvent`
  (`core/engine.py`, pre-LangGraph leftovers), `get_user_campaigns`/
  `get_active_campaign` (`services/campaign_service.py`), and `register_provider`
  (`ai/providers/base.py`) — all with zero callers.

### Security
