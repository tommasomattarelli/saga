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
- Model smoke harness (`backend/scripts/model_smoke.py`) — evaluates whether a candidate model actually honours the DM's tool obligations, instead of picking one on reputation. It drives the **production** DM system prompt and tool schemas (the campaign is a stub carrying only the attributes the prompt builder reads, so no database and no drift from a hand-copied fixture) through four scenarios drawn from the playtest failures: a present NPC answering must route through `invoke_npc` (#52), a follow-up step after an NPC result must not restate the line (#53), acquiring an object must call `add_item`, and a passive turn must still advance the clock. Each is scored for missing/forbidden tool calls, language drift (#51), markdown, and mechanics leaking into narration. Compliance is stochastic, so every scenario runs `--runs` times and reports a ratio; provider failures are recorded as results rather than raised, which also exercises the #50 class. The grader is covered by unit tests — it decides which model gets picked, so it must not lie.
- Known defects migrated out of `TODO.md` into GitHub issues, so the backlog file holds only design work, refactors and directions: embeddings hardcoded to OpenAI regardless of the configured provider (#55), Gemini `thought_signature` dropped and breaking multi-turn tool calls (#56), hardcoded Postgres port with a silent bind failure on Windows (#57), Fedora/dnf unsupported by the native installer (#58). Two entries were retired instead of migrated: the `getTurns` empty-render bug is already fixed by ADR 0013 Sprint 1, and the "verify the frontend pushes are fail-silent" item no longer applies — the WebSocket game handler was replaced by the REST turn endpoint, so there are no pushes.
- ADR 0017 (NPC dialogue turn architecture) — **WIP stub, nothing decided**. Opened from the `v0.2.0-beta.1` playtest (#52, #53): the mid-turn `invoke_npc` tool serialises the DM and NPC models (a three-beat scene costs ~7 sequential round-trips), the DM skips it or paraphrases its result, and the tool boundary breaks the rhythm of a scene. Records the parallel pre-pass alternative (~2 round-trips, reusing the existing `invoke_npcs_parallel`), the constraint that must survive any option (the NPC's *decisions* stay its own — the intent-only variant is disqualified), and six open forks including how it relates to ADR 0014's per-turn acting call. Next step is an owner design interview.
- Issue tracking conventions (CLAUDE.md "Issue Convention"): issue titles follow the commit grammar `type(scope): subject`, and labels split into three orthogonal axes — `type:`, `prio:` (set at triage, never by the reporter), `area:` (mirrors the commit scopes) — plus additive status labels. The GitHub default labels that mixed those axes were removed. New YAML issue forms in `.github/ISSUE_TEMPLATE/` (blank issues disabled): the bug form requires version, install method, area, AI provider and repro steps; the feature form points at `TODO.md` and the ADRs first.
