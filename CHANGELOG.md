# Changelog

All notable changes to SAGA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This log is curated by hand — it is not a dump of `git log`. Add entries under
`[Unreleased]` as you work, split into `### Highlights` (user-facing) and
`### Internal`. On release the notes move to
`docs/changelog/CHANGELOG-vX.Y.Z.md` (and the GitHub Release) and
`[Unreleased]` is reset; this root file keeps only `[Unreleased]`.

## [Unreleased]

### Internal

- Reorganized backend evaluation tools and tests, indexed their guide, and clarified harness-independent skills and owner authorization for external evaluation calls.
- Recorded ADR 0020 from the owner-interview plan for batched memory, durable production and save-aware histories, with explicit offline and live-evaluation gates.
- Added immutable, strictly validated memory-production policy contracts without adopting campaign defaults or changing the public creation path (ADR 0020 S1).
- Stabilized Ruff source discovery after evaluation-tool relocation without reformatting existing modules.
- Added immutable campaign histories, frozen save references and ancestry queries through a forward-only, migration-tested schema without converting existing turns (ADR 0020 S1).
- Added ordered memory batches, typed documents, rich fact provenance and coverage cursors with PostgreSQL integrity constraints (ADR 0020 S1).
- Recorded per-operation outcomes and deltas atomically with turns, adding immutable provenance and canonical batch inputs without converting historical sources (ADR 0020 S2).
- Prepared strict memory producers, validated prompt examples and reproducible offline evaluations; live evidence, production defaults and variant selection remain owner-gated (ADR 0020 S3).
- Isolated generation-profile reads from campaign relationships so memory evaluations can preserve legacy databases without migrations (ADR 0020 S3).
- Added stable per-model memory-evaluation sessions, recorded request headers and parallel model workers with sequential requests and quota-safe stopping.
- Refined candidate memory prompts toward concise third-person DM summaries, future-useful facts and importance calibration for central unresolved revelations (ADR 0020 S3).
- Added fenced memory-job claims, persistent attempt budgets, expired-lease recovery and explicit retry cycles without activating public memory production (ADR 0020 S4a).
- Added context-local single-attempt generation so durable memory jobs own retry budgets without changing ordinary provider retry behavior (ADR 0020 S4a).
- Froze complete specialist/global job requests in versioned manifests, preserving source and instruction identity across restarts and template changes (ADR 0020 S4a).
