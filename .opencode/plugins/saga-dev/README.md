# SAGA dev plugin (OpenCode V2)

Project-local, deterministic development status for SAGA. It answers one
question: **is the local stack healthy, and is the last check still current?**

No LLM calls, no external services, no npm dependencies.

## What it does

- A server plugin (`index.ts`) probes the backend, frontend, PostgreSQL and Git
  every 10 seconds, and writes a normalized snapshot to
  `.opencode/state/saga-dev.json`.
- A TUI plugin (`tui.tsx`) reads that file only. It renders a compact
  `sidebar.content` widget and a detailed panel opened with `/saga`. Pressing
  `/saga` again closes it; `esc` and `q` close it too, and `f` toggles
  fullscreen when the terminal is wide enough.
- Three tools expose the same state to agents without shelling out:
  - `saga_status` — compact health, last CI result, git branch/diff.
  - `saga_check({ scope })` — `affected`, `fast` or `full`; writes the full log
    to `.opencode/state/logs/` and returns only a concise summary.
  - `saga_logs({ service, level, limit })` — filtered recent logs.

The UI never executes commands. The monitor never runs lint or tests; checks
run only when `saga_check` is called. Results are cached by working-tree
fingerprint and guarded by a single-flight lock, so an agent running its own
commands does not duplicate work.

## Scopes

| Scope | What runs | Database |
|---|---|---|
| `affected` | only checks mapped from changed files (`ruff`, `eslint`, `prettier`, `tsc`, changed unit tests, `vitest related`, config tests) | no |
| `fast` | `ruff check`, `ruff format --check`, `mypy`, backend unit tests, `eslint`, `prettier`, `tsc`, frontend unit tests | no |
| `full` | CI parity: the fast static checks plus `vulture`, backend unit/integration/playtest, frontend coverage, `knip`, build, and the browser smoke | yes (compose test DB on 5433) |

`full` starts `docker-compose.test.yml` only if port 5433 is closed, and stops
it only if this run started it.

The browser smoke is part of `full` only. It uses the system Google Chrome via
Playwright's `channel: "chrome"`, replays the golden path with mocked APIs, and
records console errors and failed requests. It does not use
`frontend/test-results` or the e2e runner.

## State

```json
{
  "schema": 1,
  "updatedAt": "2026-10-19T17:44:00Z",
  "services": {
    "backend":  { "status": "up", "port": 8000, "latencyMs": 19, "detail": null },
    "frontend": { "status": "up", "port": 3000, "latencyMs": 8,  "detail": null },
    "database": { "status": "up", "port": 5432, "latencyMs": 2,  "detail": null }
  },
  "ci": {
    "scope": "fast",
    "status": "pass",
    "finishedAt": "2026-10-19T17:32:00Z",
    "fingerprint": "…",
    "gitSignature": "…",
    "stale": false,
    "checks": {},
    "lastFailure": null
  },
  "git": { "branch": "main", "dirty": 0, "added": 0, "removed": 0, "signature": "…" },
  "browser": { "status": "unavailable", "reason": "not run" }
}
```

`ci.stale` becomes `true` when the working tree no longer matches the tree the
last check ran against. The sidebar shows `stale` instead of pretending the
result is current. A commit changes Git's view of the tree, so `stale` can flip
right after committing even though the file contents are unchanged; the next
`saga_check` refreshes it.

## Notes

- Frontend dev server must be reached at `http://localhost:3000` (Vite binds to
  `localhost`, not `127.0.0.1`).
- Backend health uses `GET /openapi.json`; there is no `/health` endpoint.
- State, logs and cache live under `.opencode/state/` and are gitignored.
- To disable the plugin, remove or rename `.opencode/plugins/saga-dev/`.
- The existing `npm run test:e2e` suite is independent: it still needs
  Playwright's Chromium and a writable `frontend/test-results`.
