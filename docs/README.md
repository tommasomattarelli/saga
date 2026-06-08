# SAGA Documentation

Start here to find the right document. Each doc has one job (per the
[Diátaxis](https://diataxis.fr/) model) — we don't mix reference, explanation,
and decision logs in the same file.

## Map

| Document | Type | Open it when you want to… |
|---|---|---|
| [`../README.md`](../README.md) | Tutorial / front door | Understand what SAGA is and run it for the first time |
| [`../CLAUDE.md`](../CLAUDE.md) | Working rules | Know how we work here — principles, engineering standards, session protocol |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Change log | See what changed and when (curated, SemVer) |
| [`AGENTIC_ARCHITECTURE.md`](AGENTIC_ARCHITECTURE.md) | Explanation | Understand *why* the agentic DM / LangGraph design is shaped this way |
| [`CONFIG.md`](CONFIG.md) | Reference | Look up a config knob in `saga.config.yaml` |
| [`AUDIT_APRIL_2026.md`](AUDIT_APRIL_2026.md) | Living backlog | See the open findings and what's been fixed |
| [`adr/`](adr/) | Decision records | Understand a specific architectural decision and its rationale |
| [`archive/`](archive/) | Historical | Read past sprint notes, verification reports, and research (frozen) |

## Conventions

- **Naming**: active docs use `UPPER_SNAKE_CASE.md`; ADRs use `NNNN-kebab-title.md`.
- **ADRs are append-only**: never edit an accepted decision — write a new ADR that
  supersedes it.
- **Docs-as-code**: a doc change ships in the *same commit* as the code it
  describes. Architectural decisions get an ADR in that commit.
- **Archive, don't delete**: superseded docs move to `archive/`, keeping git
  history and naming as-is.
