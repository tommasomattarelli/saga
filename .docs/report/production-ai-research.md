# SAGA/Wyrd — Production Readiness & AI DM Architecture Research Report

---

## PART 1: Infrastructure & Production Readiness

### 1.1 Circuit Breaker & LLM Fallback

| Problema | Soluzione Industry Standard | Libreria/Tool |
|----------|---------------------------|---------------|
| No LLM fallback/retry | **LiteLLM Router** come abstraction layer con fallback chain e cost tracking | `litellm` v1.x + `tenacity` v8.x |
| No prompt caching | **Anthropic prompt caching** (zero infra, -60-70% costi) + semantic cache con Redis Stack HNSW | `redis-py` + Redis Stack |
| DB session held during streaming | **PgBouncer in transaction mode** + session scoping per-turn, non per-WebSocket | PgBouncer v1.22+ |
| No horizontal WS scaling | **Redis Pub/Sub** con WebSocket connection manager | `redis-py` pub/sub |
| Eager loading ORM | **Keyset pagination** per i turns, `lazy="noload"` | SQLAlchemy async |
| No backpressure streaming | **80ms token buffering** lato server prima di inviare via WS | Custom buffer |
| No rate limiting | **slowapi** (wrapper FastAPI di `limits`) | `slowapi` |

**Highest-ROI change**: Anthropic prompt caching — zero nuova infrastruttura, riduzione costi immediata del 60-70%.

### 1.2 LLM Prompt Caching & Semantic Caching

- **Anthropic prompt caching**: mark static system prompt blocks as cacheable; subsequent calls with the same prefix get a cache hit at ~10% of the cost. No new infrastructure needed.
- **Semantic caching with Redis**: use Redis Stack's HNSW vector index to cache LLM responses keyed by embedding similarity. If a new prompt is semantically close (cosine > 0.95) to a cached one, return the cached response. Best for deterministic calls (fact extraction, memory compression, world simulation).
- **Cost tracking**: LiteLLM Router provides built-in token counting and cost reporting per model/provider. Essential for optimizing the importance-based routing tiers.

### 1.3 PostgreSQL Connection Pooling

- **PgBouncer in transaction mode** is the standard for long-lived connections (WebSockets). Each query gets a connection from the pool, releases it immediately after the transaction.
- **Session scoping**: open a fresh SQLAlchemy async session per turn processing cycle, not per WebSocket lifetime. This prevents holding a connection idle during 5-30s LLM streaming.
- **Pool sizing**: `max_overflow` should be set to handle burst load (e.g., multiple campaigns processing turns simultaneously).

### 1.4 Redis Pub/Sub vs Redis Streams for WebSocket Scaling

- **Redis Pub/Sub**: fire-and-forget, low latency, ideal for real-time WebSocket event broadcasting. If a subscriber is offline, the message is lost — acceptable for ephemeral game events (streaming tokens, UI updates).
- **Redis Streams**: persistent, consumer groups, replay capability. Better for durable events (turn completion, world state changes) where missed messages must be recovered.
- **Recommendation**: use Pub/Sub for streaming tokens and ephemeral UI events; use Streams for turn completion and state change events that must be guaranteed.

### 1.5 Backpressure Handling for LLM Streaming

- **80ms token buffering**: accumulate LLM tokens for a short window before flushing to the WebSocket. Reduces frame overhead and provides implicit backpressure.
- **WebSocket write buffer monitoring**: check `websocket.client_state` before sending; if the write buffer is full, pause consuming from the LLM stream.
- **Client-side throttling**: use `requestAnimationFrame` or a 50ms debounce on the frontend to batch DOM updates from streaming tokens, instead of re-rendering on every single token.

### 1.6 SQLAlchemy Async Lazy Loading

- Change `lazy="selectin"` to `lazy="noload"` or `lazy="raise"` on `Campaign.turns` and `Campaign.saves`.
- Load turns explicitly only when needed, using keyset pagination (WHERE turn_number > last_seen ORDER BY turn_number LIMIT N) instead of loading the entire history.
- Use `selectinload()` explicitly in queries that actually need related objects, rather than defaulting to eager loading on the model.

