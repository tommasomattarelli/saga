"""Fill a built scenario's context by running the REAL memory subsystems.

The quota-spending half of the fixture build. `scenario_build.py` produces world
state and history without touching a provider; this pass runs the batch
compressor, the rolling global summary and the fact extractor over the same
authored transcript, so `context.*` and `fact_corpus` hold what the engine would
actually have produced after those turns — not prose written for the fixture.

Routing goes through the router exactly as production does, so there is no
`--model` flag: the fixture is derived on whatever the operator has configured
for background work. Override a single run with
`SAGA_MODEL_MEMORY_COMPRESSION_DEFAULT`.

Every provider call is checkpointed. A free-tier daily cap hit halfway through
must not throw away the calls already paid for — rerun and it resumes.

Usage:
  cd backend
  uv run python eval/derive.py gold
  uv run python eval/derive.py gold --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# app.config resolves `.env` relative to the cwd, so running from backend/ finds
# nothing and every provider override silently falls back to the YAML defaults.
# Load the real one before anything imports settings — deriving 34 calls against
# the wrong provider is the expensive way to discover this.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from scenario_build import BUILT, load_transcript  # noqa: E402

from app.ai.context import GameContext  # noqa: E402
from app.ai.router import AICallType, get_gameplay_config, route_ai_call  # noqa: E402

# Private helpers on purpose: the point of this pass is to drive the production
# summariser, not a second implementation that can drift from it.
from app.memory.compressor import _batch_prefix, compress_turns_batch_llm  # noqa: E402
from app.memory.fact_extractor import extract_facts  # noqa: E402
from app.memory.global_summary import (  # noqa: E402
    INITIAL_PROMPT,
    UPDATE_PROMPT,
    _format_turns,
    _generate_summary,
)
from app.models.turn import Turn  # noqa: E402

COMPRESSION_BATCH = 5  # compressor.ensure_compression hardcodes this
RECALL_ROWS = 5  # context._load_batch_summaries reads this many turn rows


# --- checkpointing ----------------------------------------------------------


def _checkpoint(name: str) -> Path:
    return BUILT / f".{name}.derive.json"


def load_state(name: str, resume: bool) -> dict:
    path = _checkpoint(name)
    if resume and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"batches": {}, "global": {}, "facts": {}}


def save_state(name: str, state: dict) -> None:
    BUILT.mkdir(parents=True, exist_ok=True)
    _checkpoint(name).write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


def as_turns(turns: list[dict]) -> list[Turn]:
    """In-memory Turn rows — the summariser reads attributes, never a session."""
    return [Turn(turn_number=t["n"], player_action=t["player"], narration=t["dm"]) for t in turns]


# --- passes -----------------------------------------------------------------


async def derive_batch_summaries(
    name: str, turns: list[dict], window: int, state: dict
) -> dict[int, str]:
    """Mirrors ensure_compression: turns past the active window, batched by five,
    each batch's summary written onto every turn it covers."""
    cutoff = len(turns) - window
    if cutoff <= 0:
        return {}

    per_turn: dict[int, str] = {}
    eligible = turns[:cutoff]
    for start in range(0, len(eligible), COMPRESSION_BATCH):
        batch = eligible[start : start + COMPRESSION_BATCH]
        key = f"{batch[0]['n']}-{batch[-1]['n']}"

        if key not in state["batches"]:
            summary = await compress_turns_batch_llm(as_turns(batch))
            if not summary:
                raise SystemExit(f"compression returned nothing for turns {key} — rerun to resume")
            state["batches"][key] = summary
            save_state(name, state)
            print(f"  compressed turns {key}")

        prefix = _batch_prefix(as_turns(batch))
        for turn in batch:
            per_turn[turn["n"]] = f"{prefix}{state['batches'][key]}"
    return per_turn


def summary_context(per_turn: dict[int, str], oldest_in_window: int) -> str:
    """Mirrors context._load_batch_summaries — the reader takes the last five turn
    *rows* below the window and dedupes, so only the last couple of batch summaries
    ever reach the prompt. Joining every batch would build a context production
    never builds."""
    rows = sorted((n for n in per_turn if n < oldest_in_window), reverse=True)[:RECALL_ROWS]
    seen: set[str] = set()
    unique: list[str] = []
    for n in reversed(rows):
        if per_turn[n] not in seen:
            seen.add(per_turn[n])
            unique.append(per_turn[n])
    return "\n".join(unique)


async def derive_global_summary(name: str, turns: list[dict], state: dict) -> str:
    """Mirrors update_global_summary: fired every N turns, each batch folded into
    the summary that already exists rather than regenerated from scratch."""
    config = get_gameplay_config()
    every = max(1, config.global_summary_update_every)
    cap = config.global_summary_max_input_chars

    existing = state["global"].get("summary", "")
    through = state["global"].get("through", 0)

    for current in range(every, len(turns) + 1, every):
        if current <= through:
            continue
        lower = max(1, current - every + 1)
        batch = [t for t in turns if lower <= t["n"] <= current]
        turns_text = _format_turns(as_turns(batch))

        trimmed = existing[-cap:] if len(existing) > cap else existing
        prompt = (
            UPDATE_PROMPT.format(existing=trimmed, turns_text=turns_text)
            if trimmed
            else INITIAL_PROMPT.format(turns_text=turns_text)
        )

        summary = await _generate_summary(prompt)
        if not summary:
            raise SystemExit(
                f"global summary returned nothing at turn {current} — rerun to resume"
            )
        existing = summary
        state["global"] = {"summary": existing, "through": current}
        save_state(name, state)
        print(f"  global summary through turn {current}")

    return existing


