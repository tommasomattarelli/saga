# ADR 0021 — Unified structured generation and bounded recovery

Date: 2026-11-13

Status: **Proposed**, confirmed by the owner on 2026-11-13; G1-G5 closed at design level by owner answers on 2026-11-13. Implementation tests and endpoint enforcement remain unverified. This is not an accepted ADR. The owner separately authorized the implementation worktree, document promotion and offline implementation; commits, push, merge and live execution remain unauthorized.

## 1. Purpose and reading instructions

This ADR allows an implementation session to reconstruct the problem, the owner's decisions, the verified code map, operational restrictions, closed design gates, remaining implementation verifications, and acceptance criteria without depending on the design interview.

The estimate, absence of a commit ceiling, and three checkpoints in section 14 are owner-approved. The branch/worktree names and implementation start were separately approved on 2026-11-13. The technical gates in section 6 contain the settled design; implement and test them, rather than reopening them by default. If implementation evidence contradicts that design and forces a new architectural choice, stop and ask the owner. Do not silently change accepted behavior to accommodate an adapter.

The architectural record is ADR 0021, written in English, with an implementation plan. It is separate from [ADR 0020](0020-batched-memory-and-history-checkpoints.md), which remains Proposed. This ADR changes ADR 0020 §20.6's no-repair/single-generation rule: full validation may be followed by wrapper-only normalization and bounded LLM correction, but never field repair, slicing or content reconstruction. It also replaces §20.5's reopenable exhausted lifecycle with distinct claim cycles, monotonic per-result send budgets and definitive exhaustion. Existing publication atomicity and contextual validation remain authoritative. No implementation or status transition is authorized through this document alone.

Owner instruction (2026-11-13): this document was copied in full from the completed design plan into `docs/adr/0021-unified-structured-generation-and-recovery.md`, with only ADR/header and obsolete temporary/session wording normalization and the explicit ADR 0020 relationship above. `docs/adr/README.md` is updated in the same documentation change. This repository ADR is now the authoritative source; the original preparation file is a historical input, not a maintained competing version. Design decisions are closed; implementation evidence and actual endpoint enforcement remain unverified and must stay labeled accordingly. Proposed status was owner-confirmed; Accepted still requires owner confirmation.

The numbered work packages below are dependency groups, not approved sprints. The earlier use of five sprint labels was incorrect: no five-sprint or automatically thirty-commit program was agreed. The owner approved a realistic baseline of 16-17 logical units, a working estimate of 16-20 commits, and no hard commit ceiling. Do not mechanically allocate commits per work package or compress this scope into seven oversized commits. Eighteen readable units are better than seven enormous ones.

## 2. Repository base and isolation

- Source checkout: `/home/tommasomattarelli/Desktop/saga-memory-production`.
- Source branch: `adr/0020-s6-integrated-eval`.
- Source HEAD: `b72a3f24aa5355e896ae6f5da9eda29ded23d897` (`b72a3f2`).
- The source working tree was clean during the design mapping and at the implementation setup check on 2026-11-13.
- The owner explicitly selected S6 as the base, not main. Main lacks the refactored memory system; summary, facts, global production and durable execution differ materially.
- The owner authorized branch `feat/0021-structured-generation` and worktree `/home/tommasomattarelli/Desktop/saga-structured-generation`, created from the exact source base on 2026-11-13.
- Do not move or modify the S6 branch, long-lived ADR integration branch, or main as a side effect of setup.
- No push, integration merge, main merge, or automatic replay is authorized.
- A main-versus-S6 mapping agent was accidentally interrupted. The owner subsequently decided the comparison was unnecessary; do not restart that task unless asked.

Read the target checkout's `AGENTS.md`, `docs/adr/README.md`, relevant skills, and evaluation guide before work. Read-only mapping found no nested `AGENTS.md` in that checkout; recheck if the base changes.

## 3. Incident and preserved evidence

Historical evidence directory:

`/home/tommasomattarelli/Desktop/saga/scratch/adr-0020-memory-production/s6-integrated-ready-20261112-subtraction/`

Required evidence:

- `HANDOFF.md`
- `VALIDATION.md`
- `reviews/PIPELINE_FINDINGS_LUNA.md`
- `reviews/QUALITY_FINDINGS_LUNA.md` — use the corrected version
- `critical-validation-verification.json`
- `mechanical-verification.json`
- `report-live.md`

Verified incident:

- The authorized integrated run received four completed generation responses from OpenRouter.
- Sixteen turns were persisted.
- Batch 1 published one summary and two facts.
- Batch 2 produced a valid summary candidate and an invalid facts candidate; neither member of that batch was published.
- Output 4 was syntactically valid JSON but violated `FactsPayload` with 31 schema errors. Its `facts` array contained heterogeneous values and the root also contained an extra `content` field.
- This is not evidence of a transport, authentication or quota failure, nor proof of why the model emitted the wrong shape.
- The corrected quality review does not establish a hallucination from the readable fragments.
- No global, unified sidecar or embedding generation was reached. Two embedding sources were pending, but no embedding request was made.
- No job retry or second run was executed.
- The partial diagnostic archive is not the runner's completion archive or a longitudinal quality acceptance.

Safety:

- Original `saga` database is preserved at revision 009.
- Local copy `saga_adr0020_s6_20261112` was migrated to revision 014 for the historical run and contains a `retry_wait` job.
- PostgreSQL was stopped and data preserved. Do not start workers or application lifespan against these databases.
- Do not edit historical manifests, authorization records, evidence, hashes, or reports.
- The old per-run authorization was consumed. Documentary web access is not authorization for inference, capability probes, provider catalogs, or another evaluation run.
- Any future live work requires a new, explicit, narrowly scoped authorization. Do not infer approval from this ADR.

The historical full check passed on `907f012`; `b72a3f2` has the identical checked tree. No full check was rerun in this design session. Do not claim freshly verified green status from the historical result.

## 4. Owner decisions — authoritative design inputs

### D1. Scope and shared execution boundary

Include all application LLM generations: memory, NPC, DM prose, and tool-enabled DM responses. Use a common execution pipeline with a Pydantic-based contract specific to the callsite.

Include pure narrative prose rather than leaving it as an unvalidated exception. Retain native tool calling. A common pipeline does not require one universal JSON envelope or identical wire protocols across providers.

Streaming has adapter methods but no production caller was found. Streaming design is explicitly deferred. Do not add streaming implementation or claim future streaming is impossible because output is JSON.

Embeddings are not narrative generations and are not converted into JSON-schema LLM calls by this scope. Existing embedding safeguards must remain intact.

### D2. Adapter coverage

Cover OpenAI, Google, OpenRouter and local OpenAI-compatible endpoints. Do not implement OpenRouter only while implying global behavior.

### D3. Native schema and explicit degradation

Prefer provider-native strict structured output. OpenRouter requests use `provider.require_parameters: true` where applicable to the selected mode.

There are two separately authorized fallback permissions: JSON mode and prompt-only schema guidance. Both require explicit permission; neither is a generic response to arbitrary errors.

