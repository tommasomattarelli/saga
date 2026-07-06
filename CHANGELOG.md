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
- [UI] Play screen redesigned to the new clean dark identity (ADR 0013, Sprint 1): self-hosted Newsreader/Instrument Sans type, verdigris accent, hero badge with level/HP, labeled panel pills, serif narration at reading measure with color-coded speakers, rounded action input in plain English, and a new tier-arc dice reveal showing all six outcome tiers. Also fixes: the orphan red companion bar, typed actions lost on a failed submit, history-load failures shown as a false "not started yet" empty state, and a CSS `@import` ordering bug that silently dropped every design token in dev.
- [UI] Redesign propagated to every remaining screen (ADR 0013, Sprint 2): auth is now a single centered card with visible boxed inputs (fixes invisible-input contrast bug); campaign list is a card grid replacing the book-spine shelf; new-campaign wizard flattened (no more 3D page-flip); character sheet is a tabbed rail modal on an opaque panel (fixes gameplay bleeding through); journal, settings, and combat tracker re-skinned to the same tokens. Plain English copy throughout, routed via i18n. Dead ornament assets (map, seal, book-spine, candles, flourishes) removed.
- [Installer] The native Linux installer now works on Debian and every Ubuntu release, not just Ubuntu 24.04: it adds the PostgreSQL PGDG apt repository so Postgres 16 + pgvector install uniformly regardless of the distro's default Postgres major (bookworm ships 15, trixie ships 17).
- [Installer] macOS: pgvector is now built from source against `postgresql@16` (Homebrew's pgvector bottle targets a different Postgres major, so `CREATE EXTENSION vector` previously failed).
- [Installer] The native Linux/macOS installer now fails fast with a clear message when run as root, instead of installing Postgres and then dying mid-way on `initdb` (which refuses to run as root).

### Internal
- ADR 0008 (world model) Sprint 2: campaigns now instantiate from library Worlds — game home `~/.saga` (SAGA_HOME override) with a git-backed world library seeded from the bundled example; slug→UUID instantiation with composed global-km positions and alias index; new `world_baseline` JSONB column (frozen authored tree, C7 TOAST split) + world identity stamp (`world_slug`/`world_version`); overlay schema v5 (`player_position`, `node_status`, `edge_overrides`, `consumed_encounters`); `templates/` + templates table removed (Alembic 004), `/api/templates` → `/api/worlds`; NPC locations are node UUIDs (J3); git added to the backend Docker image; campaign wizard picks Worlds.
- ADR 0008 (world model) Sprint 1: world meta-schema (world-defined vocabularies per P0 — custom kinds/terrains/travel-modes with engine-contract numeric fields), directory-convention World loader (dir-as-tree, filename-is-slug), three-tier validation (YAML → Pydantic → referential integrity + dynamic per-kind params), and the shipped example World `worlds/the-awakening/` with the copyable default taxonomy. Pure backend; DB wiring lands in Sprint 2.
- Dev Docker Compose: added the `:z` SELinux relabel suffix to host bind mounts so `docker compose up` works on SELinux-enforcing hosts (Fedora/RHEL); the suffix is ignored on non-SELinux systems.
- Installer smoke CI: added a `macos-smoke` job (runs the native installer's Homebrew path on a `macos-latest` runner) alongside the existing Windows and Linux smoke jobs.
- Supply-chain / security CI: Dependabot (`uv` backend, `npm` frontend, github-actions) — routine version updates as one grouped PR per ecosystem (weekly, low noise), plus Dependabot alerts + security updates **enabled** so CVE fixes open individually as soon as they land. CodeQL code-scanning and a dependency-review gate on PRs are **guarded on repo visibility** — they skip while the repo is private (free only on public repos) and activate automatically once it's public. Secret scanning + push protection remain a repo setting to flip at go-public.
