# saga.config.yaml — Configuration Reference

All game-tunable settings live in `saga.config.yaml` at the project root. Secrets and infrastructure settings (DB URLs, JWT keys, API keys) stay in `.env` / `backend/app/config.py`.

Environment variable overrides are supported for all fields using the pattern `SAGA_<SECTION>_<FIELD>` (uppercase, underscores). Example: `SAGA_GAMEPLAY_CONTEXT_WINDOW_TURNS=12`.

---

## Model Routing

SAGA routes AI calls across multiple call types. Each type can be configured independently with provider, model, temperature, and max_tokens.

### `dm_narration` — DM narrative generation

Three tiers selected by scene importance score (0-10, computed from player action content + world state):

```yaml
dm_narration:
  low:      # importance 0-3: routine exploration, simple responses
    provider: google
    model: gemini-2.5-pro
    temperature: 0.8
    max_tokens: 2000
  medium:   # importance 4-6: normal gameplay
    provider: google
    model: gemini-2.5-pro
    temperature: 0.8
    max_tokens: 3000
  high:     # importance 7-10: boss fights, dramatic reveals, story peaks
    provider: google
    model: gemini-2.5-pro
    temperature: 0.9
    max_tokens: 4000
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `provider` | string | `google` | `google` \| `openai` \| `anthropic` \| `local` |
| `model` | string | `gemini-2.5-pro` | Any model supported by the provider |
| `temperature` | float | `0.8`–`0.9` | Higher = more creative, lower = more predictable |
| `max_tokens` | int | `2000`–`4000` | Output token limit. Increase for longer narrations. |

**When to change**: Switch `high.model` to a premium model (e.g. `claude-opus-4-7`) for better narrative quality at dramatic peaks. Keep `low.model` cheap for routine turns.

---

### `companion_dialogue` — Companion speech

```yaml
companion_dialogue:
  default:
    provider: google
    model: gemini-2.5-flash
    temperature: 0.7
    max_tokens: 1500
```

**When to change**: Increase `max_tokens` if companions are cutting off mid-sentence. Switch to a better model for richer companion personalities.

---

### `npc_behavior` — NPC Director responses

```yaml
npc_behavior:
  default:
    provider: google
    model: gemini-2.5-flash
    temperature: 0.7
    max_tokens: 1000
```

NPC calls are high-volume (one per `invoke_npc` per turn). Keep this on a fast, cheap model. JSON mode is always enabled; output is `{dialogue, action, disposition_change, reveals_secret}`.

**When to change**: If NPC dialogue feels generic, try a higher-quality model at the cost of latency.

---

### `world_sim` — World simulation (future)

```yaml
world_sim:
  default:
    provider: google
    model: gemini-2.5-flash
    temperature: 0.5
    max_tokens: 1500
```

Currently unused (world simulation is a v2 feature). Lower temperature for deterministic world-state mutations.

---

### `memory_compression` — Turn summarization

```yaml
memory_compression:
  default:
    provider: google
    model: gemini-2.5-flash
    temperature: 0.3
    max_tokens: 500
```

Summarizes batches of turns into 2-3 sentence summaries for the `<history>` block. Very low temperature for factual, consistent compression. Runs async post-turn (non-blocking).

**When to change**: Rarely. If summaries are inaccurate, try a slightly higher temperature (0.4–0.5) or better model. Don't exceed 600 max_tokens — summaries should be concise.

---

### `embedding` — pgvector embeddings

```yaml
embedding:
  default:
    provider: google
    model: text-embedding-004
    dimensions: 1536