YAML provides conservative defaults, not a second mandatory operator authorization: native strict by default, JSON-mode fallback false and prompt-only fallback false. Two independent explicit personal-profile choices may override those fallback defaults. Do not implement operator AND user permission checks or disable the controls merely because a YAML default is false.

Tie the choices to the effective provider/model/endpoint fingerprint, including the resolved destination behind a local alias or instance default. A changed destination/model makes old opt-ins inactive and requires a new choice; a credential-only change does not reset format consent. Expose the two choices through the existing settings API/UI, with strict boolean validation and no credential disclosure. These are separate from server-key spending consents.

**D3 note (2026-11-13, implementation; owner decision).** Format consent binds a versioned HMAC of the full effective endpoint URL, not a plain unkeyed digest, so URL query and userinfo contents participate without being persisted or disclosed. This corrects the credential-only sentence in this decision: rotating an API key in its dedicated setting leaves the fingerprint unchanged, while rotating a credential embedded in the endpoint URL or the instance identity secret changes it. Provider, model, mode and the resolved SDK default are part of the same identity; implicit and explicit forms of the same SDK default resolve identically.

Fallback never bypasses local parsing, schema validation, contextual validation or bounded recovery. Never mask a malformed SAGA request or unsupported schema translation as a harmless capability fallback. No implicit model/provider/payment-policy switch.

### D4. Prompt and schema source

Pydantic contracts are the source of schema truth. In native mode, retain semantic instructions and coherent examples without duplicating the complete JSON Schema in the prompt.

Examples may themselves contain JSON; removing the duplicate full schema does not mean banning JSON examples.

Prompt-only fallback must obtain its schema from the same canonical source, not a handwritten parallel contract.

Do not promise lower billed input usage merely because the schema moves out of prompt text. Provider handling, accounting and cache behavior vary.

### D5. Recovery order and deterministic limits

1. Parse and validate.
2. If applicable, normalize only an explicitly whitelisted, unambiguous presentation wrapper.
3. Validate the normalized result completely.
4. If still invalid and eligible, request LLM correction within the remaining send budget.
5. Validate the entire corrected result before acceptance.

The initial approved normalization boundary is wrapper-only, such as one complete JSON document enclosed in a single unambiguous code fence. Specify the exact accepted grammar and ambiguity rejection in tests.

Do not perform general JSON repair, field invention, extra-field deletion, duplicate-key selection, coercion, positional reassembly, arbitrary completion, or content reconstruction. Do not salvage the historical facts payload by interpreting the heterogeneous array.

### D6. Corrective request and caching

Preserve the original initial context as an identical prefix. Append the complete failed output, then precise sanitized errors and deterministic structural guidance.

For further correction, retain cumulative history: base + output 1 + error 1 + output 2 + error 2.

The model returns a complete replacement result, not a patch. Do not silently truncate the source, failed output or error history to fit a context window. If preserving the required context becomes impossible, surface that limitation rather than inventing a reduced request.

Failed model output is untrusted data, not an instruction or an executable tool request. Adapter-specific message construction must not imply that unexecuted tools actually ran.

Guidance may describe mechanically known structural requirements, such as an expected object or required fields. It must not suggest invented sources, missing attribution, narrative facts, or content to discard.

Stable prefixes favor caching but do not guarantee hits. Mode changes, routing and provider implementation may affect caching.

For a tool-enabled response, narrative prose may be absent or empty when tool calls are present. Any present nonempty prose must satisfy its response contract. A response without tool calls must contain valid, nonempty prose. Absence in a tool-bearing step must not be replaced by fabricated filler or an implicit second generation. Merely wrapping arbitrary provider text in a local Pydantic object must not be advertised as provider-native structured output enforcement.

### D7. Frozen result identity

Freeze the non-secret execution identity: source, role, exact instructions, schema, model, endpoint, parameters and policy. Authorized fallback is a recorded derivation, not a mutation of the base.

Resolve credentials using current security controls; never persist secrets in request envelopes or evidence. Current authorization/endpoint safety checks still apply to frozen destinations.

Changed incompatible configuration requires a distinct production rather than silently reinterpreting an existing result. The public mechanism for creating a distinct production is not specified or authorized as a new feature here.

**D7 owner refinement (2026-11-15).** Freeze non-secret execution identity when a new job is created. If configuration or identity resolution fails, preserve that new-contract job as blocked without consuming a send. After configuration is repaired, only an explicit retry may bind identity once, before the job becomes executable; identity is immutable thereafter. Never attach identity to or backfill historical jobs. First-send identity freezing and automatic binding/retry of unresolved jobs are rejected.

### D8. Send budget

Maximum three application sends per typed logical result, initial send included. Transport retries, correction sends and fallback sends all consume the same budget.

- DM: one result is the complete response for one graph step, including prose and all tool calls, not one result per tool and not the entire turn.
- NPC: each actor result has its own counter.
- Memory batch: summary and facts have distinct counters, hence up to six sends for the two-result unit.
- Global or unified output: each typed output has one counter.

Candidate reuse consumes no new send. Durable wakeups and retries must not reset a result's counter. A manual retry cannot reopen an exhausted result's budget.

Reserve before I/O. Do not automatically refund a reservation whose outcome is uncertain. Distinguish scheduling/lease claims from provider sends.

Disable or explicitly account for SDK retries so the application cap is real. This cap cannot certify the number of attempts inside an external router's infrastructure.

Retain the existing four-claim-per-cycle scheduling guard separately from the result send budget. A claim that fails before send reservation does not consume a send. A committed reservation consumes a send even if the process fails before determining whether network I/O happened. A manual claim retry is allowed only when a required result still has sends available; it never resets send history. Do not replace four claims with three claims or eliminate the finite no-I/O crash guard.

The value is configurable in YAML. Do not add a new cumulative token or currency budget and do not scatter hardcoded limits across callers.

### D9. Error eligibility

- Selectively retry transient transport/server failures and rate limits within the send budget.
- Correct nonconforming outputs within the same budget.
- Apply explicit fallback only for a recognized incompatibility.
- Stop for SAGA bugs, authentication failures, refusal and truncation.
- Do not retry every 4xx or classify every 400 as unsupported functionality.
- Record cancellation and uncertain outcomes separately from known invalid responses. There may be no raw output to correct.

Define an exact adapter error classification table before implementation; do not replace this decision with brittle checks against arbitrary provider prose.

### D10. Tool preflight and effects

Validate the whole response's static tool properties before any effects: tool existence, permission/availability in the selected tool set, and argument schemas.

Then execute in the existing order with state-dependent domain checks against the updated state. Do not require every tool to be executable against the initial state; a preceding move may make a later NPC interaction valid.

Do not simulate the entire world execution or add transactional rollback machinery as an unrequested prerequisite.

Corrective recovery ends before admitting the response to the graph/tool executor. It does not create new DM graph steps. Existing graph/coordinator hard limits remain separate.

A stateful domain rejection after previous effects is not a format error and must not cause replay of already-applied or uncertain tool effects.

### D11. NPC rigor

Wrong types, disallowed axes and dialogue beyond declared output limits become explicit contract failures eligible for bounded correction, not silent casts, drops or clipping.

