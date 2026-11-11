# saga.config.yaml — Configuration Reference

All game-tunable settings live in `saga.config.yaml` at the project root. Secrets and infrastructure settings (DB URLs, JWT keys, API keys) stay in `.env` / `backend/app/config.py`.

Supported gameplay environment overrides use `SAGA_GAMEPLAY_<FIELD>`, for example `SAGA_GAMEPLAY_MAX_AGENT_STEPS=8`. Memory-production policy is configured in YAML, not through retired per-turn memory overrides.

## Database migrations

`migrations.lock_timeout_seconds` sets the finite wait for another process to
finish an online schema migration. The default is `30`; a timeout aborts startup
or the Alembic command rather than serving an unchecked schema. It must be a
positive finite number.

---

## OpenRouter session affinity

```yaml
generation:
  openrouter_session_affinity: true
```

Enabled by default. Generation requests made during a campaign action send that
campaign's UUID as `x-session-id` **only when the resolved provider is OpenRouter**.
DM steps, NPCs and memory jobs spawned by the action share the ID across turns;
background tasks retain their originating campaign after the request completes.
Requests outside a campaign scope have no added session header. Embedding
requests and other providers are unchanged.

The header is applied on an isolated provider/client copy, never on the cached
shared client. Existing headers, retry policy, credentials, model selection and
fallback consent remain unchanged. Set this boolean to `false` to disable it.

