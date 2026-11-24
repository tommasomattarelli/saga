# Evaluation tools

The evaluation harnesses measure prompt and dialogue behavior against controlled
scenarios. They are operator tools, not part of the application runtime. Run the
commands below from `backend/`.

## Layout

| Path | Responsibility |
|---|---|
| `eval/dialogue/` | Multi-turn dialogue suite and trial orchestration |
| `eval/probes/` | Reusable checks and bounded actor probes |
| `eval/scenario_tools/` | Scenario loading and offline transcript build |
| `eval/smoke/` | Per-model smoke runner |
| `eval/support/` | Request ledger, provider calls, tracing, affinity, run lock and usage reports |
| `eval/cache/` | Separate OpenRouter cache diagnostic |
| `eval/integrated_memory/` | Guarded API-to-DB memory replay, persisted-source evidence and offline run preparation |
| `eval/memory_scenarios/` | Controlled memory sources replayed through real operation handlers |
| `eval/memory_capture.py` | Read-only capture of unambiguous legacy campaign transcripts |
| `eval/scenarios/` | Authored transcripts, overlays, stimuli and built fixtures |

## Scenarios and probes

A scenario supplies world state, context, recent history and scene-specific
stimuli. Checks live separately in `eval/probes/probes.py`: a check should mean
the same thing across scenarios, while its stimulus belongs to the scene. This
allows the same obligation to be measured with an empty and a saturated context.
The smoke report's per-scenario scores and delta are more useful than a pooled
absolute score; heuristic failures still need human review.

Current scenario tools:

- `eval.scenario_tools.build` replays an authored transcript through production
  state handlers. It is offline and leaves generated memory context empty.

`transcripts/variants/<name>/overlay.yaml` changes only the turns relevant to a
variant; avoid full transcript copies that can drift. `world_patch` is reserved
for state without a typed replay handler, such as player position and node
status. Captured campaign data must be anonymized before it is committed.
The old context-capture CLI has been retired with the derive CLI; no integrated
context-capture workflow is currently available. `eval.memory_capture` remains a
separate read-only source capture for the archived ADR 0020 S3 dataset below.

Legacy generated `gold`, `bloat` and `contradiction` built fixtures and the old
capture/derivation CLIs are retired; the authored gold transcript and its
overlays remain offline builder inputs. Authored transcripts are not reviewed
saturated-memory evidence. Integrated S6 preparation is described separately
below; preparation is not live authorization or quality evidence.

## Offline preparation

These commands do not make generation requests. `build --check-only` validates
an authored transcript without writing a fixture. The controlled-source builder
remains available below, alongside integrated S6 preparation; the S3 producer
comparison is archived.

```bash
uv run python -m eval.scenario_tools.build gold --check-only
uv run python -m eval.scenario_tools.build gold --variant contradiction --check-only
uv run python -m eval.smoke.model_smoke \
  --model nvidia/nemotron-3-ultra-550b-a55b:free \
  --scenario debug-thornhaven --probe travel_move --dry-run
uv run python -m eval.dialogue.suite --dry-run
```

The smoke dry-run builds prompts and reports their size. The dialogue dry-run
prints a manifest without resolving a personal profile or contacting a provider
or model catalog. The cache probe's `prepare` command is also offline:

```bash
uv run python -m eval.cache.probe prepare \
  --model deepseek/deepseek-v4.1-flash-1017 --phase identical \
  --run-id <unique-run-id> --out <new-output-directory>
```

Review the generated manifest and payloads before any live run. A source, commit
or payload change requires a fresh output directory; prepared evidence is never
silently rewritten.

## Live-run safeguards

Live evaluation requires explicit owner authorization, the deployment's normal
environment and the owner's existing profile. Pass a request budget and reuse
the same daily ledger across resumptions; the budget is the ledger's total cap,
not a new allocation per invocation. Never put credentials in fixtures,
commands or reports.

Each provider attempt is reserved in the ledger before network I/O. Evaluation
clients disable SDK retries. Interrupted attempts require review and are not
retried automatically; retries of failed trials use a fresh ledger while
preserving previous evidence. A free-model limiter is process-local, so do not
run another evaluation or UI client on the same account concurrently. Budgets
do not reserve money with the provider; the owner remains responsible for any
external spending limit.

### Session affinity

The dialogue suite's default session affinity shares one stable `x-session-id`
per manifest and model across its cases, repetitions, DM calls and actors. The
smoke runner shares one per checkpoint and model. These IDs support routing
continuity but do not isolate provider caches or guarantee cache hits. Reports
must be reviewed for semantic quality; lexical and language heuristics are not
acceptance evidence by themselves.

## Memory producer evaluation (ADR 0020 S3) — archived

The isolated-producer comparison was retired by ADR 0020 S6. It compared one
combined summary/facts request against two specialist requests over identical
canonical batch sources; a separate global chain consumed the original batches
and its preceding checkpoint, never the intermediate summaries. The `eval.memory`
harness, its prepare/run/report CLI and the comparison manifests are no longer in
the tree; their evidence stays on disk and the code remains in git history. No
standalone producer-comparison CLI remains; the integrated harness below is
the memory evaluation path, including its optional combined-request sidecar.

The controlled, explicitly synthetic source builder remains available offline:

