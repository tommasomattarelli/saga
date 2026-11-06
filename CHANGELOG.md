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

- [Infra] Patch vulnerable Python and frontend dependencies, including TLS trust and Vite file protection, while preserving existing provider, UI and network configuration.
- [Memory & AI] Share OpenRouter routing affinity across each campaign's DM, NPC and background generation calls, preserving current prompts and state updates without guaranteeing cache hits.

### Internal

- Patch ESLint's minimatch subtree with a scoped override, verified by bounded attack and matching-compatibility regressions.
- Verify world filesystem guards and document 14 CodeQL path-injection false positives with per-alert evidence.
- Share evaluation affinity per suite/checkpoint and model across cases, repetitions and resume, retaining explicit header evidence and rejecting incompatible historical manifests.
- Observe cache reuse in 24 bounded DeepSeek/GLM probe requests, retaining provider-specific limitations without attributing savings solely to shared affinity.
- Add a bounded OpenRouter cache probe comparing trial and shared affinity on frozen DM requests, with simulated NPC replay and per-request routing evidence.
