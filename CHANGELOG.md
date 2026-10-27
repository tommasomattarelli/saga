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

- [Gameplay] Apply elapsed time once and report the actual clock change, including completed or interrupted travel, with tool feedback reading the canonical clock (#99).
- [World & DM] Choose a campaign language at creation or in settings; narration and NPCs share that target, while saves retain the current preference and existing text remains unchanged.

### Internal

- Added a resumable request ledger, captured saturated scenarios and a bounded real-actor path to the model smoke harness.
- Recorded the ADR 0004 S2 implementation decisions — campaign language, prompt sources, result-aware loop, clock authority — and the ADR 0017 claims they supersede.
- Clarified LangSmith graph-state traces versus model prompts and recorded persistent identity and profile requirements for rich auto-created NPCs.
