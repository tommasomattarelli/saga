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

### Highlights

- [UI] Generation settings expose independent format-fallback choices without carrying saved consent to another destination (ADR 0021).
- [Gameplay] Retried actions preserve their request identity and reject stale histories instead of applying a second turn.
- [UI] Action failures expose a memory-retry banner while preserving the pending action and its identity.
- [World & DM] Experimental batched memory retains turn-level provenance and assembles context only from the selected history.
- [Infra] Campaign exports include a versioned archive of histories and memory records with an offline integrity validator.

### Internal

- Added destination-bound format fallback settings with strict boolean overrides, opaque HMAC identities and a forward profile migration (ADR 0021).
- Extended owner-controlled workflow scope extensions to automatic isolated worktrees and per-worktree receipts, with fresh independent correctness and slop review before every commit.
- Added whole-response static DM tool preflight with strict schema-safe diagnostics before effects, preserving sequential domain checks (ADR 0021).
- Added cumulative correction requests with quoted failed outputs and schema-derived, redacted validation guidance (ADR 0021).
- Removed prompt, response and tool-argument payloads from ordinary generation logs, retaining safe call metadata (ADR 0021).
- Added Google typed generation sends with explicit format modes, lossless receipts, bounded SDK attempts, and offline wire tests (ADR 0021).
- Added strict response validation with exact JSON-fence normalization and schema-aware diagnostics that redact untrusted field paths (ADR 0021).
- Added immutable generation requests, derived execution identities and lossless raw receipts with explicit output limits and signature snapshots (ADR 0021).
- Added typed OpenAI generation with faithful schema modes, lossless receipts, output caps and zero SDK retries (ADR 0021).
- Added typed OpenRouter/local generation with faithful schema modes, native tools, preserved request affinity and zero SDK retries (ADR 0021).
- Added typed generation failure classification with explicit retry, refusal, truncation and schema-incompatibility decisions, without matching provider prose (ADR 0021).
- Added lossless, Pydantic-derived wire DTOs for NPC update and psychology maps, preserving canonical validation and rejecting duplicate entries (ADR 0021).
- Added a shared strict response contract and canonical schema snapshots, reused by memory validation without changing prompts or contextual checks (ADR 0021).
- Recorded Proposed ADR 0021 for unified structured generation, bounded recovery and durable memory candidates, replacing ADR 0020's no-repair rule without authorizing live evaluation.
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
- Added durable memory jobs with frozen requests, bounded retries, atomic publication and history-safe artifact reuse, without activating the public pipeline (ADR 0020 S4a).
- Connected idempotent actions, three-level memory, bounded admission and history-safe restore/recall, with YAML-derived client deadlines and explicit blocking retries (ADR 0020 S4b).
- Delivered versioned campaign archives with full memory provenance, offline reference validation, and recoverable save/retry behavior under repeatable-read isolation (ADR 0020 S5).
- Retired legacy memory producers, harnesses, unused fixtures, TURN indexing and obsolete settings while preserving historical archives (ADR 0020 S6).
- Prepared guarded integrated memory evaluation with persisted-source provenance, bounded generation/embedding ledgers and offline manifests, leaving live runs and production decisions owner-gated (ADR 0020 S6).
- Simplified ADR 0020 S6 memory and archive paths, retired the isolated producer harness and overlapping coverage, and bounded offline evaluation preparation without authorizing live calls.
