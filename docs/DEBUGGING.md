# Debugging SAGA

How to drive a turn through the debugger and see what the game actually did —
the real prompt, the real tool calls, the real rows. The owner drives; the agent
explains, interprets and asks. **No fix is written during a debugging session**
without an explicit decision (see [Triage](#6-triage-what-to-do-with-a-finding)).

Scope: backend turn flow first, frontend second, one scenario per area
(`TODO.md` stabilization point 5).

## 1. Preflight (once per machine)

| Step | Command | Expected |
|---|---|---|
| Dev DB up | `docker compose up -d db` | `docker compose ps` shows `db` healthy on `5432` |
| DB versioned | `cd backend && uv run python -m app.migrations.adopt --profile current_post_pr1` | prints nothing on success; `select * from alembic_version` → `007_embedding_index`, which the first boot then upgrades to the head revision |
| Config sane | `uv run python -c "from app.ai.router import validate_generation_config, validate_embedding_config; validate_generation_config(); validate_embedding_config(); print('ok')"` | `ok` |
| Dev DB reachable | `docker compose exec db psql -U saga -d saga -c "select turn_number, status from campaigns"` | one row per campaign |

If the DB is **unversioned**, startup refuses with
`UnversionedSchemaError` (`backend/app/migrations/state.py:175-182`) and names the
adopt command. Never work around it with `create_all`. On a DB you don't care
about, `docker compose down -v` and let startup migrate from empty.

**Credentials are not config.** A turn runs on the user's profile: a personal key
from Settings, or the instance key only if the user consented **and**
`providers.server_key_fallback.<provider>` is `true` in `saga.config.yaml`. With
neither, `resolve_generation` raises `ValidationError` and every turn answers 422
(`backend/app/ai/credentials.py:91-108`). The instance default
(`generation.default` in `saga.config.yaml`) only picks *which* provider/model;
it does not grant a key. Embeddings are a separate profile and a separate key.

**Interpreter**: select `backend/.venv/bin/python` in VS Code (on Windows,
`backend\.venv\Scripts\python.exe`). The launch configs pin it; don't rely on the
system Python.

## 2. Launch configurations

`.vscode/launch.json` ships two:

- **SAGA backend (uvicorn, no reload)** — `app.main:app` on `127.0.0.1:8000`,
  `cwd` `backend/`, `envFile` the **root** `.env`, `DATABASE_URL` overridden to
  `localhost` (the root `.env` points at the Docker hostname `db`).
- **SAGA single test (pytest)** — one integration test through the real graph;
  needs the **test** DB (`make test-infra-up`, port `5433`).

Two deliberate choices:

- **No `--reload`.** The reloader restarts the process and drops every breakpoint,
  and it hides the module twice in the call stack.
- **`justMyCode: true`.** Stepping skips LangChain/pydantic internals. Set it to
  `false` when you need to watch what the graph does inside `ainvoke`.

Port `8000` must be free: stop the compose `backend` service first
(`docker compose stop backend`), or nothing binds.

## 3. The turn, in order

`POST /api/campaigns/{campaign_id}/action` with `{"action": "..."}` — not
`/turns`. Router prefix at `backend/app/main.py:73`, handler
`backend/app/api/turns.py:42`.

| # | Where | What to look at |
|---|---|---|
| 1 | `turns.py:66-94` | Session 1: campaign fetch, the atomic `turn_number` claim (`:82-88`), the state snapshot (`:89-93`). **The session closes at `:94`, before any LLM call** (std 15). |
| 2 | `turns.py:97-122` | `initial_state` — exactly what the graph receives: action, `world_state`, `character_data`, `quests`, `world_baseline`, `difficulty`. |
| 3 | `turns.py:125-128` | `dm_graph.ainvoke(...)`, `recursion_limit=30`. Step in here to follow the graph. |
| 4 | `core/dm/dm_nodes.py:35-87` | `context_node` → `build_context` (`ai/context.py:140`): verbatim window, batch summaries, pgvector recall, then `build_dm_system_prompt` (`ai/prompts/dm.py:35`). **This is the prompt the model really gets.** |
| 5 | `core/dm/dm_nodes.py:90-168` | `dm_node`: active tool schemas (`:93-94`), the provider call (`:120-126`), the raw assistant message. |
| 6 | `core/dm/dm_tools_executor.py:45-194` | `tools_node`: ordering (`request_dice` first, `invoke_npc` last), per-tool handling, sanitized errors. |
| 7 | `core/dm/dm_graph.py:30-59` | Routing back to `dm_node` or out. Bounded by `max_agent_steps` (5) and `consecutive_empty_steps_max` (2). |
| 8 | `core/dm/dm_nodes.py:171-209` | `post_process_node`: narration, dice reveal, death event, state written back. |
| 9 | `turns.py:160` | `compress_turn_to_summary` — heuristic summary for the next window, **no session held**. |
| 10 | `turns.py:168-225` | Session 2: re-select `FOR UPDATE`, write `world_state`/`character_data`/`quests`, insert `Turn`, enqueue embedding, replace the auto-save, commit. |
| 11 | `turns.py:235-256` | `asyncio.create_task`: fact extraction, compression, global summary. **Nothing here has been awaited yet** — best place to see why a turn "wrote nothing". |
| 12 | `turns.py:258-276` | `TurnResponse` — what the frontend receives. |

Graph order: `context_node → dm_node → (tools_node → dm_node)* → post_process_node`
(`core/dm/dm_graph.py:65-75`).

Useful wants: the prompt → breakpoint in `build_dm_system_prompt` and inspect the
returned string; the tool call → breakpoint at `dm_node.py:120` and read
`tool_calls`; a tool's outcome → `tools_node` right after the branch; what got
persisted → `turns.py:177-179`.

## 4. The scenarios

One per area. Do not add more until these produce something actionable.

### 4.1 Plain turn, no tools

- **State**: an active campaign, a fresh turn.
- **Action**: `"I look around and take in the scene."`
- **Expect**: no tool call, `tool_events: []`, narration only; one new `turns`
  row, one replaced auto-save, quests untouched.
- **Watch**: the `<instructions>`, `<character>`, `<scene>`, `<history>` and
  `<quests>` blocks actually rendered — empty or duplicated blocks are a tuning
  finding, not a bug. Then `turn_number` before/after in `turns.py:82-88`.

### 4.2 Attack

- **State**: player and one NPC in the scene.
- **Action**: `"I swing my sword at him."`
- **Expect**: one `attack` call, `dice_results` in the response, target HP reduced
  by the server, life bar consistent; the narration must **not** invent numbers.
- **Watch**: `core/attack.py:174-230` (`resolve_attack`) — resolve sides,
  modifier, tier, the d20, `_damage_for`; then `core/health.py:93-122`
  (`apply_hp_delta`). HP lives at `character_data["hp"]{current,max}` for the
  player and `world_state["npcs"][id]{"hp","max_hp"}` for NPCs; zero sets
  `lifecycle="dead"`. Compare the numbers in the narration with the rows.

### 4.3 NPC dialogue

- **State**: an NPC present (`npcs_present`), so the `social` tool group is
  active (`saga.config.yaml:301-308`).
- **Action**: `"I ask the innkeeper what he knows about the road."`
- **Expect**: one `invoke_npc`, `npc_dialogues` in the response, the line used
  **verbatim** in the narration, psychology axes moved only if the exchange
  justifies it.
- **Watch**: `dm_tools_executor.py:90-138` → `invoke_npcs_parallel`
  (`ai/npc_director.py`), then `_handle_npc_results` (`:278-323`). Compare the
  NPC's produced line with the narrated one character by character — paraphrasing
  is a known failure mode and the reason ADR 0017 exists.

### 4.4 Memory

- **State**: at least two turns in the same campaign, with a fact worth keeping.
- **Action**: two consecutive turns that should be linked.
- **Expect**: after turn 1, background fact extraction writes `memory_facts`,
  `source_embeddings` rows appear and the worker processes them; turn 2's prompt
  carries the fact in `<recalled_memories>`.
- **Watch**: `turns.py:235-247` → `memory/fact_extractor.py:105-173` (LLM call,
  parse, cap of 5, `enqueue_source_embedding` at `:153-160`);
  `memory/embedding_queue.py:58-81`; the worker in `memory/embedding_worker.py:93`.
  Recall is `context.py:119-137`. If embeddings fail, gameplay continues and
  recall is empty — verify **which** of the two you are looking at before calling
  it a bug.

### 4.5 Quest

- **State**: an active quest, or a scene offering one.
- **Action**: `"I take the job."`
- **Expect**: `update_quest` with a stable snake_case `quest_id`, the registry
  moving between its four lists, the journal following on the next turn, the save
  and the export carrying it.
- **Watch**: `ai/tools/tools_world.py:146-166` → `core/quests.py`
  (`apply_quest_update`), then `campaigns.quests` (JSONB — there is no `quests`
  table) and the `<quests>` block in the next prompt. `quest_update` in
  `memory/updater.py:168-171` is retired; if you see it fire, that's a finding.

## 5. Reading a failure

Ask in this order, and stop at the first yes:

1. **Did the request even arrive?** `docker compose logs backend`, or the debug
   console. 401/404/422 before the graph means auth or validation, not the DM.
2. **Did the graph run?** Breakpoint at `turns.py:125`. No hit → the request died
   earlier.
3. **Did the model answer?** Breakpoint at `dm_nodes.py:120`. Empty content, a
   refusal, or a malformed tool call is a model finding, not engine logic.
4. **Did the tool run?** `tool_events` in the response, or a breakpoint in
   `tools_node`. A `Tool … failed: …` string is the sanitized path
   (`tools_base.py:178-184`) — the original exception is only in the logs.
5. **Did it persist?** Read the row, not the response. A response can carry state
   the transaction rolled back.
6. **Is it the frontend?** Response correct + UI wrong → frontend. Response wrong →
   backend. Check in that order, never the reverse.

## 6. Triage: what to do with a finding

| Kind | Where it goes |
|---|---|
| Reproducible code defect | GitHub issue (`type(scope): …`), then a targeted fix with a test |
| Prompt / model behaviour | Note for the tuning pass (gated by ADR 0004); do not patch the prompt on the spot |
| Missing feature or design fork | `TODO.md` or a new ADR |
| Migration or refactor need | Explicit owner authorization first |

No migrations, no refactors, no releases inside a debugging session.

## 7. Frontend

The dev server proxies `/api` to `http://backend:8000` by default — a Docker
hostname. Outside compose, point it at the debugged backend:

```bash
cd frontend
VITE_DEV_PROXY_TARGET=http://localhost:8000 bash ../scripts/with_node.sh npm run dev
```

Order of inspection:

1. **Network** → `POST /api/campaigns/{id}/action`: request body, status, response
   JSON. `TurnResponse` shape in `backend/app/schemas/campaign.py:54-77`.
2. **Store** → `shared/stores/game-store.ts` (`addTurn:38`, `updateWorldState:52`,
   `updateCharacter:63`, `updateQuests:74`, `updateTurnNumber:80`), driven from
   `features/game/hooks/use-submit-action.ts:22-36`.
3. **Component** → `features/game/components/game-view.tsx`.
4. **Console** → in dev the turn response is also validated against a zod schema
   (`shared/schemas/turn.ts`); a shape drift shows up there before it shows up in
   the UI.

CORS allows only `http://localhost:3000` (`main.py:57-63`); a different port
looks like "nothing works" while the backend is healthy.

## 8. Inspecting the DB

```bash
docker compose exec db psql -U saga -d saga
```

```sql
select turn_number, quests, jsonb_pretty(character_data->'hp') from campaigns;
select turn_number, player_action, left(narration, 120) from turns order by turn_number desc limit 3;
select id, entity_name, left(fact, 90) from memory_facts order by created_at desc limit 10;
select source_type, work_state, count(*) from source_embeddings group by 1,2;
select version_num from alembic_version;
```

There is no `quests` table (JSONB on `campaigns`) and no ANN index — similarity is
an exact scan, so recall cost grows with the fact count.

## 9. Traps

- **`TEST_DATABASE_URL` must never point at the dev DB.** The test fixtures
  `TRUNCATE … CASCADE` every table (`backend/tests/conftest.py:50-64`). Use the
  compose test service on `5433`.
- **`.env` is read relative to the CWD** (`backend/app/config.py:54`), and
  `backend/.env` does not exist. Without the launch config's `envFile`, the
  backend silently runs on defaults — including a placeholder
  `API_KEY_ENCRYPTION_KEY`, which makes every stored key unreadable
  (`ai/credentials.py:96-100`).
- **`DATABASE_URL` in the root `.env` says `db:5432`** — correct inside compose,
  wrong on the host. That is why the launch config overrides it.
- **Startup runs migrations and can refuse to boot** (`dependencies.py:11-14` →
  `migrations/runner.py:21-39`). A boot failure that mentions `alembic_version`
  is schema, not code.
- **Two backends on 8000**: the compose service and the debugger cannot share the
  port.
- **Background work is fire-and-forget** (`turns.py:235-256`). A breakpoint there
  does not stop the response, and an exception there appears only in the logs.
- **`--reload` silently kills breakpoints.** The launch configs never pass it.

## 10. What "correct" looks like

- A plain turn writes only what it narrates: one `turns` row, one auto-save,
  embedding rows if something was queued.
- A failed tool leaves no partial state: the sanitized error goes back to the
  model, the turn still completes.
- No stack trace or internal path ever reaches the model (std 13).
- Numbers in the narration come from `dice_results` and HP deltas, never from the
  prose.