### 1.7 PostgreSQL Hybrid Search (pgvector + tsvector + RRF)

- **Reciprocal Rank Fusion (RRF)**: combine vector similarity ranking with full-text search ranking using the formula `1/(k+rank)` for each result, then sum across both rankings. Standard k=60.
- **Implementation**: run two CTEs — one for vector cosine distance (`ORDER BY embedding <=> query_embedding`), one for tsvector relevance (`ORDER BY ts_rank(search_vector, to_tsquery(...))`). Join by ID and compute RRF score.
- **Populate `search_vector`**: use a PostgreSQL trigger on INSERT/UPDATE to automatically compute `to_tsvector('english', content)`, or populate explicitly in the fact extractor.
- **Add cosine distance threshold** (< 0.5) to filter irrelevant vector results before fusion.

### 1.8 Production Rate Limiting

- **slowapi** wraps the `limits` library for FastAPI. Apply per-user and per-campaign rate limits on turn submission (e.g., 1 concurrent turn per campaign, 10 turns per minute per user).
- **Redis-backed rate limiting** for distributed deployments (multiple server instances sharing rate limit state).
- **WebSocket rate limiting**: track message frequency per connection; disconnect clients exceeding thresholds.

---

## PART 2: AI Dungeon Master Agent — State of the Art

### 2A. AI DM Agent Architecture

#### Single Prompt vs Multi-Agent Decomposition

- **Industry trend (2025-2026)**: multi-agent with a coordinator. The DM is decomposed into specialized sub-agents:
  - **Narrator Agent**: generates descriptive prose, manages tone and pacing
  - **Rules Judge Agent**: determines when dice checks are needed, adjudicates mechanics (structured output, deterministic)
  - **NPC Agent**: manages NPC dialogue, personality, and decision-making
  - **World Simulator Agent**: advances world state independently of player actions (faction movements, weather, economy)
- **LangGraph StateGraph** with `AsyncPostgresSaver` is the current best framework for orchestrating stateful multi-agent workflows with persistence.

#### LLM-as-Judge for Rule Adjudication

- Separate structured-output call dedicated to rules: "Given this player action and game state, does this require a dice check? If so, what type (ability check, saving throw, attack roll), what DC, and what modifiers apply?"
- Use **`instructor`** library (v1.x) with Pydantic models to guarantee structured output from the LLM.
- **Critical rule**: the LLM decides WHEN a dice check is needed, but NEVER rolls the dice. Dice are always deterministic code. This is what separates a game engine from a chatbot.

#### Infinite Action Space Problem

- **Constraint framing**: the system prompt establishes what is physically possible in the world, and the Rules Judge validates actions against world state before narration.
- **Graceful failure**: if a player attempts something impossible, the DM should narrate the attempt and its failure, not refuse the input.
- **Action classification**: categorize player input (combat, social, exploration, creative) to route to the appropriate sub-agent.

#### Long-Running Stateful Sessions

- **State checkpointing**: serialize full game state to PostgreSQL at each turn boundary, enabling resume from any point.
- **Context window management**: aggressive summarization of old turns, with RAG retrieval for thematically relevant past events.
- **Session recovery**: on reconnect, rebuild context from the last checkpoint + recent turns + semantic retrieval.

### 2B. Prompting Best Practices for RPG AI

#### 4-Layer System Prompt Architecture

1. **Layer 1 — DM Persona**: consistent voice, tone, narrative style. "You are a veteran Dungeon Master..."
2. **Layer 2 — World Context**: current world state (JSONB), active quests, NPC locations, time of day, weather
3. **Layer 3 — Memory Retrieval**: semantically relevant past events retrieved via RAG (pgvector hybrid search)
4. **Layer 4 — Recent Turns**: last N turns of conversation for immediate context

#### Chain-of-Thought Scratchpad

- **DMResponse Pydantic model** with a `scratchpad` field: the DM "thinks" before narrating (considers rules, NPC motivations, world consequences).
- The scratchpad is used for reasoning but **never shown to the player**.
- This dramatically improves consistency for complex multi-step decisions (combat with multiple NPCs, branching quest logic).

#### Dice Mechanic Integration