```bash
uv run python -m eval.memory_scenarios.build \
  --out <new-source-directory> --batch-size <B> \
  --raw-turns <R> --intermediate-limit <K> --global-updates <J>
```

The source uses production tool/finalization handlers, deterministic randomness
and an authored NPC response at the actor boundary. Narration is finalized by the
engine. `batches.json` contains complete batches with local references; the full
source, annotations and incomplete tail are retained separately. Review planning
sufficiency and whether the incorporated prefix actually reaches the late
resolution: enough turns alone is not evidence of a useful global experiment.

The real S0 sample is a different dataset, not replaced by this scenario. When
the owner makes its legacy database available, capture it without migration or
workers:

```bash
uv run python -m eval.memory_capture \
  --campaign <campaign-uuid> --batch-size <B> --out <new-capture-directory>
```

Capture requires `REPEATABLE READ READ ONLY`, rejects ambiguous or history-aware
sources, preserves empty narration, and marks old operations as unrecorded rather
than reconstructing them from UI events. Never commit private campaign text.

The retired comparison also owned its own fact/global policy selection, session
scope, concurrent workers and human-review report; those are historical detail,
not usable tooling. The integrated harness freezes its own manifest and evidence
contracts instead.

## Integrated memory evaluation (ADR 0020 S6)

This runner replays the authored scenario through the authenticated action API,
production graph, operation handlers, PostgreSQL and durable memory jobs. Only
external DM/NPC responses are controlled; recall-query embeddings and probes are
excluded. It never enters the application lifespan or starts background workers.
Its provider instrumentation lives entirely under `eval/`, not in the game runtime.

Prepare and review a new evidence directory **offline**:

```bash
uv run python -m eval.integrated_memory.cli prepare \
  --sources <source-directory>/sources.json \
  --run-id <unique-run-id> --output <new-evidence-directory>
uv run python -m eval.integrated_memory.cli validate --output <evidence-directory>
uv run python -m eval.integrated_memory.cli report --output <evidence-directory>
```

These commands do not resolve credentials, query model catalogs or contact
providers. The manifest freezes source, code, world assets, production policy,
embedding policy and the existing generation output cap. A draft has no selected
model, embedding space or request/text-attempt budgets; it remains unapproved and
non-executable. Every generation model needs its own prepared run and authorization.

For the 52-turn R8/B4/K2/H1 scenario, a successful first-attempt baseline makes
22 specialist plus 9 global generation requests per model. The optional unified
sidecar adds 11 requests on those same persisted batches, for 42 total. It does
not publish alternate production memory. Generation SDK retries are disabled;
the runner stops before any memory-job retry, despite the campaign's persisted
four-attempt policy. Authorizing retries requires a newly reviewed run scope.

The 66-text bound concerns **distinct fact contents**, not outbound requests or
submitted-text attempts. Embeddings are drained after replay through the real
queue and vector publication. Batching and the frozen finite retry policy determine
actual attempts; every retry reserves another request and its submitted texts.
Choose separate generation-request, embedding-request and embedding-text-attempt
caps explicitly. Caps bound provider attempts, not currency or provider-side routing.

Preparation may reduce the frozen embedding retry count with
`--embedding-max-retries`; it cannot exceed the configured policy, change the
personal profile or change production defaults. The owner-selected preparation
uses one retry and caps of 6 embedding requests / 132 submitted texts, plus
42 generation requests including the sidecar. Generation must stay free;
OpenRouter `openai/text-embedding-3-small` is separately allowed to incur its
small embedding cost. These selections are not permission to execute a run.

The run directory is locked, and reservations are persisted before each provider
attempt. Failed, cancelled, interrupted or incompatible evidence cannot silently
resume or reset its budget. Re-running an existing integrated run requires manual
review; no automatic replay or retry-wait loop is provided. Do not run other
evaluations, application workers or account clients concurrently.

Live execution remains a separate gate: review the exact manifest, model/payment
permissions, embedding profile/space, caps, retry policy and output limits, then
obtain explicit owner authorization for that single run. A CLI flag is not owner
consent, and no preparation or deterministic test confirms production defaults,
variant quality, recall effectiveness, ADR acceptance or permission to merge main.

## OpenRouter cache diagnostic

This diagnostic is separate from the narrative suite. It builds real DM prompts
from `debug-thornhaven` and makes no NPC generation. One invocation handles one
model and one phase, with exactly eight generation requests; there is no
automatic retry, next phase or next model. Review after each block before
starting another:

1. `identical` repeats request A in per-trial and shared-session regimes.
2. `replay` sends A then a fixed continuation B in each regime.

After reviewing the prepared output and explicitly authorizing the run, use the
same output directory and the owner's UUID:

```bash
uv run python -m eval.cache.probe run --out <output-directory> --user <owner-uuid>
uv run python -m eval.cache.probe report --out <output-directory>
```

Review the report and provider dashboard before preparing another phase or
model. `report` regenerates output offline without changing owner notes.

Interpret cached tokens, cache fraction, cost and latency separately. Initial
cache warmth is unknown, the shared regime can benefit from earlier requests,
and different session IDs are routing keys rather than isolated cache slots.
The probe does not measure live NPC interleaving, background memory calls or
causal cache benefit. Missing usage or provider metadata remains unknown, not a
zero or a confirmed cache hit.