async def derive_fact_corpus(
    name: str, turns: list[dict], canaries: dict[str, str], state: dict
) -> list[dict]:
    """One extraction per turn, as production runs it, plus the authored canaries —
    facts a probe can interrogate that the model cannot infer from the scene."""
    corpus: list[dict] = []
    for turn in turns:
        key = str(turn["n"])
        if key not in state["facts"]:
            dialogues = None
            if npc := turn.get("npc"):
                dialogues = [f"{npc['name']}: {npc['dialogue']}"]
            state["facts"][key] = await extract_facts(turn["player"], turn["dm"], dialogues)
            save_state(name, state)
            print(f"  facts from turn {turn['n']}: {len(state['facts'][key])}")

        corpus.extend({"turn": turn["n"], **fact} for fact in state["facts"][key])

    corpus.extend(
        {"turn": 0, "canary": canary, "entity_type": "secret", "content": text}
        for canary, text in canaries.items()
    )
    return corpus


RECALL_LIMIT = 3  # context._recall_memories asks pgvector for this many


def resolve_recall(probes: dict[str, dict], corpus: list[dict]) -> dict[str, list[str]]:
    """Turn each probe's authored recall tokens into the strings the DM will see.

    A token is a canary key or an entity name in the derived corpus. Selection is
    authored rather than searched — but the *content* is real extracted output, so
    the fixture cannot drift into recall the engine could never have produced. An
    unresolvable token is fatal for the same reason scenario_build validates places:
    a fixture pointing at something that does not exist measures garbage in silence.
    """
    by_canary = {fact["canary"]: fact["content"] for fact in corpus if fact.get("canary")}
    by_entity: dict[str, list[str]] = {}
    for fact in corpus:
        if name := str(fact.get("entity_name") or "").strip().lower():
            by_entity.setdefault(name, []).append(fact["content"])

    recall: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for probe, fields in probes.items():
        picked: list[str] = []
        for token in fields.get("recall") or []:
            if token in by_canary:
                picked.append(by_canary[token])
            elif matches := by_entity.get(token.strip().lower()):
                picked.extend(matches)
            else:
                unresolved.append(f"{probe}: '{token}'")
        recall[probe] = picked[:RECALL_LIMIT]

    if unresolved:
        raise SystemExit(
            "recall tokens match no canary and no extracted entity:\n  " + "\n  ".join(unresolved)
        )
    return recall


# --- entry point ------------------------------------------------------------


async def resolve_model() -> Any:
    empty = GameContext(
        system_prompt="", messages=[], importance_score=0, active_quests=[], recent_events=[]
    )
    return await route_ai_call(AICallType.MEMORY_COMPRESSION, empty)


def call_budget(turn_count: int, window: int) -> dict[str, int]:
    compressible = max(0, turn_count - window)
    batches = -(-compressible // COMPRESSION_BATCH)
    every = max(1, get_gameplay_config().global_summary_update_every)
    return {"compression": batches, "global_summary": turn_count // every, "facts": turn_count}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", help="transcript name, e.g. gold")
    parser.add_argument("--variant", help="overlay under transcripts/variants/")
    parser.add_argument(
        "--dry-run", action="store_true", help="report the call budget, call nothing"
    )
    parser.add_argument(
        "--restart", action="store_true", help="discard the checkpoint and derive from scratch"
    )
    args = parser.parse_args()

    name = args.variant or args.transcript
    path = BUILT / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"no built scenario '{name}' — run eval/scenario_build.py first")

    meta, turns, _ = load_transcript(args.transcript, args.variant)
    scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    window = scenario["meta"]["active_window_turns"]

    model_config = await resolve_model()
    budget = call_budget(len(turns), window)
    print(f"{name}: {len(turns)} turns, active window {window}")
    print(f"  routing to {model_config.provider} / {model_config.model}")
    print(
        f"  budget: {budget['compression']} compression + {budget['global_summary']} global"
        f" + {budget['facts']} facts = {sum(budget.values())} calls"
    )

    if args.dry_run:
        print("  dry-run: nothing called, nothing written")
        return

    state = load_state(name, resume=not args.restart)
    per_turn = await derive_batch_summaries(name, turns, window, state)
    global_summary = await derive_global_summary(name, turns, state)
    corpus = await derive_fact_corpus(name, turns, meta.get("canaries") or {}, state)

    scenario["context"] = {
        "global_summary": global_summary,
        "summary_context": summary_context(per_turn, len(turns) - window + 1),
        "recall": resolve_recall(meta.get("probes") or {}, corpus),
    }
    scenario["fact_corpus"] = corpus
    scenario["meta"]["derived"] = True
    scenario["meta"]["derive"] = {
        "provider": model_config.provider,
        "model": model_config.model,
        "turns": len(turns),
    }

    path.write_text(
        "# GENERATED by eval/scenario_build.py, context filled by eval/derive.py.\n"
        "# Do not edit by hand.\n"
        + yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    _checkpoint(name).unlink(missing_ok=True)
    print(f"  wrote {path.relative_to(BUILT.parent.parent)}, {len(corpus)} facts")


if __name__ == "__main__":
    asyncio.run(main())
