# Evaluation tools

The evaluation harnesses measure prompt and dialogue behavior against controlled
scenarios. They are operator tools, not part of the application runtime. Run the
commands below from `backend/`.

## Layout

| Path | Responsibility |
|---|---|
| `eval/dialogue/` | Multi-turn dialogue suite and trial orchestration |
| `eval/probes/` | Reusable checks and bounded actor probes |
| `eval/scenario_tools/` | Scenario loading, capture, offline build and context derivation |
| `eval/smoke/` | Per-model smoke runner |
| `eval/support/` | Request ledger, provider calls, tracing, affinity and usage reports |
| `eval/cache/` | Separate OpenRouter cache diagnostic |
| `eval/scenarios/` | Authored transcripts, overlays, stimuli and built fixtures |

## Scenarios and probes

A scenario supplies world state, context, recent history and scene-specific
stimuli. Checks live separately in `eval/probes/probes.py`: a check should mean
the same thing across scenarios, while its stimulus belongs to the scene. This
allows the same obligation to be measured with an empty and a saturated context.
The smoke report's per-scenario scores and delta are more useful than a pooled
absolute score; heuristic failures still need human review.

There are three fixture producers:

- `eval.scenario_tools.build` replays an authored transcript through production
  state handlers. It is offline and leaves summaries, recall and fact corpus
  empty, marking the output `derived: false`.
- `eval.scenario_tools.derive` runs the real summarizer and fact extractor over
  that transcript. It uses the configured router, can spend provider quota, and
  checkpoints each call so a later invocation can resume.
- `eval.scenario_tools.capture_scenario` captures an existing campaign's state
  and history. Stimuli and per-probe recall remain authored fixture data.

`transcripts/variants/<name>/overlay.yaml` changes only the turns relevant to a
variant; avoid full transcript copies that can drift. `world_patch` is reserved
for state without a typed replay handler, such as player position and node
status. Captured campaign data must be anonymized before it is committed.

**Current fixture warning:** `scenarios/built/gold.yaml` is still marked
`derived: false`, and its `global_summary` contains contaminated model output.
Do not use it as a valid saturated-context baseline until it has been
re-derived and reviewed. Building it again only recreates world state and
history; it does not derive context.

## Offline preparation

These commands do not make generation requests. `build --check-only` validates
an authored transcript without writing a fixture; `derive --dry-run` reports
the configured provider and request budget without making calls.

```bash
uv run python -m eval.scenario_tools.build gold --check-only
uv run python -m eval.scenario_tools.build gold --variant contradiction --check-only
uv run python -m eval.scenario_tools.derive gold --dry-run
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