```

Used by `fact_extractor` for MemoryFact embeddings and `search_similar_facts` for semantic recall. **Do not change `dimensions` after the database has been populated** — it would require a full pgvector column migration.

---

## Gameplay Settings

```yaml
gameplay:
  context_window_turns: 8
  context_token_cap: 12000
  npc_verbosity: "medium"
  compression_enabled: true
  fact_extraction_enabled: true
  semantic_resolver_enabled: false
  max_agent_steps: 5
  pgvector_hybrid: false
  auto_create_npcs: true
  npc_auto_create_detail: standard
  consecutive_empty_steps_max: 2
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `context_window_turns` | int | `8` | Verbatim turns kept in `messages[]` (the Active Window). Higher = more context, more tokens. |
| `context_token_cap` | int | `12000` | Max estimated tokens in the DM prompt. If exceeded, oldest verbatim turn pairs are dropped (newest always preserved). |
| `npc_verbosity` | string | `medium` | NPC response length: `null` (0 sentences) \| `minimal` (1) \| `low` (2) \| `medium` (3) \| `high` (5) \| `unlimited` |
| `compression_enabled` | bool | `true` | Whether to run async batch summarization after each turn. Disable only for debugging. |
| `fact_extraction_enabled` | bool | `true` | Whether to extract and store MemoryFacts after each turn. Powers pgvector recall. |
| `semantic_resolver_enabled` | bool | `false` | Disabled in v1. Will enable NPC filtering + intent classification in v1.5. |
| `max_agent_steps` | int | `5` | Hard cap on LangGraph loop iterations per turn. Prevents runaway tool loops. |
| `pgvector_hybrid` | bool | `false` | Enable hybrid RRF search (vector + tsvector) for semantic recall. v1.1 feature flag. |
| `auto_create_npcs` | bool | `true` | If `invoke_npc` is called for an NPC not in `world_state`, auto-create a minimal profile. |
| `npc_auto_create_detail` | string | `standard` | Detail level for auto-created NPC profiles: `minimal` \| `standard` \| `rich` |
| `consecutive_empty_steps_max` | int | `2` | After this many agent steps with no narration text (only silent tools), force loop exit. Prevents infinite fire-and-forget loops. |

### `npc_auto_create_detail` — what gets created

| Value | Fields |
|-------|--------|
| `minimal` | name, location, disposition=0 |
| `standard` | + role, personality, motivation, last_interactions=[] |
| `rich` | + secret, fear |

---

## Summarization

```yaml
summarization:
  max_retries: 3
  retry_delays_seconds: [1, 5, 30]
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | int | `3` | LLM retry attempts before marking `Turn.summarization_failed = True` |
| `retry_delays_seconds` | list[int] | `[1, 5, 30]` | Delay before each retry (exponential backoff). Length must equal `max_retries`. |

On final failure the turn is marked `summarization_failed=True` and no summary is stored. The batch is skipped in the `<history>` block for that turn range, but the campaign continues normally.

---

## Feature Toggles

```yaml
features:
  global_summary:
    enabled: true
    mode: llm
    interval_turns: 5
  npc_enrichment:
    enabled: false
  world_sim:
    enabled: false
```

### `features.global_summary`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable rolling campaign summary. Injected as `<global_summary>` in every system prompt. |
| `mode` | string | `llm` | `llm` (LLM-generated, anchored iterative extension) \| `rule_based` (concatenation fallback) |
| `interval_turns` | int | `5` | Update global summary every N turns. Lower = more up-to-date but more LLM calls. |

The global summary is a single ~200-word paragraph that captures the entire campaign arc so far. It is **extended** each cycle, never regenerated from scratch (anchored iterative approach prevents drift).

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
SAGA_GLOBAL_MODEL_HIGH=gpt-4o
SAGA_GLOBAL_MODEL_LOW=gpt-4o-mini
```

Individual section overrides take precedence over global settings.

---

## Configuration Tips

**Budget-constrained setup** — minimal LLM calls, still playable:
```yaml
dm_narration:
  low:
    model: gemini-2.5-flash
  medium:
    model: gemini-2.5-flash
  high:
    model: gemini-2.5-pro  # keep quality only for peaks
gameplay:
  context_window_turns: 6   # fewer verbatim turns = fewer tokens
  context_token_cap: 8000
features:
  global_summary:
    mode: rule_based         # no extra LLM call for summaries
```

**Quality-first setup** — best narrative experience:
```yaml
dm_narration:
  high:
    provider: anthropic
    model: claude-opus-4-7   # best narrative quality for dramatic moments
gameplay:
  context_window_turns: 12  # more verbatim context
  context_token_cap: 20000
  npc_auto_create_detail: rich
features:
  global_summary:
    mode: llm
    interval_turns: 3        # more frequent summary updates
```
