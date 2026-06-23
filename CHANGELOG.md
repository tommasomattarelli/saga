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
- Supply-chain / security CI: Dependabot (`uv` backend, `npm` frontend, github-actions; weekly, grouped minor/patch) plus CodeQL code-scanning and a dependency-review gate on PRs. CodeQL + dependency-review are **guarded on repo visibility** — they skip while the repo is private (those features are free only on public repos) and activate automatically once it's public. Secret scanning + push protection are a repo setting to flip at go-public.
