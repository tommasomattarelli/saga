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

- [Infra] Releases are now produced by a single script — `scripts/release.sh <version>` promotes the changelog, tags `main`, and publishes the GitHub Release in one step (with a `--dry-run` preview), so cutting a release no longer means a manual checklist.
- [Installer] The native installer now tracks the just-published release automatically: its pinned `REF` is bumped at release time, so casual users always clone the latest version (still overridable with `SAGA_REF`).

### Internal

#### Added
- `scripts/release.sh` — version-in → release-out automation: parses `[Unreleased]`, regroups Highlights by `[Area]` into `docs/changelog/CHANGELOG-vX.Y.Z.md`, resets `[Unreleased]`, bumps the installer `REF`, then commits, tags, pushes `main`, and publishes the GitHub Release. `--dry-run` generates and shows everything, prints the exact git/gh commands, then reverts. Manifest versions are deliberately not bumped (pre-release PEP440/npm divergence).

#### Changed
- `CLAUDE.md`: Highlights bullets now carry an `[Area]` tag that `release.sh` groups on; the release-notes convention dropped the manual New/Improvements/Bugfixes split in favour of flat area-grouped bullets, and the release flow is documented as script-driven.