Keep gameplay bounds on applied effects separate. Do not change world-defined psychology semantics or gameplay clamping merely as output cleanup. Explicitly classify each current transformation before changing it.

### D12. Memory candidates and publication

Preserve already-valid candidates for reusable results instead of regenerating both specialists after one failure. Reuse requires the same frozen request/contract identity, sources and policy.

Candidates remain non-public until the complete atomic unit validates. Revalidate reused candidates before publication. Preserve existing atomic document, source, queue and cursor publication.

### D13. Durability, privacy and retention

Persist recovery material for durable jobs. Do not introduce global raw-response persistence for every interactive generation without a separate decision.

Remove raw prompts and outputs from ordinary runtime logs, including equivalent generation/tool payload sinks discovered during implementation. Keep safe metadata, hashes and sanitized diagnostics.

Raw/candidate retention defaults to one day after a definitively terminal state, configurable in YAML. Still-recoverable blocked jobs keep required candidates. Add an explicit `manual_retry_required` state when the claim cycle is exhausted but a required result still has send budget. This state and recoverable `blocked` do not start cleanup. `exhausted` is definitive, with a structured terminal reason; a manual retry cannot reopen it. `succeeded` becomes terminal only after atomic publication commits.

**W4 note (2026-11-15, implementation; autonomous detail).** Migration 018 records `required_result_send_budget_exhausted` as an immutable terminal code while retaining `last_error` as display text; legacy exhausted rows remain unmarked because their cause is unknown.

Persist `terminal_at` once at the definitive transition and start the one-day window from that timestamp, not from `updated_at`, the last send, or a worker wake. Cleanup removes raw/candidate/corrective-history payloads while keeping send reservations, hashes, safe reasons and provenance so cleanup cannot reopen the budget.

Delete only expired raw/candidate material, not original sources, published memory, provenance or historical evidence. Ordinary campaign export does not gain raw outputs or executable request envelopes.

Historical evaluation evidence is untouched. Newly authorized eval evidence is an explicit operator artifact, not an ordinary runtime log; do not silently apply runtime cleanup to it.

### D14. Output limit

Retain `generation.max_output_tokens = 60000` as the common configured ceiling for every generation send, including initial calls, tools, correction and fallback.

Apply it at the shared boundary rather than relying on method defaults or callsite copies. Do not add per-contract limits or a cumulative token budget without a new decision.

If a lower model limit is already known from a reliable, traceable source, use the minimum of that limit and the configured global ceiling. This is not a new per-contract cap or permission to introduce hardcoded model-limit tables. If the lower limit is unknown, request the configured ceiling and handle a rejection explicitly. Do not add automatic catalog queries or live probes to discover the limit. Include the effective requested limit and its relevant identity inputs in the frozen result.

Map the ceiling to the appropriate documented adapter field. OpenAI Chat Completions documents `max_completion_tokens` as covering visible output and reasoning; compatible/local routes and Google's current API must retain their own documented field/semantics. Do not claim that all endpoints meter hidden reasoning identically or that a requested cap alone proves their enforcement.

Keep the existing memory claim deadline of 120 seconds and lease of 150 seconds, both configurable. The deadline covers all roles and sends in the claim, not 120 seconds for each correction or each role. It does not promise that all six possible batch sends fit into one claim. Do not multiply turn/client deadlines or add another reasoning-effort/token/cost control implicitly.

### D15. Cutover, ADR and S6 return

ADR 0021 is English, includes the implementation plan, and does not maintain a legacy executor. Incompatible historical jobs must fail clearly before provider I/O, without automatic migration, backfill or replay.

Preserving old rows/archives is not a promise to execute old contracts. A forward migration for new functionality on a disposable implementation database is distinct from migrating the preserved historical databases; the latter is not authorized.

S6 stays paused. After the independently authorized implementation and checks, any return requires an agreed integration step, a new manifest, implementation fingerprint, run ID, output directory and fresh per-run owner authorization. Never resume the stopped run automatically.

## 5. Verified code map

Line numbers refer to `b72a3f2`; recheck symbols if the base changes.

### 5.1 Providers and generation boundary

- `backend/app/ai/providers/base.py:15-38`: separate `generate`, `stream` and `generate_with_tools` interfaces; schema is not a first-class generation argument.
- `base.py:53-102`: `logged_generate`, used by memory and NPC; it logs full prompts/results. Wrapping only this function misses the DM tool path.
- `base.py:109-144`: provider selection; OpenRouter reuses LocalProvider.
- `backend/app/ai/providers/local.py:32-58` and `openai.py:30-55`: boolean JSON mode sends `json_object`, not a response schema.
- `local.py:82-110` and `openai.py:81-113`: native tools; malformed argument JSON is replaced with an empty dictionary, losing the failed response representation.
- `backend/app/ai/providers/google.py:167-194,215-238`: JSON MIME generation and separate tool declarations; no common schema execution pipeline.
- `backend/app/ai/generation_attempt.py:5-20`: single-attempt context is a boolean, not a shared counter.
- OpenAI/local disable SDK retries for `generate` under that context, not uniformly for tool mode. Google has its own retry wrapper.
- `backend/app/ai/providers/openai_compat.py:38-49`: existing checks for missing choices and truncated responses.
- Refusal handling and usage capture are not uniform across adapters; preserve diagnostics without broadening into an unrelated observability redesign.
- `backend/app/logging_setup.py:80-93`: full LLM log rotates by size, not time.

### 5.2 DM and tools

- `backend/app/api/turns.py:79-105`: graph invocation and existing recursion bound.
- `backend/app/core/dm/dm_graph.py:27-65`: routes accepted DM response to tools.
- `backend/app/core/dm/dm_nodes.py:101-193`: requests native tools, accepts free prose/tool calls, creates AIMessage and increments step count.
- `backend/app/core/dm/loop_policy.py:7-25`: existing max-agent-step policy; recovery must not weaken or consume this as new graph steps.
- `backend/app/ai/tools/tools_base.py:49-53,88-142`: Pydantic tools and selective OpenAI-schema conversion; some constraints are not preserved.
- `tools_base.py:171-199`: tool argument validation boundary.
- `backend/app/core/dm/dm_tools_executor.py:26-39,53-67,83-232`: current ordering and sequential validate/execute behavior; dice first, normal tools next, NPC invocation last.
- Current executor can apply an earlier tool before discovering an invalid later call; a whole-response preflight is required.
- `backend/app/core/dm/npc_prehook.py:53-120`: name/location/duplicate/limit checks and possible NPC creation; distinguish static checks from stateful effects.
- `backend/app/core/dm/npc_beat.py:38-46,86-157`: NPC invocation orchestration and effect application.

### 5.3 NPC

- `backend/app/ai/npc_director.py:41-91`: JSON-mode request, fence handling and general `json_repair` before validation.
- `backend/app/ai/npc_outcomes.py:41-75`: strict actor model but permissive transformations, including nonnumeric-value dropping and float-to-int conversion.
- `backend/app/memory/updater.py:30-68`: axis filtering/effect bounds; classify gameplay behavior separately from output repair.
- `backend/app/ai/prompts/templates/npc.yaml`: semantic instructions/examples to align with the canonical response contract.

