# SAGA v0.1.0-beta.2 — 2026-06-24

## Highlights

### Installer

- The native installer now tracks the just-published release automatically: its pinned `REF` is bumped at release time, so casual users always clone the latest version (still overridable with `SAGA_REF`).

### Infra

- Releases are now produced by a single script — `scripts/release.sh <version>` promotes the changelog, tags `main`, and publishes the GitHub Release in one step (with a `--dry-run` preview), so cutting a release no longer means a manual checklist.


## Internal

### Added
- `scripts/release.sh` — version-in → release-out automation: parses `[Unreleased]`, regroups Highlights by `[Area]` into `docs/changelog/CHANGELOG-vX.Y.Z.md`, resets `[Unreleased]`, bumps the installer `REF`, then commits, tags, pushes `main`, and publishes the GitHub Release. `--dry-run` generates and shows everything, prints the exact git/gh commands, then reverts. Manifest versions are deliberately not bumped (pre-release PEP440/npm divergence).

### Changed
- `CLAUDE.md`: Highlights bullets now carry an `[Area]` tag that `release.sh` groups on; the release-notes convention dropped the manual New/Improvements/Bugfixes split in favour of flat area-grouped bullets, and the release flow is documented as script-driven.
