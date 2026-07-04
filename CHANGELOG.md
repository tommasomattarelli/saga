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
- [Installer] The native Linux installer now works on Debian and every Ubuntu release, not just Ubuntu 24.04: it adds the PostgreSQL PGDG apt repository so Postgres 16 + pgvector install uniformly regardless of the distro's default Postgres major (bookworm ships 15, trixie ships 17).
- [Installer] The native Linux/macOS installer now fails fast with a clear message when run as root, instead of installing Postgres and then dying mid-way on `initdb` (which refuses to run as root).

### Internal
- Installer smoke CI: added a `macos-smoke` job (runs the native installer's Homebrew path on a `macos-latest` runner) alongside the existing Windows and Linux smoke jobs.
- Supply-chain / security CI: Dependabot (`uv` backend, `npm` frontend, github-actions) — routine version updates as one grouped PR per ecosystem (weekly, low noise), plus Dependabot alerts + security updates **enabled** so CVE fixes open individually as soon as they land. CodeQL code-scanning and a dependency-review gate on PRs are **guarded on repo visibility** — they skip while the repo is private (free only on public repos) and activate automatically once it's public. Secret scanning + push protection remain a repo setting to flip at go-public.