### 5.4 Memory producers and jobs

- `backend/app/memory/producers.py:18-37`: generation and complete output validation.
- `backend/app/memory/producer_prompts.py:23-31,44-80,101-138`: four response contracts, duplicate-key/nonfinite rejection, policy-enriched schema currently placed in the prompt, frozen instruction hashes.
- `backend/app/memory/producer_contracts.py:31-95,148-178`: generated facts, attribution/source validation and policy constraints.
- `backend/app/memory/document_contracts.py:11-43`: closed, strict document models and text checks.
- `backend/app/memory/job_requests.py:42-145,148-205`: frozen prompt envelopes, roles, source IDs/hashes and restoration checks.
- `backend/app/memory/job_claims.py:47-117,147-175,200-209`: durable claims, failure states, four-attempt policy per cycle and manual retry-cycle reset.
- `backend/app/memory/job_execution.py:24-34,94-130`: request restoration, generation sequence, raw held only in memory and publication.
- `backend/app/models/memory_generation.py:84-97`: metadata columns without durable raw payload.
- `backend/app/memory/job_publication.py:38-139`: atomic validation and publication; preserve this authority.
- `backend/app/memory/job_scheduler.py:79-90`: existing scope lookup does not fully establish candidate-compatible request identity.
- `backend/app/services/campaign_export.py:76-153`: safe explicit export fields, not raw outputs.

### 5.5 Evaluation

- `backend/eval/README.md`: mandatory operational safeguards.
- `backend/eval/integrated_memory/job_driver.py:26-48,78-88,135-142`: evidence recording and stop-before-job-retry behavior.
- `backend/eval/integrated_memory/provider_guard.py`: guarded physical attempts and SDK single-attempt instrumentation.
- `backend/eval/integrated_memory/plan.py`, `ledger.py`, `runner.py`: frozen scope, request budgets and nonautomatic resume behavior.
- Historical 42 generation requests describe successful first-attempt baseline plus sidecar, not a budget automatically authorizing recovery. Do not silently reuse that cap or select a new live cap without owner review.

## 6. Technical gates — design closed on 2026-11-13

Both Luna investigations completed before the owner answered the remaining questions. All ten resulting choices were explicitly confirmed. The entries below are implementation requirements, not unresolved policy questions. Offline tests have not yet been executed; live enforcement has not been certified. Neither missing test execution nor an unknown endpoint guarantee is permission to reinterpret the chosen contract.

### G1. Mixed structured prose and native tools

Closed decisions:

- Retain native tool calling and a typed prose contract in the shared pipeline.
- Tool-bearing responses may omit prose; any nonempty prose present must validate. A response without tool calls requires valid nonempty prose.
- Do not add a second generation, synthetic universal tool envelope or prose exception implicitly.
- If combined native enforcement is unavailable, use only an already authorized weaker mode; otherwise fail explicitly. Do not present local string validation as provider-native strict enforcement.
- Official documentation and offline body/contract tests are sufficient for design/adapter qualification. No mandatory live probe is introduced and unprobed endpoints are not automatically deactivated merely because they lack a live test.

Verified evidence and limits:

- OpenAI Chat Completions permits absent/null text when tool calls are present. The API represents text and tool calls, but representation alone does not prove strict text-plus-tools enforcement on every endpoint.
- The current Google adapter uses `generateContent`. Documentation illustrating a combined workflow through preview Interactions APIs does not establish equivalence for this implementation; do not migrate APIs as an unrequested shortcut.
- OpenRouter documents endpoint-dependent schema enforcement. Parameter support filtering is not proof of every schema keyword's enforcement.

Implementation checks: serialize actual mixed/tool-only/text-only bodies for each pinned SDK; validate missing/empty/present narrative cases and verify no extra model generation or hidden fallback. Record runtime incompatibilities truthfully. Endpoint metadata and live enforcement checks still require their own authorization; none are authorized here.

### G2. Schema fidelity and local constraints

Closed decisions:

- Keep canonical Pydantic contracts and all contextual validators authoritative.
- For dynamic maps or other structures that cannot directly satisfy a closed strict wire schema, use specific lossless typed wire DTOs where necessary; a list of typed key/value entries is an example, not a universal replacement for every object.
- Conversion is explicit contract encoding/decoding, not repair. Reject duplicate keys rather than selecting a winner; never invent/drop content or change types to make a response fit.
- Derive or otherwise mechanically connect wire contracts to their canonical source; do not create a handwritten second schema of truth. Validate the decoded canonical result before tool execution or publication.
- If a particular contract cannot be faithfully encoded for an adapter, do not silently strip constraints. Use only an explicitly permitted weaker mode, or fail. An implementation bug is not an incompatibility escape hatch.
- Freeze/version the contract and encoding identity needed to prevent reuse after an incompatible translator/schema/validator change.

Implementation checks: inventory actual memory policy limits/enums, NPC axes/maps, tool maps, nullable/default fields and contextual references; compare accepted representations, not merely schema-string equality. Add round-trip and invalid/duplicate-entry tests for wire DTOs. Pydantic strictness, native strictness, router filtering and domain validation retain distinct responsibilities.

### G3. Job claims versus result sends

Closed decisions:

- Three monotonic application sends per typed result; separate summary/facts counters and no reset across claims/manual retries.
- Retain four claims per cycle as an independent scheduling/crash guard. Preserve the current policy key if renaming would introduce unnecessary stored-policy/archive churn; document that it counts claims, not sends.
- Reconstruction and credential/security resolution precede send reservation; failures there do not spend a send.
- A send reservation is a committed record before provider I/O. Count all reservations, including uncertain outcomes. Never automatically refund an uncertain reservation.
- A manual retry may reopen a claim cycle only if a required result still has send budget; it does not create a new result or reset the existing one. No public new-production endpoint is added.
- Keep claim deadline 120 seconds and lease 150 seconds, not multiplied per role or correction. An expired in-flight reservation is uncertain, remains counted, and valid persisted candidates remain reusable on a subsequent eligible claim.

Implementation checks: lock/fence claim ownership during reservation, enforce per-role uniqueness and budget checks transactionally, and preserve publication idempotence after crashes. Scheduling counters remain distinct from graph steps and provider-send counters.

### G4. Storage, states and settings controls

Closed storage decisions:

- Extend `memory_jobs` and `memory_generations`; do not introduce a separate result table.
- Store a typed immutable non-secret identity snapshot, hash and supported contract version on the job, covering frozen source/instructions plus role-specific schema/encoding identity, provider/model/destination, effective parameters and policy. The existing source/instruction manifest remains the canonical source for its existing contents; do not unnecessarily duplicate it.
- Treat each generation row as one send reservation with role, send number, send kind, outcome, raw response and safe diagnostics. Use uniqueness on `(job_id, role, send_number)` and a positive send-number constraint; enforce the configurable maximum transactionally, not with a hardcoded SQL check equal to three.
- Derive result identity from the exact job identity and role, and derive send usage from reservations that are never deleted by payload cleanup.
- Serialize reservations under existing job locking/fencing; commit before I/O. Persist received response/history before any further corrective I/O. No DB session spans an LLM call.
- Reuse a compatible valid raw candidate rather than introducing a second copy of the same candidate JSON. Preserve deterministic normalization provenance and reapply the approved validation path when needed; retention does not remove hashes or send history.
- Update current immutable-generation SQL guards narrowly: identity/provenance remain immutable; allow only the specified outcome/payload transitions and payload cleanup. Do not turn provenance rows into arbitrary mutable JSON.

