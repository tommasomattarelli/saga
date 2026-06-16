# ADR 0011 — Frontend E2E: mocked golden path (no backend/Docker)

- **Status**: Accepted
- **Date**: 2026-06-16
- **Context items**: Frontend refactor session 2026-06-16 (F-L9)

## Context

F-L9 asked for an E2E test of the golden path (login → campaigns → game). A
"true" E2E (real backend + Postgres + an LLM key) gives the most fidelity but is
slow, flaky, and pulls Docker + external credentials into a check that is meant to
guard *frontend* regressions (route guards, auth flow, wizard, render). The
`vitest` component tests already cover units with mocked clients; the gap is the
cross-page browser flow, not the backend contract.

## Decision

Author the golden path as a Playwright spec (`e2e/golden-path.spec.ts`) that mocks
every `/api/**` call **in the browser** via `page.route`. No backend, no Docker, no
LLM key. The Vite dev server (`npm run dev`, port 3000) is started by Playwright's
`webServer`; its `/api` proxy is never reached because the route mocks fulfill
first. `vitest` excludes `e2e/**` so the two runners do not collide.

The spec asserts the flow that frontend code actually owns: unauthenticated `/`
redirects to `/login`, a mocked login lands on `/campaigns`, and opening a campaign
renders the game's narrative region.

## Consequences

- Fast, deterministic, runs anywhere `npm` + Chromium do.
- Does **not** validate the real backend contract (response shapes are hand-mocked).
  A backend-real + Docker variant (`make test-infra-up`, seeded DB, action→dice) is
  deferred to a dedicated config; until then the mocks can drift from the API.
- `@playwright/test` + a browser download are new dev-only dependencies.
