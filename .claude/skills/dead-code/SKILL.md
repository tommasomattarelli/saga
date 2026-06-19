---
name: dead-code
description: Find and remove dead code in a given scope of SAGA — a whole stack (frontend / backend) or a sub-area (e.g. backend-ai, combat, memory, or a path). Static-analysis first pass (knip / vulture / ruff), then context-verification before removal, gated on a green tree before AND after. Cleanup only — never adds features. Use when the user says "dead-code <scope>", "find unused code in X", "clean up dead code".
---

# /dead-code <scope> — find and remove dead code (gated)

`scope` = `frontend`, `backend`, or a narrower area / path (e.g. `backend-ai` → `backend/app/ai`, `combat`, `memory`). Cleanup only: **never add functions or abstractions** (CLAUDE.md principle 2; the user's standing rule "senza aggiungere nuove funzioni").

## Steps

1. **Green BEFORE** — verify the suite is green for the scope before touching anything; don't trust docs/AUDIT (std 11).
   - backend: `cd backend && uv run python -m pytest tests/unit --noconftest -q`
   - frontend: `cd frontend && npx vitest run`
   If red, stop and report — never start a cleanup on a red tree.

2. **Static pass — collect candidates**:
   - frontend: `cd frontend && npx knip` (unused files / exports / deps) + ESLint unused.
   - backend: `cd backend && uv run --with vulture vulture app --min-confidence 80` (scope to the sub-path if given, e.g. `app/ai`) + `uv run ruff check` for unused imports (F401).

3. **Verify each candidate — confirm truly dead before removing**. Static tools flag false positives; check for: dynamic refs (`getattr`/`importlib`/registries), entrypoints (FastAPI routes, alembic, CLI, `__all__`), tool registration (`dm_tools`), test-only usage, config/string references, DI wiring.
   - **Large scope** → fan out a few sonnet subagents (one per module), foreground, full findings reported back. **Small scope** → verify inline. Subagents only if genuinely necessary (the user's standing preference).

4. **Remove + re-test (green AFTER)**:
   - Remove only high-confidence, truly-unreferenced code.
   - **Ask the user** before removing low-confidence / ambiguous candidates.
   - Re-run the scope's tests. If anything goes red, revert that removal.

5. **Report** — what was removed, what was left uncertain (and why), and the green→green confirmation. Propose a `refactor(<scope>): remove dead code` commit (one logical change); leave the commit to the user / `/wrap-up`.

## Boundaries
- Cleanup only — no new features, no refactors beyond removing the dead code your pass found.
- Gated: green before and after; on any post-removal red, revert rather than patch.
