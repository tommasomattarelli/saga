# ADR 0019 — Quest persistence and database migration coverage

- **Status**: **Proposed** — Part A implemented in [PR #97](https://github.com/tommasomattarelli/saga/pull/97);
  Part B's design approved by the owner on 2026-10-20, with implementation gated on
  an explicit, reasoned lead review of S0 before any implementation code.
- **Date**: 2026-10-20.
- **Context items**: [GitHub #86](https://github.com/tommasomattarelli/saga/issues/86),
  `TODO.md` stabilization point 4 and its migration-coverage audit; follows ADR 0018.

Legend: **Decided** = settled by the owner. **TODO** = explicitly open, with a
resolution gate. This record covers two separate PRs, not only the quest bug.

## 1. Context

The following paths were checked against `main` at `56f61c6` during the
2026-10-20 exploration:

- `backend/app/core/world_instantiation.py` seeds `campaign.quests["active"]`
  from the world's `scenario.initial_quests`, including descriptions and objectives.
- `backend/app/memory/updater.py` handles `quest_update` by writing
  `character_data["active_quests"]`. Starting an already-active quest does not
  update its description; completing one removes it; failure and abandonment do
  nothing, although `UpdateQuest` advertises all four statuses.
- `backend/app/ai/prompts/dm.py` reads only `campaign.quests["active"]` and renders
  names, not descriptions or objectives. The live writer never reaches this reader.
- `GameState`, the tool dispatcher/result and the turn response carry no dedicated
  quest registry. `backend/app/api/turns.py` persists world and character changes,
  but autosaves copy the unchanged `campaign.quests`.
- Manual saves, restore and campaign export also use `campaign.quests`. The
  frontend journal reads its `active` and `completed` lists, but the turn hook/store
  cannot update that registry. The frontend separately expects a per-record
  `status` that the authored seed does not supply.
- `backend/eval/scenario_build.py` works around the split by copying quests into
  character data before replay and copying them back afterwards.
- There is a campaign export endpoint, but **no campaign import endpoint**. World
  import/export is a different, existing feature.

Migration coverage is a related but distinct persistence problem:

- `backend/tests/conftest.py` creates the application schema with
  `Base.metadata.create_all`, not the Alembic chain; `init_db` in
  `backend/app/dependencies.py` also uses `create_all`.
- Revision `001_memory_facts` has no predecessor, but references `campaigns`
  without creating it. The chain therefore cannot bootstrap an empty database.
- Revision `007_embedding_index` **does have real migration tests** after #96:
  an isolated PostgreSQL database is built from frozen pre-change code, stamped
  at 006, then upgraded, downgraded and upgraded. This does not cover the complete
  chain, and the older TODO claim that no migration is tested is now historical.

The owner reports having removed the development container volume and chooses a
fresh-start quest contract. This is not evidence about other installations, nor
permission for the application to erase anyone's database.

**Out of scope:** campaign import; a new quest/objective progression system; a UI
redesign; general runtime-state typing; tool-discovery or prompt-tuning projects;
reconstruction of quest outcomes from narrative text or extra LLM calls.

## 2. Part A — Canonical quest registry (PR 1, #86)

### A1 — One campaign-owned source (Decided)

`campaign.quests` is the only quest registry. Remove
`character_data.active_quests` from live writers, frontend contracts/fixtures and
evaluation replay. Do not maintain two synchronized copies or a read fallback.

Use a typed quest contract at the runtime and API boundaries, rather than another
free-form dictionary convention. Keep the existing JSONB column; this change does
not itself require a new SQL table or an Alembic revision.

### A2 — Four lists, no duplicated status (Decided)

The registry has exactly four status lists:

```json
{
  "active": [],
  "completed": [],
  "failed": [],
  "abandoned": []
}
```

Each quest contains `id`, `name`, `description` and `objectives` (a list of strings).
Its containing list determines its status; there is no per-record `status` copy.
World-authored initial quests enter `active`; the other lists start empty.

A readable, explicit tag such as `dragon_hunt` identifies one record across the
whole campaign registry. IDs are stable and unique across all four lists; the
same ID cannot appear in multiple lists. Titles are display metadata and may
duplicate: `dragon_hunt` and `dragon_hunt_on_winter` can both be named Dragon Hunt.
Look up IDs exactly, without fuzzy title matching or IDs derived from titles.

Add the explicit ID to `InitialQuest`, world YAML and the corresponding authoring
editor/schema, including the bundled world and fixtures. Duplicate authored IDs
are validation errors, not a signal to silently merge records or invent suffixes.
The tool addresses quests by ID; names are not lookup keys.

**Design refinement (2026-10-20, owner).** Explicit tags replace the initial
name-identity direction: titles need not be unique and must not drive updates.

**S0 note (2026-10-20, implementation).** The tag contract is
`^[a-z0-9]+(_[a-z0-9]+)*$`, at most 64 characters; duplicate authored tags fail
world loading with the offending tag. `InitialQuest` and the scenario editor
carry `id`, and a title may repeat across distinct tags.

### A3 — Preserve records and honor every advertised state (Decided)

The tool supports `active`, `completed`, `failed` and `abandoned`. Moving between
states moves the whole record, preserving authored objectives and other values
that the operation does not update. Completing a quest no longer deletes it.

An update to an active quest can change its description. Repeating the same
operation must not create another record. State changes are explicitly reversible:
the DM may move a concluded quest back to `active`, using the same ID and record, without
new gameplay restrictions. This is current-state storage, not an event history.

For an unknown ID, only `active` creates a quest, and a non-empty display name is
required. Other states on an unknown ID return a short tool error without changing
the registry. Repeating an operation on an existing ID never creates a new quest.

An omitted description preserves the previous text; an explicit empty string
clears it. A new quest with no description starts with an empty string. Fields not
supplied by an update are preserved rather than reset during a status change.

DM-created quests start with `objectives: []`. The tool does not generate or edit
objectives, and there is no second AI call to populate them in this PR. Authored
objectives remain in the diary/storage, not in the DM's structured quest context:
the owner wants natural play rather than steering the DM toward an objective list.
The existing `[x]` display convention does not become a new progression mechanic.

Invalid input must not produce a success message or partial mutation. Campaign
creation and character PATCH requests containing `active_quests` are rejected with
HTTP 422, rather than silently dropping or retaining the retired container.

**S0 note (2026-10-20, implementation).** `update_quest` takes `quest_id`,
`status`, optional `name` and optional `description`; an omitted description
preserves and `""` clears it. The shared `apply_quest_update` returns the
unchanged registry plus a short message on invalid input, so no caller can
partially mutate it.

### A4 — Connect the entire turn path (Decided direction)

Carry the typed registry through the turn's input, `GameState`, quest execution
and graph output, then persist it alongside the world/character state and turn.
Use detached data, not an ORM `Campaign` passed into update handlers. DB sessions
must remain closed across model calls (ADR 0001 and engineering standard 15).

Pass the resulting registry into the turn response and update the frontend store
from it. The journal derives status from the containing list, not from a second
field. Adapt the existing journal to the four states without a redesign.

The precise updater/dispatcher signatures are an implementation design task:
choose the smallest explicit change, without refactoring unrelated tools or
smuggling quests through `world_state`, `character_data` or untyped result extras.

**S0 note (2026-10-20, implementation).** `QuestRegistry` rides
`GameState.quests` and `ToolResult.quests`; `execute_tool` accepts it as an
optional typed argument. `campaign.quests` is validated at the API boundary and
written as detached data, and autosave, restore and export serialize that registry.

### A5 — Prompt: active IDs and descriptions only (Decided)

The next turn's quest block renders each active quest's ID and description from
the canonical registry, not its display name. Objectives remain stored but are not
added to the DM's structured quest context or exposed through a new read tool.
Concluded quests remain in storage, saves and export, not in the permanent quest
prompt block. Do not grow that block with the entire campaign archive.

This fixes the read/write path, not the separate problem of a model narrating a
quest change without calling the tool. No additional generation call is needed.
This is not an absolute guarantee that a title can never reach the model: a title
the DM supplies when creating a quest may remain in tool-call history or narration.

### A6 — Saves, export and fresh-start compatibility (Decided)

Autosave, manual save, restore and export use the same typed registry as gameplay.
A restore replaces the current registry with the saved one; it does not merge
quests accumulated after that snapshot. A subsequent turn must read that restored
registry in its quest prompt block.

There is **no backward-compatibility requirement for old quest payloads**: no
backfill, merge of the two old containers or narrative reconstruction. Do not add
a quest migration merely to support data the owner has explicitly excluded.
This does not authorize automatic wipes or remove normal SQL migration obligations.

PR 1 must not claim that verifying the quest snapshot proves complete rollback of
turn history, summaries, facts or embedding indexes; those are separate state
surfaces and any additional findings must be reported rather than silently fixed.

### A7 — Acceptance tests (Decided verification scope)

Write failing tests before implementation. The core flow uses real PostgreSQL and
the actual campaign/world seed, tool execution and persistence path; control AI
responses, not a fabricated final graph state that bypasses the bug.

The PR must demonstrate:

1. Authored IDs, display names, descriptions and objectives survive campaign
   creation; different IDs may share a title, but duplicate IDs are rejected.
2. Starting and updating a quest changes the canonical registry; all four states,
   reversible transitions and repeated calls preserve one complete record.
3. A real tool call in one turn is committed and visible in the next turn's quest
   prompt block, including its ID and changed description, excluding inactive
   quests, display-name fields and objective metadata.
4. Autosave and manual save capture the registry; restoring either removes later
   changes and supplies the restored quest block on the next turn.
5. Export matches the stored registry, and the frontend journal/store reflects a
   turn response without requiring a page reload.
6. Evaluation replay uses the production quest-update behavior without its former
   character-data bridge; unknown IDs, invalid operations and retired-container
   writes fail as specified in A2–A3, without partial changes.

Unit tests cover transition/validation edge cases; frontend tests cover the store
and journal contract. Run both stacks' full checks, including PostgreSQL
integration/playtest coverage, before landing the fix.

## 3. Part B — Database bootstrap and migration coverage (PR 2)

### B1 — Separate delivery, immediately after PR 1 (Decided)

PR 1 closes #86. PR 2 addresses the remaining migration work in stabilization
point 4; it is not a condition for closing that issue and does not broaden its fix.
The TODO item remains open for this second part after the quest fix lands.

### B2 — Required verification outcomes (Decided)

PR 2 must replace the current coverage gap with a reproducible real-PostgreSQL
bootstrap/upgrade path and checks that exercise the actual Alembic revisions.
B3–B11 record the owner's subsequent design choices; implementation waits for
explicit lead approval of S0. The quest decisions do not imply that historical
migrations may be skipped, rewritten or stamped as successful without executing
the intended changes; validated adoption is limited to B3 and B6.

The verification contract is:

- Establish how an empty PostgreSQL database with the required extensions reaches
  the supported application schema through the chosen migration/bootstrap path.
- Check the resulting tables, columns, constraints, enums and vector definitions
  against what the application uses, rather than only checking `alembic_version`.
- Exercise data-bearing upgrades from a reproducible predecessor produced by real
  historical code, where required by the selected supported-baseline policy.
  Do not hand-author an assumed old schema that merely certifies the same mistake.
- Preserve the existing isolated 006→007 embedding regression and its data checks;
  an empty-database smoke test is not a substitute for testing a backfill.
- Define downgrade expectations only where representable; document irreversible
  data changes rather than claiming every migration is losslessly reversible.
- Keep test databases isolated, remove them after failures too, and run the checks
  in CI against PostgreSQL 16 with pgvector.
- Reconcile the selected bootstrap path with `init_db`, test setup and documented
  installation/development commands so `create_all` cannot mask a broken path.

This is infrastructure work, not a quest backfill, campaign import endpoint or
general installer redesign. Any broader data-support or startup-policy decision
must return to the owner instead of being inferred from the deleted dev volume.

### B3 — Explicit adoption of unversioned databases (Decided)

An existing database without an Alembic revision is not automatically adopted at
startup. Provide a manual adoption command that recognizes and validates a known,
supported schema before recording its corresponding revision. Unknown or
mismatched schemas are rejected, without an automatic wipe or a blind stamp.

The adoption command supports exactly two frozen schema profiles: the current
post-PR-1 schema at `5e9206da28a0be1d8e669dcc72ed0af6a3525eac`, and the pre-embedding
006 schema produced by `261ad5fb53003844efbe1d8097d9393469686291`. These are SQL
schema baselines, not a promise to convert legacy quest payloads.

B6 defines the validation contract. Other unversioned schemas, including the
latest tagged release `v0.2.1-alpha.2`, are not adoption targets in PR 2. The owner
prioritizes a new release after stabilization over expanding the historical
adoption matrix.

**Rejected:** automatic startup adoption puts recognition and mutation into boot;
refusing all unversioned databases without an adoption command leaves the existing
`create_all` installations without an in-scope transition; current-only adoption
omits the already reproducible 006 predecessor, while supporting tagged releases
adds historical coverage the owner does not need for this delivery.

### B4 — One Alembic chain from an empty database (Decided)

Add a frozen initial revision before `001_memory_facts`, reconstructing the
pre-001 schema from real historical code. Change only 001's predecessor link to
connect that revision; preserve the existing upgrade/downgrade bodies in 001–007.
An empty database must reach the supported schema through `alembic upgrade head`,
executing the revisions rather than creating current ORM tables and stamping head.

Add a new forward revision after 007 to reconcile verified historical omissions
and schema drift. Known examples are campaign summary/persona columns and
`turns.summarization_failed`; S0 must inventory the complete difference before
implementation. Migration DDL is frozen and does not import mutable application
models. Existing versioned databases retain their revision identity and do not
rerun the new predecessor.

**S0 note (2026-10-20, lead review).** Use the real pre-001 parent `94db17d`,
not current ORM definitions with columns subtracted. The provisional gap inventory
includes the four summary/persona/summarization columns, nullable memory-fact
timestamps, three 007 server defaults and B11's retired tables. Verify this against
real PostgreSQL catalogs as the first implementation test; static inspection is
not proof that no other difference exists.

**Rejected:** a separate historical SQL bootstrap keeps two required entry points
and lets direct Alembic use remain incomplete; a single chain makes the bootstrap
path itself executable and testable.

### B5 — Application-owned migration startup (Decided)

Replace `init_db`'s runtime `create_all` with the Alembic upgrade path before the
application serves requests or starts embedding recovery/workers. Empty and
already versioned databases upgrade automatically, serialized by a PostgreSQL
lock. A database containing application schema objects but no revision stops
startup and requires B3's manual adoption, even if its tables contain no rows;
it is never implicitly stamped. Migration failures stop startup. Unknown or newer
revisions are rejected, not automatically downgraded or guessed.

Native and Docker installations use the same backend startup path. pgvector
remains a provisioned prerequisite, as in ADR 0000, rather than assuming the
application role can install extensions. This evolves the implementation of
ADR 0000's shared startup contract without editing that Accepted record.

**Rejected:** launcher-only migration duplicates required wiring across entry
points; manual-only migration makes ordinary updates an operator task and breaks
the desired double-click experience.

### B6 — Exact, frozen schema validation for adoption (Decided)

Before stamping 006 or 007, compare the database structurally with the selected
frozen B3 profile: application tables, columns, SQL types, nullability, server
defaults, constraints, indexes, enum definitions and vector dimensions. Differences
outside documented semantic normalization reject adoption with readable diagnostics;
unexpected application objects are not silently tolerated. Extension-owned objects
are excluded from the application-schema comparison.

Adoption does not repair the schema or convert campaign JSONB contents. Recognition
must not depend on current, mutable ORM definitions pretending to describe a
historical schema; S0 will define the frozen profile representation and equivalence
rules from the two real commits.

**Rejected:** allowing unrecognized extra application objects weakens the claim
that the starting schema is known; a minimal column signature can stamp an
incomplete schema as a successful baseline.

### B7 — Migrated schemas for integration and playtest coverage (Decided)

Prepare the integration/playtest application database through Alembic once per
suite, replacing the current `Base.metadata.create_all` setup. Per-test data cleanup
preserves `alembic_version` rather than truncating the migration record. Keep the
isolated real-PostgreSQL 006→007 embedding regression and exercise the actual
application startup path in dedicated tests.

**Rejected:** keeping `create_all` for ordinary integration tests leaves a second
schema producer able to conceal missing migration objects, even with a dedicated
migration smoke test.

### B8 — Bounded migration lock contention (Decided)

Serialize concurrent startup migration attempts with a PostgreSQL lock. A waiting
process has a finite, configurable acquisition timeout and rechecks the database
revision after acquiring the lock. Timeout stops that startup with a clear error;
it never permits parallel migration or starts the server on an unchecked schema.
S0 will select the smallest shared lock mechanism and a sensible configuration
default; no unbounded polling loop is permitted.

**S0 note (2026-10-20, lead review).** The approved configuration is
`migrations.lock_timeout_seconds: 30`, positive and finite. One explicit outer
transaction acquires a session advisory lock before inspecting revision/schema
state; startup, adoption and online Alembic mutation commands share this protocol.
Alembic uses the injected connection and does not recursively invoke its own
commands from `env.py`. Release the lock only after the owner transaction exits;
clean up timeout/session state on success, failure and cancellation, invalidating
the connection if safe cleanup cannot be completed.

**Rejected:** immediate failure on any contention makes otherwise normal concurrent
starts require a manual retry; unbounded waits can leave a broken startup hanging.

### B9 — Full-chain schema and targeted historical data checks (Decided)

Verify the whole 000→head schema path and add focused data-bearing regressions for
the relevant 003, 005, 006 and 007 transitions. Produce predecessor schemas from
the frozen historical code or the actual Alembic revisions, never hand-author an
assumed old schema. Assert preserved data, intended transformations and rejection
without data loss for invalid inputs; retain the 006→007 embedding backfill checks.

Keep the scenario set small and coherent rather than building a speculative
permutation matrix. Testing versioned SQL transitions does not expand B3's two
unversioned adoption profiles or restore excluded legacy quest support.

**Rejected:** empty-database plus 006→head tests alone leave earlier data migrations
unexamined, even when the final schema smoke test is green.

### B10 — Representable downgrade guarantees (Decided)

Guarantee and test downgrade only for explicitly representable cases, including
the existing legacy 007→006→007 round trip and additional cases justified by the
actual migrations. Do not claim universal, lossless rollback: 004 drops templates,
006 drops personal-profile columns, and 007 drops newly introduced embedding data.
Document destructive boundaries and the need for backup/restore or a forward
correction. Application startup never downgrades a database.

Failed upgrades must not leave partially applied application DDL/data changes or
advance the recorded revision. Incompatible data is reported rather than silently
discarded or reinterpreted beyond the declared migration transformations. Startup
and adoption diagnostics must not expose database credentials.

**Rejected:** upgrade-only guarantees discard useful reversible-case checks;
universal rollback would promise recovery of data that the historical downgrade
operations cannot reconstruct.

### B11 — Reconcile the two retired meta tables in 008 (Decided)

**S0 finding (2026-10-20, review).** The actual pre-001 code at `94db17d`
registers `achievements` and `profile_stats` through `app.models.meta`. Commit
`bcded56` removed those unused models without a SQL migration. A faithful 000
therefore creates both tables, while neither frozen B3 adoption profile has them.

The owner explicitly authorizes 008 to drop these two retired tables, including
any rows they contain, so fresh-chain and adopted databases converge on the
current application schema. The owner reports having removed their historical
development database; this is not evidence that other installations lack data.
Document the destructive boundary and backup requirement. Do not use this choice
to justify cascading deletion of unexpected dependencies or any other data.

**Rejected:** keeping optional public legacy tables makes final schema convergence
conditional; moving them into a new archive schema adds preservation machinery
the owner does not want for these retired features. Dropped rows cannot be
reconstructed by a downgrade.

**S0 review gate (2026-10-20, lead).** The first S0 was not approved: revise it to
apply one locking/transaction protocol to startup, online Alembic commands and
adoption, not just the two application wrappers. Conditional schema correction
must validate existing objects rather than hiding incompatible columns with
`IF NOT EXISTS`. Missing historical timestamps must not be silently invented;
incompatible values fail atomically under B10. Recheck the complete schema-gap
inventory against real PostgreSQL catalogs before treating static inspection as
verification. These are requirements for the revised S0, not permission to code.

**S0 approval (2026-10-20, lead).** The revised S0 is explicitly approved for
implementation because it unifies lock/transaction ownership across all mutation
paths, rejects ambiguous existing objects and unknown timestamps, preserves
frozen historical provenance and verifies convergence of all three supported
paths. Binding refinements: no public unvalidated-stamp escape hatch for tests;
the existing frozen-006 test helper must use validated production adoption while
retaining its historical schema, seeded vectors and backfill assertions. In 008,
absence of a 007 server default is valid for adopted schemas, while removal is
limited to the known historical default; unexpected definitions fail. Freeze
revision-local DDL/check helpers rather than importing mutable runtime migration
helpers. A new genuine design fork or contradiction from the first catalog check
returns to the lead/owner before proceeding.

## 4. Delivery and relationship to other ADRs

- **PR 1 — quest persistence:** one focused feature/fix branch and PR to `main`,
  with `Closes #86` in the PR body, typed state, backend/frontend/evaluation changes
  and their tests. Do not close the issue with this documentation commit.
- **PR 2 — bootstrap and migration coverage:** a separate reviewable branch/PR
  after PR 1, using the resolved Part B design and retaining the existing migration
  regressions. The split is by logical deliverable, not one PR per sprint.
- **PR 2 S0 gate:** a fresh implementation teammate first delivers its grounded
  schema inventory, frozen-profile contract, startup/locking plan, focused tests
  and logical commit plan, then stops without implementation edits. The lead
  explicitly approves with reasons or rejects with reasons and required changes;
  silence or a generic acknowledgement is not authorization to implement.
- **ADR 0001:** preserve the detached-state, short-session turn lifecycle.
- **ADR 0008:** retain world-authored initial quest descriptions and objectives;
  world import/export is unaffected.
- **ADR 0010:** general character typing remains its responsibility; removing the
  duplicate quest key does not expand this work into that redesign.
- **ADR 0018:** retain the delivered embedding migration tests and index contract;
  this ADR does not reopen either decision.

No existing ADR is superseded or edited. The two deliverables complete point 4
before the guided gameplay debugging of point 5. Campaign import stays a
far-future, non-priority backlog item, not a third delivery in this ADR. A separate
AI call to author objectives for DM-created quests is also deferred; it must not
delay a stable quest registry or be introduced as an implicit background task.

## 5. Decided vs open index

| Area | State | Resolution gate |
|---|---|---|
| Campaign-owned registry, four lists, unique explicit IDs, display-only titles | Decided | A1–A2 |
| Description updates, retained objectives, reversible states, no duplicates | Decided | A3 |
| Turn propagation, frontend synchronization, snapshot/export parity | Decided direction | A4, A6–A7; settle signatures in the pre-code pass |
| Active IDs/descriptions in the prompt, no display names/objectives/archive | Decided | A5 |
| No old-quest compatibility; no automatic deletion | Decided | A6 |
| Two PRs; campaign import deferred | Decided | B1, §4 |
| Exact ID lookup, duplicate authored IDs rejected, duplicate titles allowed | Decided | A2; small validation/signature details in S0 |
| Unknown ID: only active plus a non-empty title may create | Decided | A3 |
| Omitted description preserves; explicit empty clears | Decided | A3 |
| New DM quests have empty objectives; no extra AI call | Decided | A3, §4 |
| Invalid tools do not mutate; retired-container writes return 422 | Decided | A3 |
| Existing unversioned databases: manual, validated adoption; current and frozen 006 only | Decided | B3, B6 |
| Adoption validates the complete frozen application schema, without repairs | Decided | B6; freeze profile representation and equivalence rules in S0 |
| Empty-DB bootstrap: frozen pre-001 revision and a new post-007 correction | Decided | B4; inventory all schema gaps in S0 |
| Full-chain SQL schema and focused historical data upgrades | Decided | B9; distinct from unversioned adoption and legacy quest compatibility |
| Downgrade guarantees are limited to tested, representable cases | Decided | B10; document irreversible data boundaries |
| Startup/bootstrap ownership: automatic Alembic for empty/versioned DBs | Decided | B5, B8 |
| All integration/playtest schemas come from Alembic; keep 006→007 isolation | Decided | B7 |
| Concurrent startup migrations use a bounded, configurable PostgreSQL lock wait | Decided | B8; mechanism and default in S0 |
| 008 drops only the two retired meta tables, with explicit data-loss consent | Decided | B11; no unexpected dependency cascade |

Part A shipped in #97; the owner approved Part B as Proposed after the B3–B10
design interview. The remaining S0 tasks are concrete implementation
grounding: verify schema gaps against catalogs and freeze profile representation/
equivalence rules. The revised S0 has explicit, reasoned lead approval recorded
next to B11; B8 records its lock protocol and timeout. The first review found B11's
additional owner decision before any implementation. New genuine design forks
return to the owner before code. No external research is required:
these choices rest on inspected code, Git history and the owner's constraints.

## 6. Rejected alternatives and consequences

**Rejected by the owner:**

- Character-owned quests: moves the established seed, prompt and snapshot contract
  instead of fixing its disconnected live writer.
- Active-only storage: loses structured completion/failure/abandonment outcomes.
- A flat list with per-quest status: workable, but changes more existing readers
  than the chosen four-list contract; duplicating status in both forms is worse.
- Irreversible states: adds gameplay restrictions to a persistence fix.
- Name-based identity: distinct quests can share a title; explicit tags avoid that
  collision and are the only lookup key.
- Objective/archive prompt context: the owner chose active IDs and descriptions,
  with objectives hidden to avoid steering play toward a checklist.
- A second AI call for objectives now: appealing as future work, but adds cost and
  orchestration before the basic persistence path is stable.
- Legacy recovery: unnecessary under the chosen fresh-start quest contract.
- Campaign import now, or migration repair inside #86: expands one focused fix
  into unrelated delivery; both were explicitly separated or deferred.

**Positive:** one typed source connects the tool, next-turn prompt, journal,
snapshots and export; a separate infrastructure PR makes migration failures visible
without delaying the quest fix. Application startup and integration tests share
the real migration chain, and unversioned adoption has a finite, verified scope.

**Trade-offs / risks:** JSONB still rewrites the complete registry, whose archive
grows with the campaign; the archive is not fed wholesale into the prompt. Explicit
IDs change the authored YAML/tool contract, and DM-created objectives remain empty
for now. Old quest payloads are not supported; restore outside the quest registry is not proven
by these tests. Startup now needs migration privileges and may take longer during
an upgrade; lock acquisition is bounded, adoption rejects unrecognized schemas,
and destructive historical migrations cannot promise universal lossless downgrade.
This infrastructure adds no AI calls or per-turn token cost.
