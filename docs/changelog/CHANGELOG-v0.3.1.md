# SAGA v0.3.1 — 2026-11-06

## Highlights

### Memory & AI

- Share OpenRouter routing affinity across each campaign's DM, NPC and background generation calls, preserving current prompts and state updates without guaranteeing cache hits.

### Infra

- Patch vulnerable Python and frontend dependencies, including TLS trust and Vite file protection, while preserving existing provider, UI and network configuration.


## Internal

- Patch ESLint's minimatch subtree with a scoped override, verified by bounded attack and matching-compatibility regressions.
- Verify world filesystem guards and document 14 CodeQL path-injection false positives with per-alert evidence.
- Share evaluation affinity per suite/checkpoint and model across cases, repetitions and resume, retaining explicit header evidence and rejecting incompatible historical manifests.
- Observe cache reuse in 24 bounded DeepSeek/GLM probe requests, retaining provider-specific limitations without attributing savings solely to shared affinity.
- Add a bounded OpenRouter cache probe comparing trial and shared affinity on frozen DM requests, with simulated NPC replay and per-request routing evidence.