Closed state/retention decisions:

- `queued`, `running`, `retry_wait`: nonterminal.
- Recoverable `blocked`: requires explicit intervention and keeps necessary candidates; no terminal cleanup clock.
- New `manual_retry_required`: the claim cycle is exhausted while a required result still has sends available; explicit retry opens claims only and keeps candidates.
- `exhausted`: definitive inability to produce a required valid result within the agreed policy/budget; store a stable structured terminal reason and no manual budget reset.
- `succeeded`: terminal after atomic publication commit. Detached activation is not a substitute for this success/failure lifecycle.
- Persist `terminal_at` once for definitive termination. After one configured day, clear only raw/candidate/corrective payloads; retain safe metadata, hashes, reservations, sources and published artifacts. Do not use `updated_at` as the cleanup clock.
- Missing/unsupported historical contract identity is non-executable before provider I/O, without backfilling a valid identity or invoking a legacy executor. Surface a clear reason; a worker must not turn repeated incompatible-contract encounters into repeated provider calls.

Closed settings decisions:

- YAML supplies native-strict and two false fallback defaults, not an operator veto requiring a second authorization.
- Add two independent strict-boolean personal overrides for JSON-mode fallback and prompt-only schema fallback, separate from server-key spending consent.
- Tie opt-ins to a non-secret effective provider/model/endpoint fingerprint. A destination change, including a changed URL behind an alias or instance default, invalidates old format opt-ins; credential changes alone do not.
- Expose the choices in the existing settings API and reusable profile editor. Do not disable them simply because YAML defaults are false. Preserve current credential and endpoint security validation.
- Frozen jobs are not silently rewritten when settings change. Reject incompatible identity changes, while allowing current credential resolution under the existing security checks.

**G4 note (2026-11-13, implementation; owner decision).** The credential-only sentence is corrected by the D3 note: URL-embedded credential rotation changes the keyed effective-endpoint identity and invalidates consent; rotating a dedicated API-key setting does not.

**G4 owner refinement (2026-11-15).** New jobs carry an immutable nullable current-contract marker distinct from identity-snapshot versioning. Unmarked historical jobs remain unbound; only a marked blocked job may bind once during explicit retry before becoming executable. Owner delegated implementation blocker decisions through W5, requiring autonomous decisions to be recorded here and in the changelog, then stopping before merge. Avoid live calls unless necessary, and use exclusively free models if needed; no paid-model calls are authorized. W5 delegates checks and subtraction reviews to independent agents; the orchestrator verifies critical points and fixes belong in the owning commit.

**G4 note (2026-11-15, implementation).** Migration 016 binds each send digest to its frozen role digest, but corrections and fallbacks have distinct derived request identities; migration 017 preserves the base snapshot and verifies each derived snapshot against its exact digest. Existing outcome columns also cannot reconstruct `RawGenerationReceipt`, so durable storage needs a versioned lossless receipt envelope separate from the candidate column.

**G4 note (2026-11-15, implementation; autonomous details).** Migration 017 uses nullable marker version 1, separate from snapshot version, so old rows remain identifiable without backfill. A schema-specific SQL serializer validates typed fields and emits sorted, compact UTF-8 JSON matching the shared `MemoryGenerationRequestIdentitySnapshot.snapshot_json`; both SQL and ORM compare the explicit format column. The base job digest retains Python's existing `ensure_ascii=True` contract: SQL validates the complete typed Pydantic shape, then emits sorted compact JSON with ASCII escapes, including surrogate pairs for astral code points. Job binding verifies the versioned identity digest before the blocked-to-queued transition. Safe outcome reasons cover classifier and executor codes, remain separate from diagnostics, and survive payload clearing. Receipt JSON uses strict versioned fields and base64 for opaque signatures; its candidate is referenced from the existing hash-bound column to avoid a second mutable copy. Downgrade refuses to discard markers or receipt evidence, including reachable receipt-only rows from unmarked pre-contract jobs. These autonomous guard and encoding choices preserve owner policy and add no runtime retry behavior.

Implementation surface: `backend/app/models/user.py`, `backend/app/schemas/settings.py`, `backend/app/api/settings.py`, existing frontend `settings-ai-profiles.tsx`/`settings-ai-panel.tsx`, relevant profile types/API tests, and English/Italian translations. Locate exact current frontend paths before editing.

A forward migration after revision 014 is required for the chosen added persistence/profile fields and state/constraint changes. Test fresh upgrade and upgrade with preexisting rows on disposable PostgreSQL. Existing rows need not be assigned a usable new contract identity: missing identity is explicitly non-executable. Do not start or migrate either preserved historical database.

### G5. Output limit and reasoning semantics

Closed decisions:

- Use 60,000 as a configurable global ceiling for every generative send through the common boundary.
- If a lower model output limit is already reliably known, send `min(global_ceiling, known_model_limit)` and record the effective value/source as appropriate for frozen identity. No hardcoded catalog substitute, new provider-discovery request, speculative limit guessing or new per-contract knob.
- If the lower limit is unknown, request the global ceiling; treat an actual rejection explicitly rather than silently removing the cap or retrying guessed lower limits.
- Map to the appropriate documented SDK field for the adapter. OpenAI's `max_completion_tokens` covers visible and reasoning output in its documented API; do not assume every compatible endpoint accepts that field. Google and compatible routes use their supported field/semantics.
- Documentation and offline request serialization/contract tests are sufficient for design qualification; do not require an authorized live probe merely to enable every profile. Actual enforcement remains explicitly unverified where it has not been observed.
- No new cumulative token/currency budget or implicit reasoning-effort control. The owner retained the 120/150-second memory claim/lease limits independently of output-token limits.

Implementation checks: verify pinned SDK field support, each wire body including tool/corrective/fallback calls, known-lower-limit versus unknown-limit behavior, and truncation classification. Document output/reasoning differences without promising identical accounting or infinite-reasoning prevention on an unverified external endpoint.

## 7. Proposed implementation dependency groups

These are work packages, not fixed sprints or commit counts. Design readiness, Proposed status and offline implementation were separately confirmed by the owner on 2026-11-13; use the ADR implementation skill under the topology and commit-ceiling exceptions recorded here.

### W0 — Record the closed design as ADR

- Carry the already closed G1-G5 design and its evidentiary limits into the ADR; do not delegate those policy choices to the implementer or require live probes as an unstated prerequisite.
- Encode the already settled response, failure, state, budget, fallback and wrapper-only rules into concrete types and tests. Choosing field names, implementing error adapters and specifying the exact unambiguous-fence grammar are implementation details under those closed rules, not unclosed architectural gates. Escalate only if evidence forces a materially different rule.
- The branch/worktree names and reviewable scope were owner-confirmed; source remains b72a3f2 unless explicitly changed.
- This English document is promoted directly into ADR 0021 by copying it, with only the minimal ADR/header/session-wording normalization described in section 1; do not rewrite it or commission a second ADR. Update its index row in the same documentation change. Proposed status was owner-confirmed on 2026-11-13.
- Cross-reference the changed Proposed ADR 0020 behavior without rewriting historical evidence.

