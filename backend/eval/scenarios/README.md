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

`scenario_build.py --from-campaign <uuid> --at-turn 25` emits the **same** format from a real
campaign in the database. The harness cannot tell the difference. That is why the format was
fixed before either producer was written.

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

`updates` uses the live handler keys: `npc_psychology`, `inventory_change`, `quest_update`,
`hp_change`, `event_log_entry`.

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

## Deliberately out of scope

**No combat in gold.** ADR 0003 removes `start_combat` / `end_combat` / `combat_state` and
rewrites resolution entirely. Combat turns authored now would rot on that ADR's first sprint,
and none of the current probes need them. The arc is social and exploratory, which this world
supports natively.