Affinity favors routing continuity, not guaranteed cache hits or fixed provider
selection. Prompt content, state refresh, summaries and tool availability are not
changed to improve cache reuse. Evaluation has its own suite/model affinity;
see [`backend/eval/README.md`](../backend/eval/README.md#session-affinity).

## Memory production and action deadlines

`memory.production` is validated and copied into an immutable `MemoryPolicy` when
a campaign is created. YAML changes affect new campaigns only; they do not
repartition existing histories or reset job attempts. Restart the backend after
editing the YAML, which is cached in each process.

| Setting under `memory.production` | Branch value | Meaning |
|---|---|---|
| `raw_turns` / `batch_turns` | `8` / `4` | Protected complete turns / turns per compaction batch |
| `intermediate_limit` / `backlog_batches` | `2` / `1` | Normal intermediate count / additional backlog allowance |
| `facts.max_per_batch` | `6` | Validated output maximum, never silent slicing |
| `facts.importance_levels` | `ordinary`, `critical` | Shared prompt and validation rubric |
| `global.target_words` | `1000` | Indicative target, not mechanical truncation |
| `jobs.max_attempts` | `4` | Initial attempt plus at most three automatic retries |
| `jobs.retry_backoff_seconds` | `[5, 30, 120]` | Delays before those retries |
| `jobs.request_timeout_seconds` / `lease_seconds` | `120` / `150` | Entire specialist attempt / publication lease |
| `jobs.poll_seconds` | `5` | Durable worker scan interval |
| `admission.wait_timeout_seconds` | `10` | Pre-claim wait before returning `memory_busy` |

These values and the specialist variant remain subject to the integrated quality
evaluation before release. The raw ceiling is 16; projected intermediate pressure
is capped at 4, including complete raw batches still awaiting production. A blocked
action consumes neither a request slot nor a turn number. Exhausted or
configuration-blocked memory work requires an explicit retry; loading a save does
not reset its historical attempt count.

Action transport settings are runtime-global, not campaign policy snapshots:

| Setting under `gameplay` | Value | Derived deadline |
|---|---|---|
| `action_timeout_seconds` | `600` | Accepted DM graph execution |
| `action_completion_margin_seconds` | `50` | Request token and client: `600 + 50 = 650` seconds |
| `action_proxy_margin_seconds` | `80` | Future proxy minimum: `600 + 80 = 680` seconds |

The authenticated `GET /api/runtime-config` exposes only the calculated
`action_client_timeout_seconds`; the frontend applies it to action requests, with
no duplicate numeric timeout in its bundle. The client budget includes admission
waiting, so the completion margin must exceed that wait; the proxy margin must
exceed the completion margin. There is no proxy in the current deployment.

Network timeout does not prove that a turn failed. Retries retain their logical
request ID and expected head/epoch; a committed result is replayed without another
generation, or reported historical if the active context changed. Interrupted
accepted actions are not regenerated automatically.

Per-turn compression, TURN-summary embedding work, silent context trimming and
their legacy settings are retired. Only fact content is eligible for new embedding
work or rebuilds; historical summaries remain readable and exportable.
Pre-contract campaigns and saves remain readable but cannot enter the new action
or restore path through automatic conversion.

## Legacy routing reference

SAGA routes AI calls across multiple call types. Each type can be configured independently with provider, model, temperature, and max_tokens.

### `dm_narration` — DM narrative generation

Three tiers selected by scene importance score (0-10, computed from player action content + world state):

```yaml
dm_narration:
  low:      # importance 0-3: routine exploration, simple responses
    provider: google
    model: gemini-3.5-flash
    temperature: 0.8
    max_tokens: 2000
  medium:   # importance 4-6: normal gameplay
    provider: google
    model: gemini-3.5-flash
    temperature: 0.8
    max_tokens: 3000
  high:     # importance 7-10: boss fights, dramatic reveals, story peaks
    provider: google
    model: gemini-3.1-pro
    temperature: 0.9
    max_tokens: 4000
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `provider` | string | `google` | `google` \| `openai` \| `openrouter` \| `local` |
| `model` | string | `gemini-3.5-flash` | Any model supported by the provider |
| `temperature` | float | `0.8`–`0.9` | Higher = more creative, lower = more predictable (if supported by the provider)|
| `max_tokens` | int | `20000`–`40000` | Output token limit. Increase for longer narrations. |

**When to change**: Switch `high.model` to a premium model (e.g. `gemini-3.1-pro`, or a Claude model on `provider: openrouter`) for better narrative quality at dramatic peaks. Keep `low.model` cheap for routine turns.

Direct `provider: anthropic` is no longer supported and fails without fallback.
To use Claude, explicitly select `openrouter`, an OpenRouter model ID and your
OpenRouter key; Anthropic keys are not interchangeable. Historical encrypted keys
are retained, and legacy `ANTHROPIC_API_KEY` entries are accepted but unused.

---

### `companion_dialogue` — Companion speech

```yaml
companion_dialogue:
  default:
    provider: google
    model: gemini-3.5-flash
    temperature: 0.7
    max_tokens: 15000
```

**When to change**: Increase `max_tokens` if companions are cutting off mid-sentence. Switch to a better model for richer companion personalities.

---

### `npc_behavior` — NPC Director responses

```yaml
npc_behavior:
  default:
    provider: google
    model: gemini-3.5-flash
    temperature: 0.7
    max_tokens: 10000
```

NPC calls are high-volume (one per `invoke_npc` per turn). Keep this on a fast, cheap model. JSON mode is always enabled; output is `{dialogue, action, disposition_change, reveals_secret}`.

**When to change**: If NPC dialogue feels generic, try a higher-quality model at the cost of latency.

---

### `world_sim` — World simulation (future)

```yaml
world_sim:
  default:
    provider: google
    model: gemini-3.5-flash
    temperature: 0.5
    max_tokens: 1500
```

Currently unused (world simulation is a v2 feature). Lower temperature for deterministic world-state mutations.

---

### Embedding sources

Published batch facts enqueue their `content` in the versioned embedding index.
Embedding provider/model settings are separate from generation settings; changing
the embedding space uses the existing rebuild lifecycle, never mixed vectors.
See [ADR 0018](adr/0018-byoak-personal-config-and-embedding-index.md).

---

## Gameplay Settings

```yaml
gameplay:
  default_campaign_language: en
  npc_verbosity: "medium"
  semantic_resolver_enabled: false
  max_agent_steps: 8
  auto_create_npcs: true
  npc_auto_create_detail: standard
  consecutive_empty_steps_max: 2
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `npc_verbosity` | string | `medium` | NPC response length: `null` (0 sentences) \| `minimal` (1) \| `low` (2) \| `medium` (3) \| `high` (5) \| `unlimited` |
| `semantic_resolver_enabled` | bool | `false` | Disabled in v1. Will enable NPC filtering + intent classification in v1.5. |
| `default_campaign_language` | string | `en` | ISO 639-1 target persisted for new campaigns; existing campaigns retain their selection across saves and global-default changes. |
| `max_agent_steps` | int | `8` | Hard DM-call cap; the last call exposes only active `advance_time`, `set_scene_mood`, `log_event`. Actor calls are separate; graph recursion is derived from this cap. Override with `SAGA_GAMEPLAY_MAX_AGENT_STEPS`. |
| `auto_create_npcs` | bool | `true` | If `invoke_npc` is called for an NPC not in `world_state`, auto-create a minimal profile. |
| `npc_auto_create_detail` | string | `standard` | Detail level for auto-created NPC profiles: `minimal` \| `standard` \| `rich` |
| `consecutive_empty_steps_max` | int | `2` | Consecutive steps without state change or fresh playable dice/NPC results force a terminal-safe closing call within the remaining budget; repeated identical request/results without new effects stall, regardless of prose. |

### `npc_auto_create_detail` — what gets created

| Value | Fields |
|-------|--------|
| `minimal` | name, location, disposition=0 |
| `standard` | + role, personality, motivation, last_interactions=[] |
| `rich` | + secret, fear |

---

## Feature Toggles

```yaml
features:
  npc_enrichment:
    enabled: false
  world_sim:
    enabled: false
```

### `features.npc_enrichment` [v1.5]

When enabled, the NPC Director will call an LLM to enrich the NPC profile before generating dialogue. Currently disabled — the pre-hook provides baseline profile from template + world_state without an extra LLM call.

### `features.world_sim` [v2]

Autonomous world simulation agent that evolves factions and NPCs between player turns. Disabled until v2.

---

## Tool Groups

```yaml
tool_groups:
  core:
    always: true
    tools: [move_to, advance_time, set_scene_mood, log_event, update_quest]
  combat_entry:
    always: true
    tools: [start_combat]
  combat:
    when: combat_active
    tools: [request_dice, apply_damage, end_combat, update_hp]
  social:
    when: npcs_present
    tools: [invoke_npc, change_npc_disposition]
  inventory:
    always: true
    tools: [add_item, remove_item]
```

Tool groups control which tools the DM can see in each turn. The DM should never have more than ~12 tools simultaneously (empirical reliability limit for medium models).

### Activation conditions

| Condition | When true |
|-----------|-----------|
| `always: true` | Every turn |
| `when: combat_active` | `world_state.combat_state.active == true` |
| `when: npcs_present` | At least one NPC in `world_state.npcs` has `location == current_location` |
| `when: companion_active` | [v1.5] At least one companion in `world_state.companions` |

### Adding a new tool group

1. Implement the tool class in `app/ai/tools/dm_tools.py` (subclass `DmTool`, use `@_register`)
2. Add the group to `saga.config.yaml` under `tool_groups`
3. Add activation condition handling in `app/ai/tools/tool_groups.py` if using a new condition
4. No code changes needed for existing conditions

---

## Global Provider Override

You can override all model sections at once using global provider settings. These are typically set via environment variables rather than in the config file:

```
SAGA_GLOBAL_PROVIDER=openai
SAGA_GLOBAL_MODEL_HIGH=gpt-5.5
SAGA_GLOBAL_MODEL_LOW=gpt-5.4-mini
```

Individual section overrides take precedence over global settings.

---

## Configuration Tips

Tune `memory.production.raw_turns`, `batch_turns` and `intermediate_limit`
together using measured prompt sizes and reviewed memory quality. Larger batches
reduce generation frequency but increase each request's input; fewer raw turns
reduce verbatim context, not the requirement for complete published replacements.
Do not use removed toggles or truncation settings to bypass memory admission.