### W1 — Shared typed generation and adapter contracts

- Write failing contract/serialization tests before implementation.
- Introduce the minimal common request/result execution boundary, not an extensible framework with speculative features.
- Carry the response contract explicitly, while letting each adapter own its wire encoding.
- Preserve malformed output for diagnosis; normalize provider receipts without losing refusal, finish or raw tool-argument information.
- Enforce the common configured output ceiling, reliably known lower model limits and application-owned send accounting.
- Disable hidden SDK retries and expose recognized failures consistently.
- Add strict schemas and explicit fallback behavior for all supported adapters, using the same canonical source.
- Add the agreed profile/config contract, two user overrides and destination fingerprint validation; YAML defaults are not a second operator veto.

### W2 — Bounded validation and corrective recovery

- Implement full validation, exact wrapper-only normalization and revalidation.
- Add sanitized error descriptors and deterministic structural guidance.
- Freeze the base and build cumulative corrective requests as explicit derivations.
- Preserve prefix order and input identity; do not fabricate successful tool results during correction.
- Enforce the three-send counter across transport, fallback and corrections.
- Stop on refusal, truncation, internal bugs, unauthorized configuration and unrepresentable full context.
- Remove raw runtime logging without replacing it with another uncontrolled raw sink.

### W3 — Consumer integration and tool preflight

- Adapt DM mixed responses, including narrative, without abandoning native tools.
- Validate complete responses before graph admission and increment the graph step only for the accepted step result, according to the finalized counter semantics.
- Add pure whole-response tool preflight, preserving execution ordering and sequential domain checks.
- Audit NPC transformations against the chosen rigorous output contract; remove permissive repair/casts/drops/clipping from the output acceptance boundary while retaining intentional gameplay effect rules.
- Adapt the four memory producer contracts to the shared schema source and full local validation.
- Remove only helpers/dependencies made orphaned by these changes; do not perform unrelated dead-code cleanup.

### W4 — Durable memory recovery, privacy and cutover

- Write failing real-PostgreSQL integration/migration tests on a dedicated disposable database.
- Extend existing job/generation storage for durable send/candidate/diagnostic data; do not add a result table. Preserve the finite claim guard separately and add the agreed manual-retry-required lifecycle.
- Reserve sends before I/O; persist received recovery material before subsequent corrective I/O; never hold DB sessions across LLM calls.
- Reuse exact-identity valid candidates, revalidate them, and publish complete units atomically.
- Cover lease expiration, cancellation, crash windows and manual retry without budget resets.
- Block incompatible old contracts before provider calls, with no legacy executor or historical backfill.
- Apply configurable one-day cleanup from immutable definitive `terminal_at`, retaining reservations/provenance and all payloads still needed by recoverable jobs.
- Preserve export safety and provenance; no automatic raw/executable-envelope export.

### W5 — Offline evaluation integration and verification

- Keep evaluation instrumentation outside runtime behavior; ensure each application send is observable and reserved before provider I/O.
- Update offline preparation, fingerprints and reports for the new contracts and selected recovery behavior.
- Do not weaken the harness to accept invalid production outputs merely to score prose.
- Prepare only new artifacts if requested; do not rewrite or resume the historical run directory.
- Reconcile generation counts and per-result limits with a separately selected run-wide cap. No cap selection authorizes execution.
- Run full backend and frontend gates, migration/integration tests and a final independent review before declaring implementation complete.
- Return to S6 only through an owner-approved integration and a newly authorized run.

## 8. Required acceptance and regression cases

### Request/schema contracts

- Every runtime generative path reaches the common boundary, including DM native-tool mode and all corrections/fallbacks.
- Every send applies the configured output ceiling, reduced only for a reliably known lower model limit; no caller's old 2,000-token method default silently wins. Unknown model limits do not trigger catalog discovery or guessing.
- Strict/native, permitted JSON mode and permitted prompt-only modes generate the intended body for each adapter.
- OpenRouter preferences are emitted only where applicable; unsupported parameters are not falsely claimed as enforced.
- Pydantic/provider schema differences are identified, not hidden by keyword filtering.
- Dynamic source/policy restrictions remain effective locally.
- Native-mode prompts omit the duplicate complete schema; fallback schema and examples remain consistent with the same contract.
- Tool-bearing responses may omit prose; present prose validates and responses without tool calls require valid nonempty prose. No implicit extra model call and no local wrapper falsely labeled native strict.
- Dynamic-map wire DTOs round-trip without loss, reject duplicate entries, preserve canonical validation and do not become a second independent schema source.
- Both personal fallback controls override false YAML defaults independently, reset/inactivate on effective destination changes, and remain separate from credential/spending consents.

### Validation and recovery

- Missing/extra fields, wrong nested types, invalid enums, duplicate keys, nonfinite constants and contextual-reference failures are rejected appropriately.
- A single permitted wrapper can be normalized; ambiguous wrappers, multiple documents, partial JSON and mixed prose/documents are not salvaged arbitrarily.
- No field dropping, coercion, invented attribution/source or positional facts reconstruction.
- Original raw and derivation identity remain available where required.
- Corrections preserve the initial prefix and cumulative order, include the full failed result and sanitized error guidance, and return complete replacements.
- Diagnostics contain no Python exception/class disclosures, stack traces, internal filesystem paths, credentials or raw Pydantic context objects. JSON field paths are permitted diagnostic data.
- Raw failed output is data only; it cannot cause tool execution.
- Refusal, truncation, authentication/internal failures and context overflow do not become generic corrective retries.

### Budget and idempotence

- Three sends maximum per typed result across all eligible paths.
- Invalid strict response followed by correction; unsupported strict mode followed by permitted fallback; transport retry followed by correction all share one counter.
- No hidden SDK multiplication; no durable wake/manual retry reset.
- Memory summary/facts counters are separate; reused valid candidates do not spend another send.
- A reservation with uncertain outcome is not automatically refunded.
- Application send accounting does not make false claims about external-router internal attempts.
- Existing graph step/recursion bounds remain enforced independently.
- Four claim attempts remain a separate finite scheduling guard. A no-reservation failure does not consume a send; manual retry with remaining sends resets only the claim cycle.
- Memory claim deadline is shared 120 seconds and lease 150 seconds; corrections do not receive a fresh full deadline, and timeout after reservation remains counted/uncertain.

### Effects and domain behavior

- A malformed later tool prevents all effects of that response, including dice and NPC creation.
- Unknown/disallowed tools are caught by preflight according to the finalized contract.
- A preceding valid move can still enable a later NPC interaction through sequential domain checks.
- Domain rejections after earlier effects do not replay the accepted response or previously applied tools.
- NPC output failures are not silently converted, dropped or clipped; gameplay effect bounds remain intentional and independently tested.
- No invalid/corrective candidate reaches graph admission or publication.

