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
- [Memory & AI] Truncated model answers are no longer stored as complete, and every call uses the `max_tokens` the router resolves instead of a hardcoded one (#77).

### Internal
- `docs/adr/README.md` — tabular index of the 18 decision records: status, last movement, title, one-line direction. A `README` so GitHub renders it on opening `docs/adr/`; `/adr` updates the row at close-out.
