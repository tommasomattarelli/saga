---
name: adr-implement
description: >-
  Implement an owner-approved, Proposed SAGA ADR using a bounded, reviewable,
  evidence-driven workflow. Use when asked to implement or continue an ADR.
  Design decisions belong to $adr; stop and ask the owner if implementation
  evidence genuinely forces a new decision.
---

# $adr-implement — implement the decision

This workflow starts after `$adr` has closed the design. The source ADR remains
the sole authority for decisions. Implementation may reveal that a premise or
contract is wrong; record evidence, but do not silently redesign.

## 1. Preconditions and startup

- Read the complete Proposed ADR and its row in `docs/adr/README.md`. Check
  status, gates, dependencies, and the relationship to other ADRs. WIP is not
  implementable; Accepted is not reopened—propose a superseding ADR instead.
- Read `AGENTS.md`, run the catchup workflow, and inspect the complete
  authoritative source of every contract or behavior being changed. Summaries,
  previous agent notes, and generated ledgers are not substitutes for source.
- Require explicit owner authorization for this implementation and any
  separately authorized activity. Do not infer approval for external-provider
  calls, catalog or environment probes, evaluations, pushing, merging, or
  rebasing.
- Before edits, establish the actual worktree, branch, last ten commits, status,
  and baseline checks. Preserve pre-existing user changes; do not claim a clean
  baseline if it was not verified.
- The startup hook prints the actual worktree and branch, `git log -10
  --oneline`, and `git status -sb`. Otherwise take that Git snapshot manually.
  Never imply a hook or other enforcement exists when it does not.
- Follow project branch rules by default. An implementation plan or explicit
  owner instruction may override base, topology, commit heuristic, or check
  cadence; do not hardcode a branch count, commit ceiling, or topology.

## 2. S0 — ground the plan in code

Do not start implementation from the plan alone. Verify its claims against
current code, schemas, tests, and consumers. Identify seams, affected contracts,
risks, dependencies, and the checks each logical block needs. Resolve only
unresolved configuration values or premises required to proceed, using the
ADR's stated constraints and owner input; do not invent gameplay values.

Protect existing work and establish a baseline before changing files. Re-size
the plan where repository evidence requires it, without revisiting closed
design choices. If evidence forces a real design fork, stop and ask the owner;
do not turn S0 into a second design interview.

## 3. Roles, coordination, and concurrency

Keep logical roles distinct: an orchestrator coordinates and reviews; a mapper
traces contracts and consumers; an implementer changes code; an independent
reviewer checks the result read-only. The orchestrator delegates ordinary
implementation work and works directly only on unusually high-effort work.
Resolve role availability and depth intent from the active harness and
user-configured options for each run. Do not hardcode agent identifiers,
model/provider names, or proprietary effort labels. Surface actual selections
through the workflow controller; never silently substitute a default.

Use adaptive, bounded parallelism: start with two concurrent writers; allow up
to three only for genuinely disjoint scopes and within the limit approved for
this run. Mapping and review remain read-only. Serialize migrations and
database tests unless they use genuinely disposable, isolated infrastructure.
Before any commit or hook, freeze every writer and wait for all work to finish;
hooks may run the whole unit collection even when implementation tasks appeared
independent.

Keep reviews in the conversation and use concise tool verdicts, not repository
review reports or handoff documents. The workflow controller maintains a
minimal machine ledger at `<absolute-git-dir>/saga-workflow/state.json`
(resolve the private Git directory; do not create a source-tree state file):
block identifier and content hash, actual check command and exit status,
reviewer session/verdict, and writer states. Reuse real chat/session references
for finding details; the ledger supplements operational state only and never
replaces or overrides the ADR or authoritative source evidence.

On resume, read the ADR, controller state, and actual Git state. Reconcile
claims, content hashes, checks, and review freshness before writing. A prior
summary is not proof. Do not create Markdown reports, scratch notes, or
temporary handoff files.

## 4. Implement each logical block

For each block:

1. For behavior or executable-code changes, write a focused failing test first.
   Do not invent tests for documentation-only edits: review their source and
   diff instead. Exercise real PostgreSQL for core flows and migrations only
   with explicitly authorized, disposable infrastructure.
2. Implement the minimum change that satisfies the test and ADR.
3. Run pertinent tests, lint, and type checks. If related authored content or
   fixtures changed, verify it is not stale and that consumers use the
   authoritative contract.
4. Review correctness and slop before accepting the block. For every addition,
   identify its actual requirement or reader/consumer and a distinct regression
   test. Reject duplicated fixtures with conflicting contracts, vacuous tests
    of typed fields/defaults, speculative framework paths, unnecessary guards,
    silent coercions, data loss, or inventions used to accept invalid outputs,
    and duplicate validation. Do not reject intentional domain rules authorized
    by the ADR. Ground exact official machine vocabulary in authoritative
    sources where relevant.
5. Review the exact frozen content, not an earlier snapshot. If review finds a
   defect or slop, fix it and rerun pertinent checks and review.

Correctness and slop are semantic judgments, not guaranteed by procedure.
Fresh content hashes, actual check receipts, and independent review improve
traceability but do not prove quality. Seek independent review when another
perspective could materially change the outcome.

Run checks appropriate to each block; do not run both stacks' full suites for
every commit by default unless the owner explicitly requests them. At branch
completion, run the full checks for both stacks and all applicable gates from
`AGENTS.md`, including `mypy`, `knip`, coverage, or build checks when required.
Required failures or unverified checks mean the branch is not green. Focused
checks are not a substitute for full gates at completion.

## 5. Commit and safety boundaries

Keep each commit one logical change with its relevant tests and a concise
`CHANGELOG.md` `[Unreleased]` entry, following `AGENTS.md`. Avoid filler
commits and do not compress unrelated work into a large commit to satisfy a
heuristic. Amendments, branch topology, and cadence follow the project rules
unless the authorized plan explicitly says otherwise.

Do not bypass existing hooks. Freeze writers and review the exact staged
content before committing. Every commit requires explicit correctness and slop
verdicts for its exact staged scope. The gate verifies fresh proof for that
scope and the writer barrier; it cannot guarantee semantic quality. No
automatic push, merge, or rebase. A pause is not
branch completion: record machine-verifiable state, known failures, and
unverified work. A safe checkpoint may remain uncommitted; do not force a WIP
commit or promise a green result.

## 6. Reconcile the ADR

At meaningful implementation checkpoints, compare evidence with the ADR for:

1. Contract or signature changes forced by code.
2. False premises about existing behavior or data.
3. Vocabulary collisions with established code or official machine terms.
4. Missing guarantees assumed by the design.
5. Cross-ADR effects or gates.

Only actual findings justify documentation changes. Add a dated implementation
note next to the affected decision, in the form
`**Sn note (YYYY-MM-DD, implementation).** …`, and update the index row when
its status or last movement changes. A note records what implementation forced
and why; it is not a new decision. Do not edit an Accepted ADR. If no finding
forces documentation change, leave the ADR and index untouched.

## 7. Completion and delivery

Distinguish implementation completion from owner acceptance. Owner playtest,
acceptance, and any live evaluation are separate activities requiring their
own authorization; do not infer or perform them.

Before declaring the branch complete, close all in-scope work, review the exact
final frozen state, and pass required full gates. Record provenance
and actual check results in controller state. Delivery, push, or merge occurs
only when explicitly authorized and project workflow permits it. A partial
checkpoint must state what is done, what remains, and what is red or
unverified—never imply full completion.
