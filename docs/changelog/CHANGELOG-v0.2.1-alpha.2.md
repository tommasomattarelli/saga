# SAGA v0.2.1-alpha.2 — 2026-08-04

## Highlights

### Memory & AI

- Model reasoning is no longer saved as a campaign summary: the summarisers require a JSON object and `<think>` blocks are stripped, so deliberation fails to parse instead of being stored (#78).
- Truncated model answers are no longer stored as complete, and every call uses the `max_tokens` the router resolves instead of a hardcoded one (#77).


## Internal

- Changelog bullets capped at one sentence and commits at one *logical* unit (six or seven per branch, `--amend` over follow-ups) in CLAUDE.md.
- `docs/adr/README.md` — tabular index of the 18 decision records: status, last movement, title, one-line direction. A `README` so GitHub renders it on opening `docs/adr/`; `/adr` updates the row at close-out.
