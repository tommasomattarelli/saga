# OpenRouter cache probe

An operator diagnostic, separate from the narrative evaluation suite. It uses
SAGA's saturated `debug-thornhaven` fixture and real DM prompt/tool builders.
Preparation is offline; neither fixture assembly nor report generation resolves
credentials or contacts a catalog/provider.

## Experiment

One model and **one eight-request phase per invocation**, in this fixed order:

| Phase | Per-trial ID | Shared ID | Total |
|---|---|---|---:|
| `identical` | T1: A→A; T2: A→A | S: A→A; S: A→A | 8 |
| `replay` | T1: A→B; T2: A→B | S: A→B; S: A→B | 8 |

Start with `deepseek/deepseek-v4.1-flash-1017`, then review before selecting
`z-ai/glm-5.3-flash`. Each model uses **16 generations**, not the earlier proposed
24. There is no automatic third repetition, next phase, next model or retry.

A is a frozen opening DM request. B is its fixed continuation after `invoke_npc`:
the real tools executor applies one simulated actor result, deriving NPC history,
line handles, beat state and prompt reminders. No NPC generation is performed.
The live response to A never constructs B, so omitted tools or truncated argument
JSON cannot change the schedule. The mock exists only during offline assembly.

The SDK client comes from the owner's normal router/credential resolution. The
probe sends the same request shape as `LocalProvider.generate_with_tools`, but
reads the SDK response directly: production intentionally rejects truncated prose;
this diagnostic records `finish_reason=length` and continues. A transport or
in-band upstream failure instead stops the block, without retrying.

`max_tokens` defaults to **1024** and cannot exceed that agreed probe cap. This is
an upstream generation limit, not local truncation. Reasoning usually consumes
the same budget. Missing usage remains unknown; generated narrative text is not
needed or stored by this probe.

## Commands

From `backend/`, prepare a fresh manifest (no network/DB):

```bash
uv run python eval/cache/probe.py prepare \
  --model deepseek/deepseek-v4.1-flash-1017 --phase identical \
  --run-id cache-20261105 \
  --out ../scratch/openrouter-cache/20261105/deepseek-identical
```

Review `manifest.json`, its eight requests, frozen payloads and approximate cost
before starting. The manifest includes source and payload hashes, HEAD and dirty
state. A later source/commit change requires preparation into a new directory;
existing manifests are never silently updated.

After owner approval, supply the deployment's normal database/encryption
environment and the owner's UUID (never extract a key into a command or artifact):

```bash
uv run python eval/cache/probe.py run \
  --out ../scratch/openrouter-cache/20261105/deepseek-identical \
  --user OWNER_UUID
```

The command resolves the personal OpenRouter profile without changing it or its
model preference. An isolated client copy disables SDK retries; a per-request
`x-session-id` leaves shared clients untouched. Every generation is reserved in
the existing request ledger before network I/O. `started.json` exclusively claims
the block; interrupted or completed blocks cannot be run again automatically.
Review interrupted evidence before authorizing any replacement experiment.

After the generation block, one metadata GET per available response ID queries
`/generation`; these are not generations and do not consume the eight-generation
allocation. Missing metadata is reported for dashboard review, without polling.

**Stop after the eight calls.** Review `report.md` and the OpenRouter dashboard;
put observations and actual pause duration in `owner-notes.md`. Only at the
owner's next go, prepare/run `--phase replay` in another directory. The same
pause/review applies before GLM. Do not run phases/models in parallel.

Regenerate the report offline (leaves `owner-notes.md` untouched):

```bash
uv run python eval/cache/probe.py report \
  --out ../scratch/openrouter-cache/20261105/deepseek-identical
```

## Interpreting results

- The first request may already find a warm cache. Per-trial runs before shared,
  so the second regime can benefit from the first. These are exploratory
  observations, not a causal A/B or an acceptance threshold.
- UUIDs are derived from run/model/phase/payload identity and regime (plus trial
  for per-trial). Different IDs are routing keys, **not isolated cache slots**.
- Pausing 5–10 minutes does not guarantee cold cache. OpenRouter's documented
  ten-minute inactivity expiry concerns routing affinity, not upstream cache TTL.
- Compare per-request cached tokens and the cached fraction, not just hit count.
  Keep endpoint pricing, reasoning/output cost and latency distinct.
- `metadata.jsonl` preserves provider name, available endpoint attempts and cache
  discount; absent routing information still needs the owner's dashboard check.
  A provider name alone does not identify a physical cache/backend.
- The replay measures DM cache reuse. It does not measure actual interleaved NPC
  requests, concurrency, elapsed gameplay idle time or background memory calls.
- No universal 4k-token threshold is assumed. Prompts retain their natural size;
  short reusable prefixes can legitimately miss even with working affinity.

Sources: [OpenRouter caching](https://openrouter.ai/docs/guides/best-practices/prompt-caching),
[generation metadata](https://openrouter.ai/docs/api/api-reference/generations/get-generation),
[max_tokens](https://openrouter.ai/docs/api/reference/parameters).

The external session plan is `~/.opencode/plan/openrouter-cache-probe.md`; prior
ADR 0017 evidence and production requests remain separate from these new runs.
