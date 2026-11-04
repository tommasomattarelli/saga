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

- [World & DM] Remove narrowly recognized quoted speech echoes before subsequent NPC beats, preserving original provider messages and adding language, placement and beat-progress reminders (ADR 0017).
- [World & DM] Separate NPC instructions from character data, share filtered player input with actors and default to four spoken lines per actor call (ADR 0017).
- [World & DM] Distinguish NPC speech, intentional silence and failed generation, rejecting unusable responses without fake dialogue or conversation effects (#102).
- [World & DM] Dispatch independent NPCs in observable parallel beats, preserve per-turn interaction history and compose verbatim speech through one ordered transcript (ADR 0017).
- [UI] Interleave NPC speech with narration through ordered parts, without repeating actions below bubbles or bypassing progressive dice reveal.
- [Memory & AI] Summarize complete turn transcripts instead of 300-character narration prefixes, and feed NPC speech once to fact extraction (#106).
- [World & DM] Reduced new travel narration/state divergence by requiring `move_to` on coherent histories; old conflicting history is not repaired (#101).
- [World & DM] Narrate tool outcomes from refreshed in-turn state, with a configurable eight-call DM limit, terminal-safe closing steps and a guard against repeated no-progress tool results.
- [Gameplay] Apply elapsed time once and report the actual clock change, including completed or interrupted travel, with tool feedback reading the canonical clock (#99).
- [World & DM] Choose a campaign language at creation or in settings; narration and NPCs share that target, while saves retain the current preference and existing text remains unchanged.

### Internal

- Clarify single-call versus bounded-turn dialogue evaluation and freeze the tested candidate without changing runtime or historical evidence (ADR 0017).
- Record the 16-trial dialogue comparison and observed cache reuse, deferring production caching decisions and requiring cache-hit checks in the final suite (ADR 0017).
- Add opt-in, trial-scoped OpenRouter session affinity to dialogue evaluation, preserving shared clients and binding sanitized routing headers to request evidence (ADR 0017).
- Prepare a DM-only prompt experiment with persistent composition examples contrasting copied speech, omitted handles and invented dialogue, including terminal-safe closing requests (ADR 0017).
- Run dialogue evaluations in independent model lanes with automatic free-model throttling, isolated trial contexts, concurrency-safe request budgets and coherent new courier-seal fixtures (ADR 0017).
- Prepare a selectable v2 dialogue evaluation with natural two-turn cases, explicit paid-model consent, request identity, separate outcome metrics and resumable usage reports (ADR 0017).
- Capture per-request evaluation usage, cache/reasoning details and actor/step correlation, with offline CSV/Markdown summaries and explicit missing values (ADR 0017).
- Completed ADR 0017's 36-trial baseline and recorded the owner-approved S2 quality pass; further live evaluation awaits renewed authorization.
- Added typed narration parts and frozen NPC line handles with deterministic placement, malformed-marker cleanup and dice-safe end-of-turn fallback (ADR 0017).
- Grounded ADR 0017 S0 on merged PR 1, recording ordinary-NPC beat, failure, visibility and transcript contracts with quota-bounded two-day final evaluation.
- Live probes requested `move_to` for every valid response in short and ten-turn coherent travel; recovery of already-conflicting history remains unreliable (#101).
- Hardened live evaluation with personal AI settings, retry-free request accounting, full traces and identity-aware resume/reporting; verified campaign-language defaults and rejected tool-call correlations.
- Factored prompt text into packaged YAML and composed deterministic tool obligations from each step's exposed tool registry (ADR 0004 S2).
- Added a resumable request ledger, captured saturated scenarios and a bounded real-actor path to the model smoke harness.
- Recorded the ADR 0004 S2 implementation decisions — campaign language, prompt sources, result-aware loop, clock authority — and the ADR 0017 claims they supersede.
- Clarified LangSmith graph-state traces versus model prompts and recorded persistent identity and profile requirements for rich auto-created NPCs.
