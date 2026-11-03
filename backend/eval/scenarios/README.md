# Scenarios — saturated context fixtures for the model smoke harness

`eval/model_smoke.py` runs on an **empty** context by default: `summary_context`,
`global_summary` and `recalled_memories` are all passed empty. That makes every probe
easier than real play, and it showed — `nvidia/nemotron-3-ultra` scored 5/5 on
`npc_speaks` here while skipping `invoke_npc` in four of five real turns (see #52).

These fixtures exist to measure the gap.

## The one rule: probes are orthogonal to scenarios

A scenario file carries **world and context state only — never checks**. The checks live in
`eval/probes.py` and never move.

What the scenario *does* supply is the **stimulus**: the line the player types, and the NPC
result injected for probes that test what happens after one. It has to, because you cannot
ask a model to pick up a knife at the foot of a menhir in a scene that has no menhir. The
`probes:` block in `meta.yaml` is authored with the transcript, in the terms of the scene it
ends in. So: **the check is universal, the prose is local.**

That split is not style. The measurement we want is the **delta** between an empty and a
saturated context for the *same* obligation. If a check lived in a scenario file you would
duplicate 25 turns of context per obligation, and the delta could not be computed at all.

```
model_smoke.py --model X --scenario empty --scenario gold    # Δ column, last vs first
model_smoke.py --model X --scenario gold --scenario bloat --runs 5
model_smoke.py --model X --scenario gold --dry-run           # assemble prompts, call nothing
```

The Δ column is the deliverable. Absolute scores are not. Failure reasons are reported per
scenario rather than pooled, so you can see whether saturation introduced a failure mode the
empty context never produced.

`--dry-run` builds every prompt and prints its size without touching a provider. Use it
after any change to a transcript or to the prompt itself — it is the only validation
available when the daily quota is gone.

## Pipeline

```
transcripts/gold/                 authored play, 25 turns — costs no API
        │
        │  scenario_build.py
        │    1. instantiate the campaign from the world
        │    2. replay each turn's `updates` through apply_typed_updates()  ← real handlers, no API
        │       (quest rows use the production apply_quest_update transition)
        │    3. run the real summarizer / fact extractor / global summary   ← costs quota, once
        ▼
built/gold.yaml                   committed derived artefact
        │
        │  model_smoke.py --scenario gold
        ▼
    measurement
```

Two properties this buys, both deliberate:

- **World state is derived, never hand-written.** Replaying through the real handlers means
  every state in a fixture is one the engine can actually produce. A hand-authored blob
  eventually encodes an impossible combination and you end up measuring a fiction.
- **Context is derived, never hand-written.** The summaries a budget model produces over 25
  turns are repetitive and lightly contradictory. Prose written to be clean would make the
  fixture easier than production — the exact mistake the empty scenario already makes.

`built/` is committed because regenerating costs quota. Regenerate when a schema rung moves.

## Same format, two producers

`capture_scenario.py --campaign <uuid>` emits the **same** format from a real campaign in the
database: the world overlay, the active-window history and the batch summaries are captured,
not replayed. The harness cannot tell the difference. That is why the format was fixed before
either producer was written.

A captured state is only as faithful as the moment it was taken. A fixture that has to move the
player — to put a living NPC in the scene, or to sit at the turn where the failure happened —
is marked `reconstructed: true`, and the report prints it. Never silently.

Stimuli and per-probe recall are authored in `scenarios/stimuli/<name>.yaml` and merged by the
capture, because they belong to the scene, not to the database.

Anonymise before committing anything extracted from real play — this repo goes public.

## Variants are overlays, not copies

`transcripts/variants/<name>/overlay.yaml` declares only the turns it replaces or inserts on
top of `gold`. Full copies of 25 turns would drift apart silently, and a variant that has
drifted no longer isolates one variable.

Current variants, one hypothesis each — the two live explanations for why compliance drops
under load:

| variant | isolates |
|---|---|
| `gold` | baseline: coherent, no entropy |
| `bloat` | **length** — same events, much longer summaries |
| `contradiction` | **inconsistency** — the player asserts things that contradict canon |

Built scenarios are not all transcript variants. `debug-shrine` and `debug-thornhaven` are
**captured** from the 2026-10-25/26 debug campaign. `debug-thornhaven` moves the captured state
to Thornhaven so a living NPC is present (`reconstructed: true`); `debug-thornhaven-it` is an
**overlay** (`extends:`) that changes only the campaign language and the Italian stimuli, so
the two language directions share one captured state. A probe a scene cannot ask honestly —
`npc_speaks` where no living NPC is present — is reported `n/a`, never invented.

### Travel prevention versus conflict recovery

Use the same `travel_move` probe with two explicitly different cases:

- **`travel-coherent`**: an authored, reconstructed conversation that still places the
  player at the shrine before setting out for Thornhaven; it is not a captured state
  from before the original turn 11.
- **`travel-conflict`**: the original captured post-turn-14 mechanical state and unchanged
  history, where previous DM narration already claimed arrival but canonical position
  remains the shrine; this tests recovery from an existing conflict.

Both extend `debug-shrine`, preserving canonical state, summaries, recall, tools and the
same current player action. Only the coherent case replaces evaluation history; neither
rewrites the saved campaign or the original captured fixture. Both require `move_to`
because the canonical starting position is the shrine. Score and inspect them separately:
a coherent-case pass does not establish recovery, and recovery alone does not establish
normal coherent play. The quote/length/language heuristics still require manual review.

Offline assembly only, with no provider or catalog requests:

```text
uv run python eval/model_smoke.py --model nvidia/nemotron-3-ultra-550b-a55b:free \
  --model nvidia/nemotron-3.5-super-vl:free \
  --scenario travel-coherent --scenario travel-conflict --probe travel_move --dry-run
```

Future owner-authorized live runs must use a new checkpoint such as
`pr1-state-authority`, not append revised-prompt scores to the old `pr1-final` or
`pr1-context-diagnostics` comparison. The owner requested no commit until positive live
results: retain the truthful dirty-tree marker and exact request digest rather than
describing the new prompt as a clean run of the previous HEAD. Live validation is pending.

More were considered (`rename`, `death`, `abandoned`, `language`) and deliberately not built:
they are speculative until `bloat` and `contradiction` say something. Add one when a
measurement asks for it.

`language` is the interesting future one: it would be a *translation of the same 25 turns*,
so events and structure hold constant and only the language moves — which is the controlled
way to put a number on #51. Gold is authored in English on purpose: the world content is
English, so an English transcript keeps the baseline free of codeswitch noise, and English
measures the ceiling of a model's obligation-following.

## Transcript schema

```yaml
- n: 7                       # turn number
  player: "..."              # what the player typed
  dm: "..."                  # DM narration
  npc:                       # optional, an invoke_npc result
    name: Lyra
    dialogue: "..."
    action: "..."
  minutes: 15                # game time advanced
  updates:                   # replayed through apply_typed_updates() — real handlers
    - {key: npc_psychology, target: Lyra, changes: {trust: 4}}
    - {key: inventory_change, target: "Lantern", change: add}
  world_patch:               # direct overlay writes — see below
    player_position: thornhaven
```

`updates` uses the live handler keys: `npc_psychology`, `inventory_change`, `hp_change`,
`event_log_entry`. Quest rows are applied through the production quest tool contract instead:
`{key: quest_update, quest_id: who_am_i, change: active, description: "..."}` (a new id also
needs `name:`).

`world_patch` is an escape hatch for overlay state that ADR 0008/0009 own and that no typed
handler writes: `player_position`, `node_status`, NPC `location` / `lifecycle`, the clock.
It exists because those move through tool executors, not through `apply_typed_updates`.

<!-- TODO: world_patch should shrink to nothing once the tool executors can be replayed
     off recorded tool calls. Every direct write here is a place the fixture can encode a
     state the engine would not produce. -->

<!-- TODO(#55): `recalled_memories` is frozen per scenario (strategy "a"). In production
     recall is a pgvector similarity against the *current player action*, so the real set
     differs per probe. Strategy "b" — store the fact corpus and run real retrieval per
     probe — is impossible while embeddings are hardcoded to OpenAI and silently return
     None. The corpus IS stored in built/*.yaml under `fact_corpus` so the switch needs no
     format change. Until #55 is closed, do not read these recalls as faithful. -->

## Live runs: ledger, resume, budget

Every provider call is a request, and the free tier does not forgive an overshoot. Pass
`--user <owner-uuid> --checkpoint pr1 --ledger <daily-path> --budget N`. Credentials and
policy come from that user's existing configuration; the explicitly selected free model
is applied only to the evaluation, never saved to the profile. The copied provider client
has SDK retries disabled so a trial cannot hide extra requests.

The harness reserves each attempt before the call and retains full prompt/messages/tool
schemas, raw public response and scores. `--resume` skips only matching checkpoint/model/
request identities; failed and interrupted attempts still consume budget. `--out` writes
the selected checkpoint's results, not pooled before/after scores.

```text
uv run python eval/model_smoke.py --model nvidia/nemotron-3-ultra-550b-a55b:free \
  --scenario debug-shrine --probe travel_move --dry-run

uv run python eval/model_smoke.py --user OWNER_UUID --checkpoint pr1 \
  --model nvidia/nemotron-3-ultra-550b-a55b:free --scenario debug-shrine \
  --probe travel_move --runs 3 --ledger DAILY_LEDGER --budget REMAINING_AUTHORIZED_BUDGET \
  --out REPORT_JSON --resume
```

Supply the deployment's normal environment, including its encryption secret and database
URL, before resolving a personal profile. Never extract keys into scenarios or reports.
Reuse one daily ledger across checkpoints/models; `--budget` is its total authorized
request count, not a fresh allocation on every command. If earlier SDK retries were not
instrumented, establish actual remaining usage before another live run.

If the owner explicitly confirms a residual allocation instead, keep it in a separate
ledger with that exact cap and reference the earlier ledger; never treat it as a new
daily allocation. Small batches can resume the missing trials without repeating completed
requests, provided commit/checkpoint/request identity stays unchanged.

`--actor` adds the bounded real-actor path (`actor_probe.py`): one real `invoke_single_npc`
call per run against a present NPC, because the DM probes inject the actor result and so cannot
see the actor's own prompt (#51). Batched beats and multi-line results are ADR 0017's PR 2.

On exhaustion the run stops, writes what it has and exits 3 — it never sleeps until quota
renews.

DM smoke probes do not execute the requested tools; they measure foreground invocation
and prose compliance. A tool request is not evidence of successful travel or persistence.
The real actor path measures prompt/parser output; the migration-backed integration
suites separately verify effects, final-step execution limits, time and persistence.

## ADR 0017 final suite — prepared, live execution requires owner approval

`eval/dialogue_suite.py` reuses the captured/reconstructed PR 1 baseline, rather than
spending requests on another baseline. The v2 default includes six unchanged comparison
cases plus four separately identified review cases: ten cases × two default models ×
three repetitions = **60 trials**, nominally **186 generation requests**, bounded at **210**.
The original six-case v1 evidence remains immutable; v2 records the cap-6→4 runtime change
in its manifest through the effective gameplay configuration.

- saturated-context NPC invocation and injected-result placement/follow-up;
- real actor output in English and Italian against conflicting input language;
- an actor with an authored vow of silence;
- two independent actors followed by a dependent second beat, through real DM/tool/
  composition code in an isolated overlay, without persistence or background calls.
- an exact short quoted follow-up for the narrow echo guard, a scene-context actor parity
  case, a natural two-NPC exchange and a bounded two-turn continuation carrying the real
  prior transcript and state, with semantic relevance explicitly left for review.

`npc_followup_short`, `actor_scene`, `two_npc_natural` and `two_npc_conversation` are new fixtures with no v1
comparison. Their exact stimuli still require owner approval before any live run. The
natural exchange is not forced to produce a fixed number of actor turns; its expected
relevance is reported for prose review. Language checks are heuristic and always carry a
manual-review flag; ambiguous/mixed output is not a universal pass.
The natural cases do not require a fixed initial cast or second reply. Narrator and
actor language metrics are separate; exact-text echo counts are lexical signals, not
proof of a paraphrase or of who spoke. The conversation case carries two actual turns
without background memory calls, not a simulation of retrieval or compression.

The pipeline case has three DM opportunities and a seven-request foreground cap; a
normally shaped two-beat scene uses six. A cap hit is recorded as an incomplete bounded
evaluation, not silently treated as a gameplay failure or retried. The ordinary-NPC
verbosity policy remains unchanged. Mira is produced by the real scaffold with a fixed
fixture identity and seeded statblock; original captures remain untouched.
The two-turn conversation allows at most fourteen requests across two three-DM-call
turns. Selecting only the original six cases remains 36 trials with a ceiling of 72.

```text
# Offline: no profile lookup, provider request or public-catalog request.
uv run python eval/dialogue_suite.py --dry-run

# Select an offline subset; these flags do not resolve a profile or call the catalog.
uv run python eval/dialogue_suite.py --dry-run --suite candidate-a \
  --models nvidia/nemotron-3-ultra-550b-a55b:free --cases npc_speaks actor_scene --runs 1

# Only after explicit owner authorization; paths below are relative to backend/.
uv run python eval/dialogue_suite.py --user OWNER_UUID \
  --cases npc_speaks npc_followup actor_en actor_it actor_silent two_npc_two_beat \
  --budget AUTHORIZED_REQUESTS --ledger ../scratch/adr-0004-0017-eval/outputs/pr2-quality-v2/day-1.jsonl \
  --results ../scratch/adr-0004-0017-eval/outputs/pr2-quality-v2/trials.jsonl

# Future paid comparison requires both selecting and explicitly allowlisting the exact ID.
# This option is not authorization to run; owner approval and request budget remain required.
uv run python eval/dialogue_suite.py --dry-run --models vendor/model-id \
  --allow-paid-model vendor/model-id --cases npc_speaks --runs 1

# Next owner-started day, after confirming the available quota; reuse trials, new daily ledger.
uv run python eval/dialogue_suite.py --user OWNER_UUID --resume \
  --cases npc_speaks npc_followup actor_en actor_it actor_silent two_npc_two_beat \
  --budget AUTHORIZED_REQUESTS --ledger ../scratch/adr-0004-0017-eval/outputs/pr2-quality-v2/day-2.jsonl \
  --results ../scratch/adr-0004-0017-eval/outputs/pr2-quality-v2/trials.jsonl
```

On a fresh ledger, the budget is the authorized remaining allowance, not an inferred
quota reset. On that same ledger's resume, it remains the total cap including earlier
attempts; do not mistake it for another fresh allocation.
Trial scheduling checks its entire request ceiling before starting, and every actual DM/
actor attempt is reserved and captured separately before network I/O. SDK retries are
disabled on a copied personal client; settings/credentials are not changed. Rate limits
stop the day without polling or paid fallback. A provider failure marks only that trial
retryable: `--resume` on a later day repeats those specific trials and skips completed
ones, never rerunning the suite. A failed-trial retry requires a fresh ledger; historical
attempts and their costs remain in the combined usage report. An unstarted budget stop
can resume normally; a trial cut off after requests needs owner review. Interrupted trials require owner review. Completed
misses and provider failures remain visible as evidence.

The shared manifest freezes code, scenarios, models, effective gameplay configuration
and output cap. Resume skips completed matching trials, including across daily ledgers;
changed identities are rejected. Raw requests/results and complete public parts/transcript
remain local under ignored `scratch/.../outputs/`. Summaries report inventory only:
**evaluate acceptance after the complete suite**, including manual review of semantic
paraphrases that regex checks cannot certify. Engine insertion is not a guarantee against
invented dialogue in free prose. No travel baseline or contaminated `gold` derivation is run.
Per-attempt request hashes bind effective prompts, tools and parameters. `.usage.csv`
and `.usage.md` are generated offline beside the result file from all referenced ledgers,
including superseded retries. Missing provider usage/currency/cost stays unknown; cache
and reasoning are details of the totals, not additions. There is no local monetary
reservation: any external spending block is the owner's responsibility.

### Parallel execution and timing

The runner creates one independent sequential lane per selected model: four selected
models create four lanes, six create six. A lane starts its next trial as soon as its
previous trial finishes; there is no cross-model barrier. DM steps, dependent actor
beats and the two turns of a conversation retain their internal order. Actor fan-out
can therefore produce more simultaneous HTTP requests than there are model lanes.

All generation requests whose model ID ends in `:free` automatically share a limit
of **20 starts per rolling 60 seconds**, including DM and actor requests. There is
no `--free` opt-in to forget. Paid requests bypass this limiter, not request budgets.
The limiter covers this process only: do not run another free eval/UI client on the
same account concurrently, and leave 60 seconds between separate invocations.

Before starting a trial, the scheduler holds its full request ceiling from the shared
remaining allowance. Unused capacity is released when it finishes; only actual
reserved provider attempts are written to the request ledger or counted as spent.
HTTP 429 stops new requests across lanes without retrying; already-sent requests can
finish. Cancelling a queued rate wait consumes no request; cancelling a sent request
leaves interrupted evidence that requires owner review before resume.

Per-request `seconds` measures the provider call, excluding throttling;
`rate_limit_wait_seconds` records throttling separately in the ledger and usage reports.
Trial `seconds` includes its rate waits. Summary `timing.wall_seconds` and
`timing.model_wall_seconds` measure this invocation's execution/lane wall times,
including budget waits but excluding catalog/profile setup; they are not cumulative
timings across resumed invocations. Request-latency sums are not suite wall time.

### Owner-approved acceptance rubric (2026-11-03)

Evaluate each obligation separately, per model and case. With three repetitions,
**3/3** means respected in this sample, **2/3** unstable, **0–1/3** unreliable; none
establishes a general reliability guarantee. The one-repetition diagnostic round is
exploratory, not an acceptance result. Paid success does not substitute for free-model
validation, and no aggregate score may conceal a failing obligation.

| Area | Review criterion |
|---|---|
| Engine | No pipeline-introduced loss/duplication of actor lines; coherent ordering, transcript and state. |
| Actor envelope | Valid JSON/typed outcome; a safely handled malformed response remains an actor failure. |
| Silence | Intentional silence is distinct from missing invocation or generation failure. |
| Placement/echo | Separate accepted markers/fallback, quoted copies, unquoted copies and paraphrases; lexical checks are not semantic review. |
| Language | Review narrator and actors separately, including mixed-language output. |
| Dependent beat | Separate missing call, failed actor and an answer that actually uses the previous public intervention. |
| Prose | Relevant, continuous, canon-compatible geography/identities, no automatic secret disclosure where applicable, at most four spoken lines per actor call. |
| Natural cases | Judge whether the choice of speakers is sensible; no mandatory cast or response count. |

The courier seal is seeded through the real inventory tool only in
`two_npc_natural` and `two_npc_conversation`; captured fixtures and all six comparison
case overlays remain unchanged. The shared output cap remains **60,000 tokens**.

### Prepared four-model diagnostic — not live authorization

The owner selected exactly these four IDs; do not add alternatives or silently fall
back. The first diagnostic selects `npc_followup`, `actor_en` and
`two_npc_two_beat`, one repetition per model: **12 trials**, nominally **32 requests**,
ceiling **36**. Its evidence/manifest stays separate from the final regression suite.

```bash
cd backend
uv run python eval/dialogue_suite.py --dry-run \
  --suite adr-0017-quality-diagnostic-v2 \
  --models deepseek/deepseek-v4.1-flash-1017 z-ai/glm-5.3-flash \
    nvidia/nemotron-3-ultra-550b-a55b:free nvidia/nemotron-3.5-super-vl:free \
  --allow-paid-model deepseek/deepseek-v4.1-flash-1017 \
  --allow-paid-model z-ai/glm-5.3-flash \
  --cases npc_followup actor_en two_npc_two_beat --runs 1
```

This command is offline. Do not replace `--dry-run` with live arguments until the
owner authorizes provider/catalog contact and the request allocation. The full final
four-model, ten-case, three-repetition suite remains **120 trials**, ceiling **420**,
excluding this diagnostic, authorized retries and separately accounted UI playtests.

### Prepared DM-example comparison — renewed live consent required

The first diagnostic completed 12 trials and 30 generation requests on candidate
`3dc8695`; the owner reports $0.02 in the OpenRouter dashboard. Its evidence remains
immutable in `scratch/adr-0004-0017-eval/outputs/pr2-quality-v2/diagnostic-20261103-3dc8695/`.
The next candidate changes only DM prompt text: permanent composition examples remain
present in opening and closing calls, while actor-call policy remains tool-dependent.
Actor prompts, engine/guard, fixtures, output limits, models and routing are unchanged.

Compare `npc_followup`, `actor_en` and `two_npc_two_beat` with the prior diagnostic;
label `npc_followup_short` separately because it has no live result from that round.
One run on the same four models is **16 trials**, nominally **36 generation requests**,
ceiling **40**. Use a new checkpoint and evidence directory; never resume the earlier
manifest or overwrite its outputs. Keep cache/routing behavior unchanged for this
prompt comparison; the owner's caching investigation is separate from this candidate.

```bash
cd backend
uv run python eval/dialogue_suite.py --dry-run \
  --suite adr-0017-dm-examples-v1 \
  --models deepseek/deepseek-v4.1-flash-1017 z-ai/glm-5.3-flash \
    nvidia/nemotron-3-ultra-550b-a55b:free nvidia/nemotron-3.5-super-vl:free \
  --allow-paid-model deepseek/deepseek-v4.1-flash-1017 \
  --allow-paid-model z-ai/glm-5.3-flash \
  --cases npc_followup actor_en two_npc_two_beat npc_followup_short --runs 1
```

This is still offline preparation, not permission to contact the catalog or run paid
or free inference. Prose review stays with the owner-requested Luna agent; the parent
must not reread raw outputs unless the owner changes that instruction. The full final
suite and UI playtest still require separate authorization and evidence.

### Approved direct comparison with eval-only session affinity

The owner subsequently approved adding affinity before the same 16-trial, 40-request
maximum run rather than spending six requests on a separate cache probe. This is a
new cohort: **DM examples plus explicit affinity**, not an isolated prompt A/B against
`3dc8695` or a causal cache-benefit measurement. The prepared prompt-only candidate
`63f8305` has not been evaluated live. The four selected models/cases, 60k cap,
free-model limiter and no-retry policy stay unchanged.

`--session-affinity` is off by default and affects only the eval. When enabled, each
trial gets a UUIDv5 derived from its already opaque, model/case/run-specific trial
key. It is shared by that trial's DM and NPC calls, remains stable through its turns
and resume, and differs for independent trials; it is not a global hardcoded value
or a UUID regenerated per request. The constant UUID namespace is not a session ID.
An isolated copy of the SDK client sends `x-session-id`, preserving existing headers,
credentials and zero retries without mutating the personal or another trial's client.

Only this explicit, non-secret header is stored in `request_headers` and CSV
`session_id`; the request hash covers `{body, headers}` when enabled and keeps its
legacy body-input hash when disabled. The manifest records `per-trial` versus
`implicit` affinity, so resume cannot mix regimes. Production requests, settings,
prompt layout and provider/fallback policy are not changed by this flag.

According to the owner-requested documentation research, OpenRouter accepts the
[session header](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
as a sticky-routing key, not a unique cache slot. A different NPC prefix does not
automatically overwrite a DM prefix. [Caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
still depends on the actual prefix, endpoint and best-effort retention; affinity is
not provider pinning and can be affected by tool routing. DeepSeek/Z.AI automatic
cache support does not establish support on the selected Nemotron free endpoints.

Observe `cached_input_tokens > 0`, reported cost and request latency separately by
model/role/step; missing usage stays unknown. Existing reports do not capture the
actual upstream provider or cache-write tokens, so ID presence and latency alone
cannot prove a cache hit or that the provider stayed fixed. No extra generation,
warming, authenticated metadata lookup or provider pinning is added. Any production
adoption belongs in the owner's separate PR after the eval evidence is reviewed.

```bash
cd backend
uv run python eval/dialogue_suite.py --dry-run \
  --suite adr-0017-dm-examples-affinity-v1 --session-affinity \
  --models deepseek/deepseek-v4.1-flash-1017 z-ai/glm-5.3-flash \
    nvidia/nemotron-3-ultra-550b-a55b:free nvidia/nemotron-3.5-super-vl:free \
  --allow-paid-model deepseek/deepseek-v4.1-flash-1017 \
  --allow-paid-model z-ai/glm-5.3-flash \
  --cases npc_followup actor_en two_npc_two_beat npc_followup_short --runs 1
```

The command above is offline; the approved live invocation uses a fresh ledger and
results directory with `--budget 40`, no baseline rerun, no added models and no
automatic progression to the 420-request final regression suite.

## Deliberately out of scope

**No combat in gold.** ADR 0003 removes `start_combat` / `end_combat` / `combat_state` and
rewrites resolution entirely. Combat turns authored now would rot on that ADR's first sprint,
and none of the current probes need them. The arc is social and exploratory, which this world
supports natively.