### Durability and crash cases

- Crash after reservation before/during network: budget remains consumed, outcome distinguished as uncertain.
- Response received but not durably recorded: recovery does not invent the lost raw or refund the send silently.
- Valid candidate persisted before publication: new lease reuses only exact-compatible identity and revalidates.
- Crash after publication commit before acknowledgement: next wake does not duplicate artifacts or cursors.
- Changed prompt/schema/model/endpoint/policy cannot silently reuse an incompatible candidate.
- Incompatible historical contracts fail before network I/O; no legacy execution path appears accidentally.
- Terminal cleanup removes only eligible raw/candidates after one configured day; recoverable jobs and provenance remain intact.
- `manual_retry_required` retains candidates and permits reopening claims only with send budget left; definitive `exhausted` cannot be reopened by the retry endpoint. Cleanup uses `terminal_at`, not `updated_at` or activation state.
- Updated generation immutability guards allow only approved reservation/outcome/cleanup transitions; uniqueness and fencing prevent duplicate or stale-worker mutations.
- Exports contain safe metadata and published artifacts, not new raw payloads or replayable requests.
- Ordinary runtime logs do not retain raw prompts, model responses or equivalent complete tool payloads.

### Migration and evaluation

- Fresh database upgrade and upgrade from revision 014 preserve required existing rows without backfilling historical executable recovery data.
- Migration tests run against disposable PostgreSQL, not either preserved database.
- Evaluation failures remain distinguishable from successful HTTP transport and successful publication.
- Changed contracts/mode/recovery settings affect fresh preparation fingerprints and manifests appropriately.
- Old stopped evidence remains unchanged, and no authorization is inherited by a fresh run.

## 9. Existing tests to inspect and extend

Use current test organization and add focused tests where missing. Do not create a second handwritten schema in fixtures that disagrees with the real producer.

- Provider/generation: `tests/unit/ai/test_generation_contract.py`, `test_provider_error_payloads.py`, `test_content_policy.py`, `tests/unit/test_generation_attempt.py`, `test_local_provider_usage.py`, `test_provider_usage.py`, `test_google_thought_signatures.py`.
- DM/tool flow: `tests/unit/core/test_dm_nodes.py`, `test_dm_routing.py`, `test_tools_node.py`, `test_dm_loop_flow.py`, operation-recording and NPC-operation-recording suites.
- NPC: `test_npc_director.py`, `test_npc_outcomes.py`, `test_npc_prompt_contract.py`; some current tests explicitly pin permissive behavior and must change only with the corresponding contract change.
- Memory contracts/producers: `tests/unit/test_memory_producers.py`, `test_memory_producer_contracts.py`, `tests/integration/memory/test_memory_producers.py`.
- Durable integration: job execution, claims, publication, scheduler, storage, generation storage and reconciliation suites under `tests/integration/memory/`.
- Migration/export: memory history migration tests, `test_campaign_archive_memory.py` and other archive integrity tests.
- Evaluation: integrated memory preparation, guards, ledgers, stopped-run behavior and fingerprint tests; discover exact current files before editing.
- Settings: inspect backend/frontend profile schemas and existing settings tests before choosing new fields or controls.

Paths above include basename references from the mapping; locate exact current paths rather than inventing them.

## 10. Verification and handoff rules

- TDD first. Start only dedicated test infrastructure when authorized for implementation; never point an application worker at the preserved run copy.
- Run real DB integration tests for core job/publication/migration flows.
- Full backend gate includes lint, formatting, mypy and unit tests; full frontend gate includes lint/format/types, knip, build and coverage as required by the checkout's guide.
- Prefer the SAGA status/check tools where they target the correct worktree and do not violate database/runtime restrictions. Check tool behavior before invoking a command that could start services or write in a historical directory.
- Request a GPT-6 Luna max independent review at material design/implementation checkpoints, as requested by the owner. Include constraints explicitly in every agent task.
- Do not announce green status without current verification. Record failures and known skips accurately.
- Respect scoped Conventional Commits and docs-as-code. Do not commit, push or merge merely because a plan exists.
- Update this ADR/index/changelog under the document-promotion and implementation authorization; no accepted ADR edits and no historical evidence rewriting.

## 11. Sources and evidentiary limits

Read-only mappings/reviews in this session used GPT-6 Luna with maximum effort. Findings are grounded in local source at b72a3f2, not provider experiments.

Official documentation consulted:

- OpenRouter structured outputs: https://openrouter.ai/docs/features/structured-outputs
- OpenRouter provider routing: https://openrouter.ai/docs/guides/routing/provider-selection.md#requiring-providers-to-support-all-parameters
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Chat Completions reference (content/tool-call and completion-token fields): https://platform.openai.com/docs/api-reference/chat/create
- Google GenerateContent reference: https://ai.google.dev/api/generate-content
- Google thinking/token-limit guidance: https://ai.google.dev/gemini-api/docs/thinking#token-limits
- Pydantic JSON Schema: https://docs.pydantic.dev/latest/concepts/json_schema/
- Claude Agent SDK structured output: https://code.claude.com/docs/en/agent-sdk/structured-outputs.md
- Codex noninteractive structured output: https://developers.openai.com/codex/noninteractive/
- OpenCode V2 tools/plugins/API documentation: https://opencode.ai/docs/tools/ ; https://opencode.ai/docs/build/plugins/server/ ; https://opencode.ai/docs/openapi.json

OpenRouter documents endpoint-dependent enforcement. `require_parameters` is not proof of full strict schema enforcement. OpenAI distinguishes completed non-refusal structured outputs from refusals, incomplete responses and rules not expressed by the schema. Harnesses may validate and reprompt; none should be treated as infallible evidence that a model never emits invalid data.

No catalog lookup or inference probe established current Nemotron/OpenRouter compatibility. No live run is authorized by documentary research or this handoff.

## 12. Design completion and remaining verification

The two technical-gate investigations completed, the owner answered all ten resulting questions, and this ADR incorporates those answers. No architecture/policy decision from G1-G5 is intentionally deferred to a fresh implementation session.

Remaining work is implementation evidence: actual SDK request tests, wire/canonical round-trip tests, database migration/state/race tests, settings UI/API tests and full checks. These are not authority to change the chosen design. External endpoint enforcement remains unverified without a separately authorized live invocation; documented/offline qualification is the agreed prerequisite, not mandatory live certification.

Formal Proposed status and delivery-branch names were owner-confirmed when promoting this document and starting implementation on 2026-11-13. Do not promote to Accepted without implementation and owner acceptance. Repository doc promotion, feature implementation, commits, live execution, push and merge remain distinct authorizations.

## 13. Alternatives explicitly not selected

These summarize choices not selected in the interview and the trade-offs discussed; they do not invent additional reasons on the owner's behalf.

