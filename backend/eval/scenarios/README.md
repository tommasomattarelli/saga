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

## Deliberately out of scope

**No combat in gold.** ADR 0003 removes `start_combat` / `end_combat` / `combat_state` and
rewrites resolution entirely. Combat turns authored now would rot on that ADR's first sprint,
and none of the current probes need them. The arc is social and exploratory, which this world
supports natively.
