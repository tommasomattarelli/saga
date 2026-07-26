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
- Issue tracking conventions (CLAUDE.md "Issue Convention"): issue titles follow the commit grammar `type(scope): subject`, and labels split into three orthogonal axes — `type:`, `prio:` (set at triage, never by the reporter), `area:` (mirrors the commit scopes) — plus additive status labels. The GitHub default labels that mixed those axes were removed. New YAML issue forms in `.github/ISSUE_TEMPLATE/` (blank issues disabled): the bug form requires version, install method, area, AI provider and repro steps; the feature form points at `TODO.md` and the ADRs first.