- Main-first development: not selected; the owner chose the S6 base because main lacks the refactored memory contracts and job system.
- A fixed five-sprint/approximately thirty-commit program: never approved; the numbered list was a set of work packages. This is not a ban on exceeding the estimate if genuine logical units require it.
- Memory-only coverage, free-prose exception, and universal synthetic tool envelope: not selected; all generative paths, including narrative, use the shared pipeline while retaining native tools. Tool-bearing responses may omit prose; a response without tool calls requires valid nonempty prose.
- Mandatory live certification of every endpoint: not selected; documentary/offline qualification and explicit runtime failures preserve unverified enforcement honestly.
- Silent schema stripping, arbitrary JSON repair, dropping/coercing fields and content reconstruction: not selected; approved normalization is wrapper-only and wire DTO conversion is explicitly lossless.
- Mandatory prose in tool-bearing steps and implicit extra narration generations: not selected; tool-only responses are valid and tool-free responses need nonempty prose.
- One budget per whole turn/job or one per individual tool: not selected; the unit is one typed result, with separate memory roles.
- Claim-limit replacement by three sends, claim-guard removal and manual send-budget resets: not selected; four scheduling claims and three sends have distinct lifecycles.
- A separate durable result table: not selected; extend job and generation tables with serialized reservations and a retained provenance ledger.
- Reusing only existing job states with reason codes for manual claim exhaustion: not selected; add explicit `manual_retry_required` and distinguish definitive exhaustion.
- YAML AND profile fallback authorization: not selected; YAML supplies defaults that explicit profile choices can override.
- Format consents following the user to a different model/destination: not selected; destination fingerprint changes invalidate old opt-ins.
- Sending exactly 60,000 despite a reliably known smaller model limit: not selected; 60,000 is a ceiling, not a requirement to exceed a known model maximum.
- Automatically multiplying timeout by sends/roles or increasing claim/lease to 360/390 seconds: not selected; retain 120/150 seconds, configurable.
- Seven- or thirty-day raw retention, raw ordinary runtime logging and automatic raw export: not selected; one terminal day, safe ordinary logs and explicit safe exports.
- Legacy executors, historical-job backfill and resuming the stopped S6 run: not selected; preserve evidence/data without re-executing incompatible contracts.

## 14. Owner-approved effort estimate, checkpoints and setup

Owner-approved topology (2026-11-13): one feature branch and one additional worktree based on exact S6 HEAD b72a3f2, with no sprint subbranches: `feat/0021-structured-generation` and `/home/tommasomattarelli/Desktop/saga-structured-generation`.

Owner approval (2026-11-13): there is **no hard ceiling on the number of commits for this work**. Do not apply the repository's usual six/seven-commit branch heuristic as a reason to compress this ADR into mega-commits or split the architecture artificially. Prefer **eighteen readable logical units over seven enormous ones**.

The approved planning baseline is **16-17 logical units**, with an initial working estimate of **16-20 commits**. Twenty is not a maximum. Additional genuine units are acceptable if implementation evidence requires them; do not manufacture bookkeeping commits to match a number, and do not combine unrelated work to stay below one. More commits do not automatically imply more sprints or branches.

| Logical area | Baseline commits | Contents and checks |
| --- | ---: | --- |
| Shared contracts and faithful wire schemas | 2 | Canonical contracts, frozen identity, lossless DTO encoding/decoding, typed receipts and schema tests; copy/index the ADR in the first relevant architectural unit. |
| Provider adapters | 3 | OpenAI, OpenRouter/local and Google, each with its schema/tool/body/capability-error serialization tests and correct output-ceiling mapping. |
| Common recovery and send accounting | 2 | Wrapper-only normalization, precise safe diagnostics, cumulative corrective requests, shared send budget, selective retry/fallback and removal of hidden SDK retries; safe runtime logging. |
| Backend settings and frontend controls | 2 | YAML defaults, two personal choices, destination fingerprints, API validation, UI/translations and required profile migration tests. |
| DM integration and tool preflight | 2 | Typed narrative/native-tool responses, no premature graph admission, pure static preflight and preserved sequential domain behavior, with no-effects regressions. |
| Rigorous NPC integration | 1 | Actor response acceptance and contextual checks without permissive output coercion/drop/clipping, preserving gameplay effect bounds. |
| Durable memory | 3 | Existing-table schema/trigger migration, send and candidate lifecycle with atomic publication, then one-day retention/export safety and crash/lease/manual-retry coverage. |
| Offline eval and final document reconciliation | 1-2 | New execution accounting/preparation/fingerprint/report tests, ADR implementation evidence and final offline gates; no live execution. |
| **Estimated baseline** | **16-17** | Tests are part of the owning logical change, not separate filler commits. |

Follow-up corrections amend their owning logical commit when appropriate under the repository convention; genuinely new logical work earns its own commit. Keep scoped Conventional Commits and changelog/docs aligned. Individual commits may depend on earlier ones, but the final branch must be coherent and verified before any separately authorized integration.

Three owner-approved substantive checkpoints:

1. **Core and adapters:** canonical/wire fidelity, correct provider bodies, preservation of failed output, no hidden retries and a verifiable bounded execution budget. Review before treating the shared foundation as ready for consumer adoption.
2. **Consumers:** DM and NPC integration, typed prose/native tools, and tests proving that no tool, die or NPC-creation effect occurs before the entire response's static preflight. Preserve state-dependent tool ordering and graph limits.
3. **Durability and completion:** real-PostgreSQL migration/integrity tests, crash/fencing/lease scenarios, candidate reuse, definitive/manual-retry states, retention/export safety and atomic publication; complete backend/frontend checks and final independent review.

These checkpoints are review/evidence gates, not three mandatory sprints or branches. Use independent GPT-6 Luna max reviews where they can materially affect correctness. Carry discovered findings into the owning logical changes and the ADR; do not conceal a new architectural fork as a review fix.

Approved initial effort estimate: approximately **five to ten focused engineering days equivalent**, including TDD, migrations/integration coverage, review and rework, and full local checks. This is a planning range for an experienced engineer familiar with the project, not a promise about AI wall-clock runtime or a measured throughput forecast. Do not infer duration from commit count alone. Main risks remain mixed tool/schema behavior across adapters, faithful DTOs and durable crash/fencing tests. Live evaluation, provider experiments, S6 integration, playtest, push and merge are excluded.

The estimate and checkpoints are not automatic setup or execution authorization. The owner separately confirmed Proposed status, branch/worktree names, document promotion and offline implementation on 2026-11-13, and the worktree was created from b72a3f2. Commits, live execution, push and merge remain unauthorized; none is authorized solely by updating this ADR.

## 15. Final Luna consistency review

The final read-only GPT-6 Luna max review found **no architectural blocker** in the consolidated decisions. It identified three document issues, corrected here:

1. Remove stale wording suggesting design gates are still open; distinguish closed design from unexecuted implementation tests and uncertified live enforcement.
2. Replace the misleading statement that every generation includes prose: narrative is in scope, but tool-bearing responses may omit it and tool-free responses require nonempty valid prose.
3. Clarify that implementing exact grammar/error/type details under the settled rules is not another unresolved owner design gate in W0.

The review's earlier endorsement of the six/seven-commit and three-to-six-day delivery proposal is superseded by the owner's subsequent explicit approval of the 16-17-unit baseline, 16-20-commit estimate without a ceiling, three checkpoints and five-to-ten-day equivalent effort range. Review approval is not current CI evidence or permission for provider execution.
