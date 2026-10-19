# ADR 0018 — BYOAK configuration contract: personal providers, credentials and the embedding index

- **Status**: **Proposed** (Part A and the personal configuration surface have landed on
  `main`; Part B is in progress on `feat/embedding-index` (point 5), and point 6 — the
  minimal provisional UI — remains open. The ADR stays Proposed until both points land:
  Part A already on `main` does not complete it.)
- **Date**: 2026-10-17.
- **Context items**: GitHub #65, #73, #74, #55 (all open); supersedes ADR 0016; builds on
  ADR 0000 (BYOAK distribution model).

Legend: **Decided** = settled by the owner. **TODO** = consciously open, with where it
gets resolved.

## 1. Context

BYOAK is SAGA's distribution model (ADR 0000): keys are entered from the UI, not from a
dialog. Today that documented flow is broken end to end, and the configuration surface
around it has drifted (all states verified in the 2026-10-17 session):

- **Personal keys are write-only.** `app/api/settings.py` encrypts and stores the
  `openai`/`anthropic`/`google` keys, reads them back only as `bool(...)` for the UI, and
  `decrypt_api_key` (`app/security/encryption.py`) is called from nowhere; every provider
  client is built from environment variables in `get_provider`
  (`app/ai/providers/base.py`). On a shared instance every call bills the host's key
  while the UI says otherwise.
