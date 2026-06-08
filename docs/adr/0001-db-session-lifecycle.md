# ADR 0001 — DB session lifecycle for the turn endpoint

- **Status**: Accepted
- **Date**: 2026-06-08
- **Context items**: A-3, B-H4, B-H5 (AUDIT_APRIL_2026)

## Context

`POST /campaigns/{id}/action` (`app/api/turns.py`) is the live turn path:
validate the campaign → run `dm_graph.ainvoke` (multiple LLM calls, multi-second)
→ persist the turn. The original implementation held a single request-scoped
`AsyncSession` (`Depends(get_db)`) open across the whole handler, including the
graph invocation. Two problems:

1. **Rule 15 violation** — a DB session was held open across LLM calls, pinning a
   pooled connection for seconds and risking idle-in-transaction timeouts.
2. **`turn_number` race** — the next turn number was computed in Python
   (`campaign.turn_number += 1`) on a read-then-write within the long session.
   Two concurrent actions on the same campaign could read the same value and
   collide, and the error path tried to "give back" the number
   (`campaign.turn_number -= 1`), which is itself racy.

## Decision

Split the handler into two short sessions with no session held across the graph:

1. **Session 1 — claim.** Validate ownership/status, then atomically claim the
   next turn number with `UPDATE campaigns SET turn_number = turn_number + 1
   ... RETURNING turn_number`. Commit and close before touching the graph. The
   row lock serialises concurrent claims, so each turn gets a distinct,
   sequential number under Postgres READ COMMITTED.
2. **No endpoint-held session** across `dm_graph.ainvoke`,
   `compress_turn_to_summary`, and `generate_embedding`. The graph's own nodes do
   touch the DB, but each opens and **closes** a short session before the next
   LLM call — see the rule-15 note below — so no session is ever held across an
   LLM call anywhere on the turn path.
3. **Session 2 — persist.** Re-fetch the campaign (a fresh attached instance —
   the Session 1 object is detached), write `world_state` / `character_data`,
   insert the `Turn` and refresh the auto-save, commit and close.

The response is built from the graph's `final_state`, not from a detached ORM
object. Background tasks already open their own session via `get_db_context`.

### Dropped: turn-number rollback

If the graph fails we no longer decrement `turn_number`. A claimed-but-unused
number simply leaves a harmless gap. This removes a write on the error path and
the associated race, and keeps the failure path read-only.

## Consequences

- **Positive**: no DB connection pinned across LLM calls; concurrent actions are
  safe; the failure path no longer mutates state. Covered by
  `tests/integration/test_turn_concurrency.py` (5 concurrent actions → distinct
  sequential numbers + N persisted rows).
- **Trade-off**: turn numbers can have gaps on graph failure. Acceptable —
  numbers are identifiers/ordering, not a contiguous count.
- **Trade-off**: two round-trips to the DB instead of one. Negligible next to the
  multi-second graph.

## Rule-15 status of the whole turn path

A-3 closes the last gap. The graph nodes were already compliant:

- `context_node` — opens a session, reads the campaign, runs `build_context`
  (incl. the recall embedding, B-M1) and routing, then **closes** the session
  before returning. `dm_node`'s main LLM call therefore runs session-free.
- `dm_node` — no session at all.
- `dm_tools_executor` (`invoke_npc`) — opens a session to read the campaign and
  **closes** it before `invoke_npcs_parallel` (the NPC-director LLM call).
- `post_process_node` — synchronous, no DB.

B-M1 (the embedding runs inside `context_node`'s still-open session) is the only
residue: it's a DB-then-embedding sequence, not a session-across-LLM, and the
embedding is ~200ms vs the multi-second graph — minor, tracked separately.

## Notes

`get_db_context()` returns `async_session()` (sessionmaker has
`expire_on_commit=False`), so attribute access after `commit()` is safe inside
each `async with` block. The test conftest rebinds
`app.dependencies.async_session` to a `NullPool` test engine, so each concurrent
request gets its own connection.
