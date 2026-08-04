---
name: dead-code
description: Find and remove dead code in a given scope of SAGA — a whole stack (frontend / backend) or a sub-area (e.g. backend-ai, combat, memory, or a path). Two modes - symbol mode runs static analysis first (knip / vulture / ruff), key mode traces readers and writers of JSONB dict keys that static tools cannot see inside (world_state, character_data). Both context-verify before removal and are gated on a green tree before AND after. Cleanup only — never adds features. Use when the user says "dead-code <scope>", "find unused code in X", "clean up dead code", "dead keys", "who writes this key", "reader-writer audit".
---

# /dead-code — find and remove dead code (gated)

Two modes. Pick by what the deadness lives in:

| Invocation | Mode | Finds |
|---|---|---|
| `/dead-code <scope>` | **symbol** | Unreferenced functions, exports, files, imports. Static tools do the first pass. |
| `/dead-code keys <namespace>` | **key** | Dead *string keys* inside JSONB / dict payloads. Static tools are blind here — `state["foo"]` is a string, not a symbol. |

`scope` = `frontend`, `backend`, or a narrower area / path (e.g. `backend-ai` → `backend/app/ai`, `combat`, `memory`).
`namespace` = a payload whose shape is untyped and crosses layers — `world_state`, `character_data`, `npc` records, a tool's argument dict.

Cleanup only, both modes: **never add functions or abstractions** (CLAUDE.md principle 2; the user's standing rule "senza aggiungere nuove funzioni").

## Mode: symbol — steps

1. **Green BEFORE** — verify the suite is green for the scope before touching anything; don't trust docs/AUDIT (std 11).
   - backend: `cd backend && uv run python -m pytest tests/unit --noconftest -q`
   - frontend: `cd frontend && npx vitest run`
   If red, stop and report — never start a cleanup on a red tree.

2. **Static pass — collect candidates**:
   - frontend: `cd frontend && npx knip` (unused files / exports / deps) + ESLint unused.
   - backend: `cd backend && uv run vulture app --min-confidence 80` (scope to the sub-path if given, e.g. `app/ai`) + `uv run ruff check` for unused imports (F401).

3. **Verify each candidate — confirm truly dead before removing**. Static tools flag false positives; check for: dynamic refs (`getattr`/`importlib`/registries), entrypoints (FastAPI routes, alembic, CLI, `__all__`), tool registration (`dm_tools`), test-only usage, config/string references, DI wiring.
   - **Large scope** → fan out a few sonnet subagents (one per module), foreground, full findings reported back. **Small scope** → verify inline. Subagents only if genuinely necessary (the user's standing preference).

4. **Remove + re-test (green AFTER)**:
   - Remove only high-confidence, truly-unreferenced code.
   - **Ask the user** before removing low-confidence / ambiguous candidates.
   - Re-run the scope's tests. If anything goes red, revert that removal.

5. **Report** — what was removed, what was left uncertain (and why), and the green→green confirmation. Propose a `refactor(<scope>): remove dead code` commit (one logical change); leave the commit to the user / `/wrap-up`.

## Mode: key — steps

A key is dead when one side of the reader/writer pair is missing. The failure is silent by construction: a read with no writer returns the default forever and the feature never fires (`score_importance`'s combat bonus shipped this way and never once triggered), a write with no reader is payload that costs prompt tokens to carry.

1. **Green BEFORE** — same gate as symbol mode. Red tree, stop.

2. **Anchor the shape** — read the namespace's own definition first, not the greps:
   - seed / instantiation site (`world_state` → `app/core/world_instantiation.py`);
   - the migration ladder (`world_state` → `app/memory/world_state.py`, rungs 1..N + `CURRENT_SCHEMA_VERSION`). The ladder is the historical key list: a key no rung writes and no seed sets exists only in rows nobody made.

3. **Sweep every layer** — grep the literal key across **all** of them. Missing one layer manufactures a false orphan, which is the expensive mistake here:
   - backend Python: `state["k"]`, `.get("k")`, `["k"] =`, `.setdefault("k")`, `.update({...})`, `.pop("k")`;
   - **prompts** (`app/ai/prompts/`) — an f-string interpolation is a real read, and the consumer is the LLM;
   - **tool schemas** (`dm_tools.py`) — a key the LLM is told to emit is a write from outside the codebase;
   - alembic migrations, YAML templates (`templates/`), and the frontend (TS access + POST bodies).

4. **Classify** — one row per key: `key | writers (file:line) | readers (file:line) | verdict`.
   - **orphan read** — read, never written. The bug class. Highest value, cheapest fix.
   - **orphan write** — written, never read. Payload bloat; check it isn't read by a *prompt* before calling it dead.
   - **divergent** — one concept, several spellings across layers (`dexterity` / `"DEX"` / `char_data["dex"]`).
   - **live** — both sides present. Say so and move on.

5. **Fix per class — the cost is not the same, do not batch them**:
   - orphan read → delete the read and the branch it feeds. No migration, no schema move.
   - orphan write → delete the write. Only drop the key from existing rows if it is prompt-carried bloat, and then only via a **new rung** (bump `CURRENT_SCHEMA_VERSION`) — never by editing an existing rung, which would skip rows already past it.
   - divergent → **report, do not normalize**, unless the fix is a pure rename at one site. Unifying a key across layers is a typing job with an owner (ADR/TODO), not a cleanup; say who owns it and stop.
   - **Round-trip gate**: `world_state` and `character_data` ship in campaign export/import (data-sovereignty pillar). Dropping a key an old export still carries must leave the importer able to read it — that is what the rung is for. Verify import of a pre-change export before calling a key removal done.

6. **Re-test (green AFTER)** + report the table, what was removed, what was left to an owner and why.

## Boundaries
- Cleanup only — no new features, no refactors beyond removing the dead code your pass found.
- Gated: green before and after; on any post-removal red, revert rather than patch.
- Key mode reports divergences, it does not unify them — normalization is a typed-schema change, out of scope.