- **Provider and model are composed independently.** `_get_config_for_call`
  (`app/ai/router.py`) applies `SAGA_GLOBAL_PROVIDER` and `SAGA_GLOBAL_MODEL_*`
  separately with no pair check: reproduced `openrouter + gemini-3.5-flash` from a
  provider-only override (#74), and the `default` tier of the background call types
  resolves to the medium model when the three global models are set (#73).
- **The declared config and the running code disagree on embeddings.** `saga.config.yaml`
  declares `google / text-embedding-004 / 1536`; `app/ai/embeddings.py` always calls
  `api.openai.com` with `text-embedding-3-small` at 384 dimensions; `AICallType.EMBEDDING`
  has zero uses (#55).
- **The frontend has no keys/provider/model surface at all** — the settings drawer has
  audio, motion and account, nothing else.
- **Vector storage is a fixed `Vector(384)` column** on `turns` and `memory_facts`, with
  no ANN index: recall is an exact sort filtered by campaign.

Two forces make this the right moment. First, the tier routing the old config was built
for no longer pays for itself: modern cheap models are strong enough that three cost tiers
are complexity without value, and the tiers are the root of #73. Second, the stabilization
plan schedules configuration and credentials (point 3) before quests and guided debugging,
because every later debug session runs on the wrong key until this is fixed.

**Out of scope:** Gemini thought-signature handling (#56 — a provider bug, point 4); the
full UI redesign (point 6 ships only a minimal, deliberately provisional surface);
`character_data` typing (ADR 0010 F1).

## 2. Part A — Personal generation configuration and credentials

### A1 — One generation model per user (Decided)

Each user picks one provider and one model, used by every generation call: DM narration,
NPC behaviour, companion dialogue, compression, fact extraction, global summary. The
low/medium/high tiers are **removed from the project**, not hidden. `importance_score`
survives only as turn metadata; it stops routing anything, which retires the class of
defects #73 and #74 belong to by construction, and supersedes ADR 0016.

### A2 — No temperature, one instance-wide output cap (Decided)

Temperature is removed everywhere: it is a legacy knob that reasoning models often reject
or ignore, and the provider defaults are the honest setting. In its place there is a
single output cap, instance-wide, `60000` tokens, declared in `saga.config.yaml` (std 14 —
no output number hardcoded in code). It is a runaway guardrail, not a tuning knob; the
existing `finish_reason == length` guard stays the truncation signal.

### A3 — Four providers; personal keys are the primary credential (Decided)

The provider set is `openai`, `openrouter`, `google`, `local`. `cohere` and `groq` are
removed from the code (point 3) — the long tail of providers is OpenAI-compatible and is
reached through `openrouter` or `local`; `anthropic` was already retired. Personal
encrypted keys are the primary credential of every generation and embedding call for
their provider: `openai`, `openrouter`, `google` carry keys; `local` is an endpoint
without a key (authenticated local endpoints are a later extension). Schema note: `User`
currently has `anthropic`/`openai`/`google` columns; the `openrouter` column and its
migration belong to point 3.

### A4 — Server-key fallback with double consent, key-absent only (Decided)

The existence of a server key says the credential is available, not that the operator
wants to pay for users' calls. Fallback therefore needs two independent consents:

- **Operator**: enables credential sharing per provider in `saga.config.yaml` (default
  off).
- **User**: accepts in settings, persistently, per provider — a settings choice, never an
  in-game popup.

The fallback fires **only when the personal key is absent**. A present key that is
rejected, rate-limited or out of quota shows its error; nothing silently moves the bill to
the operator. Fallback changes the credential only — never the provider or the model. The
UI shows the credential provenance (personal / consented server key / missing) without
ever exposing the key.

**Implementation note (2026-10-17).** Integration tests exposed raw SDK authentication
and quota errors becoming generic 500s; the turn executor now returns short provider
errors without exposing upstream payloads or retrying with the operator's key.

### A5 — Admin policy: one allowlist, named local endpoints (Decided)

One allowlist of enabled providers covers both generation and embeddings, with an
allow-all mode; local endpoints are a named list defined by the operator (e.g.
`ollama-home: http://host:11434`). Users select from that list; they never supply URLs —
the backend only ever contacts endpoints the operator named (SSRF containment).

### A6 — New users inherit the instance default (Decided)

Until a user configures their own, the instance default (provider + model) applies. The
first turn starts only when a usable credential exists — personal or consented fallback;
otherwise the error names exactly what is missing.

**Implementation note (2026-10-17).** Background tasks inherit only the owner's ID through
a scoped `ContextVar` and resolve their configuration in a short session before each call;
offline evaluation explicitly selects the operator context.

### A7 — Legacy environment variables are removed (Decided)

`SAGA_GLOBAL_PROVIDER`, `SAGA_GLOBAL_MODEL_HIGH/MEDIUM/LOW`, and
`SAGA_MODEL_<CALL_TYPE>_<TIER>[_PROVIDER]` are removed from the project: nothing reads
them any more, and a leftover value in `.env` is simply ignored — delete it. No implicit
conversion: the single-model contract is declared, never guessed.

### A8 — Where configuration lives (Decided)

Instance policy lives in `saga.config.yaml`, edited by hand and applied on restart (no
hot reload, no admin UI for now — the settings UI is redesigned later). Personal settings
and consents live in the database. Provider clients are cached keyed by provider **and**
credential: a global cache keyed by provider name alone would cross credentials between
users.

### A9 — Validation before the first turn (Decided)

Configuration is validated at startup and again before a turn: provider enabled, model
non-empty, credential available (personal or consented fallback). Errors are short and
human-readable (std 13). #74 disappears by construction: provider and model are chosen
together in one profile, and the legacy env layer that composed them independently is
gone.

## 3. Part B — Embeddings and the index lifecycle

### B1 — Separate personal embedding configuration (Decided)

Embedding provider and model are independent of the generation pair: e.g. generation on
OpenRouter with embeddings on a local Ollama model, or generation on OpenAI with
embeddings on OpenRouter. This closes #55. Correction to that report: OpenRouter now
documents an embeddings endpoint, so it is no longer accurate to say it has none.

### B2 — Local embedding endpoints are admin-named (Decided)

Same rule as A5: endpoints come from the operator's named list; the user picks an endpoint
and types the model name. SAGA never downloads or runs a model itself — it talks to an
external service (e.g. Ollama) the user or operator runs.

### B3 — Flexible vector storage with a per-row model label (Decided)

The vector columns drop their fixed `384` dimension; each row carries the label of the
model (and dimension) that produced it. Reads filter by campaign and by the active model:
vectors of different models are never compared, regardless of dimension. No ANN index is
introduced now — today there is none and recall is already a campaign-scoped exact sort;
an index is added only when measurements ask for it.

### B4 — Resumable, batched rebuild (Decided; trigger amended 2026-10-19)

Re-embedding is an explicit user action. It runs in the background, non-blocking, in
batches (arrays of texts per request — never one call per fact; batch size is a config
knob, std 14). It is resumable: state and progress are persisted, not held in a volatile
task, so an interrupted rebuild never reads as completed. Progress is visible in settings;
the game itself stays silent.

**Owner decision (2026-10-19).** The rebuild is also started by the campaign screen's
idempotent `ensure`, so a campaign nobody reopens spends nothing to adopt a new profile.
An interrupted rebuild resumes automatically after a restart, while a cancelled or failed
one moves again only through the user's explicit retry — see *Owner decisions
(2026-10-19)* below, which wins where it differs.

### B5 — The old index stays active; otherwise recall is silently suspended (Decided)

While a rebuild runs, recall keeps using the old index when the old model is still
reachable. If it is not, semantic recall is suspended silently for gameplay — the turn
still resolves with the remaining context mechanisms — while the condition is visible in
settings. When the rebuild completes, reads switch to the new index; old and new vectors
are never mixed.

### B6 — Rebuild sources already exist (Decided)

`Turn.summary` and `MemoryFact.content` are the embedding sources; the rebuild re-embeds
stored texts without regenerating history or facts.

### Owner decisions (2026-10-19, point 5)

These refine B1–B6; where they differ from the paragraphs above, they win. They are
owner decisions, not implementation notes — the point 5 code does not exist yet.

- **Separate storage.** Index versions and their vectors live in dedicated tables, not on
  the source rows; the sources keep their text and identity. Dimensionality is native: no
  personal reduction parameter, the observed dimension is bound to the index version, and
  a campaign with no texts makes no paid probe — the first real response fixes it. A
  version records the space identity — provider, model, endpoint (a URL change behind the
  same alias is a different space) and pipeline — so a key rotation never changes it.
  The storage contract fixes the tables: `embedding_indexes`, one row per index version,
  and `source_embeddings`, the per-source work queue.
- **The queue is the store.** A source's persisted records are the work queue and its
  progress — derived by counting them, not tracked in separate counters — so no separate
  job framework is introduced.
- **Rebuild trigger.** The campaign screen's idempotent `ensure` starts the rebuild for
  that campaign alone. The job is not tied to the browser tab: closing it does not stop
  the rebuild, and no heartbeat or player-presence detection is introduced.
- **Automatic resume vs explicit retry.** A rebuild interrupted (a restart, a backend
  shutdown) resumes automatically, revalidating the credential and policy. A cancelled or
  failed rebuild is never restarted by reopening the campaign — cancellation and failure
  must not become a paid loop — but restarts on the user's explicit retry (API now,
  point 6 UI later).
- **Profile change.** Changing the personal embedding profile requires cancelling that
  user's own campaigns' in-flight rebuilds first; an existing job is never retargeted.
  Editing keys or revoking consent stays always possible.
- **Suspension.** A job with no usable key or policy stops with a persisted reason, and
  the game proceeds. An old index is usable only with credentials and policy authorized
  today; recall that cannot run is suspended silently for gameplay and visible in
  settings.
- **Previous index retained.** The previous index is kept during the rebuild; there is no
  unlimited history and no rollback function. Cleanup is limited to replaced or cancelled
  versions, never the index still active.
- **Instance default (refines B1).** The default embedding profile is
  `openrouter / openai/text-embedding-3-small`, using only the OpenRouter key — not
  Google, not an OpenAI key. Google remains supported, and existing personal profiles are
  never rewritten.
- **Batching and pacing (B4 values).** Batches of 32 texts, at least one second between
  rebuild requests, one rebuild request at a time; the cadence is a config knob subject
  to the provider's documented limits.

## 4. Decided vs open

| Group | Items | State |
|-------|-------|-------|
| Part A | A1–A9 | Decided |
| Part B | B1–B6 | Decided |

Open TODOs, with where they resolve:

- Authenticated local endpoints (key optional) — future extension, not scheduled.

## 5. Implementation plan — point 3 (proposed commits)

The point 3 branch carries this ADR as its first commit; the sequence lands in 6–7
commits per the commit convention:

1. `docs(adr): add 0018 BYOAK configuration contract (ADR 0018)` — this document, the
   index row, the 0016 supersession, the CHANGELOG entry.
2. `feat(config): single-model provider configuration with startup validation (ADR 0018 A1–A2, A5–A7)`
   — rewrite `saga.config.yaml` (generation block, output cap 60000, provider allowlist,
   named local endpoints, instance default, embedding block; no tiers, no temperatures);
   startup validation; legacy env vars removed from the project and from .env.example.
3. `feat(auth): per-user provider settings and fallback consent (ADR 0018 A3–A4)` —
   settings API: personal generation and embedding configuration, `openrouter` key column
   (migration), per-provider consent for server fallback, credential provenance in the
   response.
4. `feat(ai): resolve the user credential on every call (ADR 0018 A3–A4, A8–A9)` — decrypt
   and use personal keys; consented fallback only when the key is absent; client cache
   keyed by provider and credential; readable pre-call validation errors.
5. `refactor(ai): retire tier routing and secondary providers (ADR 0018 A1–A2)` — remove
   tiers from the router, `score_importance` from routing, temperature plumbing,
   `cohere`/`groq`, and the dead env override layer.
6. `feat(ai): background jobs carry the user configuration (ADR 0018 A6)` — compression,
   fact extraction, global summary and the NPC director run with the owning user's
   resolved provider and model.
7. `test(ai): two-user isolation and consent end-to-end (ADR 0018 A)` — PostgreSQL
   integration: two users with distinct keys never share a client; fallback fires only
   when the key is absent; legacy env vars are ignored per A7; disabled providers are rejected.

## 6. Rejected alternatives

- **Keep low/medium/high tiers.** Complexity without value — modern cheap models are
  strong enough, and the tiers are the root of #73. Removed from the project, not hidden.
- **Per-call-type temperatures.** Legacy surface; reasoning models often reject or ignore
  it; provider defaults are fine.
- **Per-call-type output caps.** Same maintenance surface; one generous guardrail is
  enough.
- **Fixed-dimension vector column.** Excludes local models with different dimensions
  (384/768/1024 are all common).
- **Fixed 1536 with the `dimensions` parameter.** Covers cloud models only, excludes
  almost every local one.
- **Curated model catalog.** Ages fast and must be hand-maintained; free-text plus a
  readable provider error is honest with BYOAK.
- **User-supplied local URLs.** SSRF surface; the operator names endpoints.
- **Automatic fallback on error or quota.** Hides the user's failure behind the
  operator's bill; fallback only when the key is absent.
- **In-game consent popup.** Breaks the game flow; consent is a persistent settings
  choice.
- **Hot YAML reload, or admin policy in the database.** Touches every consumer of the
  config loader, or adds an API plus admin UI; edit and restart is enough for now.
- **Two ADRs (configuration vs embeddings).** Logically one contract; one document in two
  parts.
- **Gemini thought signatures here.** A provider bug (point 4, #56), not configuration.

## 7. Consequences

**Positive**

- The documented BYOAK flow becomes real: the personal key is used, and on a shared
  instance cost attribution stops lying.
- One model per user retires the #73/#74 defect class by construction.
- Embeddings stop being a hidden OpenAI/384 pocket; any allowed provider or local model
  works, with an index lifecycle that cannot silently mix vector spaces.
- The configuration surface shrinks: no tiers, no temperatures, one output cap.

**Trade-offs**

- Per-call-type tuning is gone; a premium model also runs background chores (accepted:
  cheap models are strong, and the output cap bounds runaway cost).
- Free-text model names fail at the provider on a typo; errors are readable and, where
  possible, caught before the turn.
- `score_importance` and its tests are retired — ADR 0016 closes without implementation.
- Flexible vectors forgo an ANN index for now; the campaign-scoped sort must hold until
  measurements say otherwise.
- The index gains its first `Superseded by [NNNN]` status with this ADR.

## 8. Relationship to other ADRs

- **Supersedes ADR 0016** (importance scoring for model routing): with one model per user
  the score routes nothing; it survives only as turn metadata.
- **Builds on ADR 0000** (distribution): BYOAK per-turn cost on the user's key is the
  premise this contract finally implements.
- **Enables point 5** (embedding index rebuild) and **point 6** (minimal UI). No conflict
  with ADR 0004 (`dm.yaml` untouched) or ADR 0017 (dialogue contract untouched — NPC calls
  simply resolve through the owning user's configuration).
- Not gated by any other ADR.

## 9. Notes / sources

- Current-state claims verified in the 2026-10-17 session: `rg`/`read` on the named files,
  plus two router reproductions (provider-only override; background-tier resolution).
- OpenRouter embeddings endpoint —
  <https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings> — corrects
  #55's claim that OpenRouter has no embeddings API.
- Gemini thought signatures —
  <https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures> — a
  provider bug handled by #56 (point 4), out of scope here.
- Tracker: #65, #73, #74, #55.