- Prompt structure: "If the player's action requires a skill check, ability check, saving throw, or attack roll, output a `dice_request` object specifying the type, DC, and relevant modifiers. Do NOT narrate the outcome — wait for the dice result."
- After dice are rolled (by deterministic code), a **second LLM call** narrates the outcome incorporating the result.
- This two-phase approach (request dice -> narrate result) is critical for mechanical fairness.

#### Preventing Common Failure Modes

| Failure Mode | Prevention Technique |
|-------------|---------------------|
| Repetitive narration | Inject recent narration summaries into prompt with instruction "vary your descriptions, do not repeat phrases from recent turns" |
| Ignoring player actions | Structured output requiring an `action_acknowledgment` field that must reference the player's specific input |
| Breaking character | Strong persona anchoring in Layer 1, with few-shot examples of correct DM voice |
| Losing track of NPCs/quests | Inject active NPC list and quest tracker from world state (Layer 2) into every prompt |
| Contradicting established facts | RAG retrieval of relevant past events (Layer 3) + fact consistency check in scratchpad |

### 2C. Competitor & Market Analysis

#### AI Dungeon
- **Approach**: pure narrative LLM, no game mechanics, context-only memory
- **Tech**: custom fine-tuned models, no structured output
- **Strength**: pioneer, large user base, creative freedom
- **Weakness**: no dice, no rules, no persistent world state, frequent narrative inconsistency
- **Lesson for SAGA**: creative freedom is valued, but players also want mechanical fairness

#### Loom (Hidden Door)
- **Approach**: licensed IP (Wizard of Oz, etc.) + RAG on lore databases
- **Tech**: proprietary, RAG-heavy architecture
- **Strength**: rich, consistent world-building from established IP
- **Weakness**: closed ecosystem, not generalizable, limited player agency
- **Lesson for SAGA**: RAG on lore/world state is essential for consistency

#### Narrat
- **Approach**: open-source visual novel engine with scripted branching
- **Tech**: TypeScript, web-based
- **Strength**: open source, good tooling, visual novel format
- **Weakness**: scripted not AI-driven, limited emergent gameplay
- **Lesson for SAGA**: good open-source community practices, UI/UX patterns for narrative games

#### Roleplay.ai / Character.ai
- **Approach**: character-focused chat, no game mechanics
- **Tech**: fine-tuned models for persona consistency
- **Strength**: excellent persona maintenance, emotional engagement
- **Weakness**: no mechanics, no world state, no game structure
- **Lesson for SAGA**: persona consistency techniques for NPC agents

#### Endless RPG
- **Approach**: mobile RPG with basic AI-driven encounters and dice mechanics
- **Tech**: Unity + cloud LLM calls
- **Strength**: actual dice mechanics integrated with AI narration
- **Weakness**: very simplified mechanics, limited narrative depth
- **Lesson for SAGA**: closest competitor in the "AI + dice" space, but much simpler

### SAGA/Wyrd Differentiation

**No existing competitor combines all four of these:**
1. **Structured, deterministic dice mechanics** (not LLM-generated random numbers)
2. **Semantic memory via pgvector RAG** (thematic recall of past events)
3. **Living world state** (persistent JSONB with faction AI, NPC psychology, independent world progression)
4. **Open source and self-hostable** (data sovereignty, campaign export/import)

This is both the opportunity (clear market gap) and the risk (solving all four simultaneously is technically challenging, and no one has proven the market for a fully-featured AI DM engine).

---

## Key Library Versions (2025-2026)

| Library | Version | Purpose |
|---------|---------|---------|
| `litellm` | v1.x | LLM Router with fallbacks, cost tracking, provider abstraction |
| `tenacity` | v8.x | Retry with exponential backoff for LLM calls |
| `slowapi` | latest | FastAPI rate limiting (wraps `limits`) |
| `langgraph` | v0.2+ | StateGraph for multi-agent DM orchestration, AsyncPostgresSaver |
| `instructor` | v1.x | Pydantic structured output from LLMs |
| PgBouncer | v1.22+ | Connection pooling in transaction mode |
| Redis Stack | latest | HNSW vector index for semantic caching |
