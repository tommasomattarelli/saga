# SOTA Handover & Phase 5 Safety Plan ⚔️🛡️

## 1. Summary of Phase 4 Accomplishments
In this session, we transformed the project into a **State-Of-The-Art (SOTA)** repository:
- **Backend Quality**: 100% pass rate for 74 unit tests. Achievement of **70%+ coverage**.
- **Frontend Quality**: Achievement of **~71% coverage** with Vitest. Integrated ESLint v9 and Prettier.
- **Architecture**: Renamed `SagaException` to `SagaError` for naming conventions. Cleaned up all verbose comments/docstrings.
- **Orchestration**: Root `Makefile` implemented. `make check` now validates the entire project.

---

## 2. Upcoming Challenge: Engine Reconstruction
The next phase involves a deep refactor of the **Engine Core** (`engine.py`, `turn_service.py`). This is "open-heart surgery" on the project. To avoid breaking the game, we need a **Safety Net** before we start.

### Why?
Unit tests verify *pieces*. If you change how the Engine talks to the Database or how the World State is merged, unit tests might still pass (because they use mocks), but the **real game** will break.

---

## 6. Senior Code Audit & Scoring (1-30L)

| Aspect | Score | Senior Feedback |
| :--- | :--- | :--- |
| **SOTA Compliance** | **26** | Great toolchain usage. Deductions for `as any` in TS and lazy imports in backend. |
| **Readability** | **28** | Exceptionally clean. Avoid turning `engine.py` into a monolithic script. |
| **Modularity** | **23** | **Critical.** The Engine is a "God Object". Decouple dice, AI, and state logic. |
| **Scalability** | **26** | **Ottimo.** L'uso di PostgreSQL + Redis via Docker è la scelta corretta. Punti persi solo per l'assenza di partizionamento dei log e di un cluster reale, ma per una SaaS in avvio è perfetto. |
| **Testing** | **26** | Great unit coverage jump. **Integration tests are mandatory** for the next phase. |
| **Documentation** | **30L** | `CLAUDE.md` and this plan are top-tier. Maintain this discipline. |

### Final "Senior" Nitpicks:
1. **Frontend**: 71% coverage with `as any` mocks is "false security". Use **Zod** or strict **Interfaces** for API contracts.
2. **Error Handling**: Implement **Error Boundaries** and AI retry logic in the Service layer.
3. **Mocks vs Reality**: Il debito tecnico più grande ora è l'abuso di \`AsyncMock\` nel backend. La Phase 5 deve essere il passaggio ai **test su database reale (Docker)** per garantire che i vincoli di integrità e le query pgvector funzionino davvero.


---

## 3. Recommended Safety Net (Pre-Engine Hack)

### 🔬 Integration Tests (The Plumbing)
*Done in `tests/integration/` — **STOP MOCKING DB, USE REAL POSTGRES***
- **`test_api_persistence.py`**: A real API call to `/api/campaigns` that verifies data is actually in the **Postgres DB (via Docker)**, not just mocked.
- **`test_websocket_sync.py`**: Verifies that when a turn is processed, the WebSocket sends the correct sequence of events (`turn_start`, `narration`, `turn_complete`).
- **`test_auth_guard.py`**: Verifies that the security layer and `get_current_user` work with the real DB session.

### 🎭 Playtests (The Gameplay Scenarios)
*Done in `tests/playtests/`*
- **`scenario_intro_loop.py`**: A scripted run (Register -> Login -> Create Campaign -> 3 Turns).
- **`scenario_combat_consequences.py`**: Focuses on mechanics. "If HP reaches 0, does the World State transition to 'Defeated'?"
- **`scenario_persistence_reload.py`**: Perform actions, "kill" the server, restart, and verify the state is 100% recovered.

### 🛡️ TypeScript Quality
- **Typed Mocks**: In `*.test.tsx`, replace all `as any` with proper Interfaces. This ensures that if the API changes, the tests will fail to *compile*, giving you instant feedback.

---

## 5. SOTA Testing Philosophy

### ⚖️ Does 100% Coverage make sense?
- **Backend (Engine)**: **Yes**, aim for 90-100% on the `engine.py` and `dice.py`. These are the "Truth" of your game. Every calculation must be perfect.
- **Backend (API/Boilerplate)**: **No**, 70-80% is the Sweet Spot. Testing that a 404 is returned for every single ID is often noise.
- **Frontend**: **No**, 100% is a trap. You end up testing "if a button is blue" rather than "if the game works". Stay around 70%.

### 🌐 Frontend Integration vs Playwright
- **Vitest + RTL**: These are already "Integration" tests (e.g., `NewCampaign` tests multiple components and stores). These are fast and essential.
- **Playwright (Cross-Stack)**: This is "End-to-End". It's the only one that tests **Frontend + Backend** together. 
- **The Verdict**: Wait for Phase 6. Doing Playwright now, while the Engine is changing, will lead to "Flaky Tests" (tests that fail because the DB schema changed, not because the UI is broken).

