"""Model smoke harness — does a candidate model honour the DM's tool obligations?

Not a test suite: an evaluation tool. It drives SAGA's *real* DM system prompt and
*real* tool schemas against a candidate model and scores the behaviours the
v0.2.0-beta.1 playtest found broken — invoke_npc skipped (#52), NPC output
paraphrased (#53), narration language drifting (#51).

Compliance is stochastic, so a single sample says nothing: every scenario runs
--runs times and the score is a ratio. Provider errors are recorded as results,
not raised — a model that 500s under load is answering the question too (#50).

No database and no network beyond the model call. The campaign is a stub carrying
only the attributes the prompt builder reads, so the prompt under evaluation stays
the production one as it evolves.

Usage:
  cd backend
  uv run python scripts/model_smoke.py --provider openrouter \
      --model deepseek/deepseek-chat --model qwen/qwen-2.5-72b-instruct
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.prompts.dm import build_dm_system_prompt  # noqa: E402
from app.ai.providers.base import get_provider  # noqa: E402
from app.ai.tools.dm_tools import get_tool_schemas  # noqa: E402
from app.ai.tools.tool_groups import resolve_active_tools_from_state  # noqa: E402

# --- fixtures ---------------------------------------------------------------

SHRINE_STATE: dict = {
    "meta": {"current_location": "shrine"},
    "time_of_day": "alba",
    "weather": "nebbia bassa",
    "locations": {
        "shrine": {
            "description": "Un cerchio di menhir coperti di muschio. Un corvo osserva.",
            "connections": ["sentiero nel bosco"],
        }
    },
    "npcs": {
        "3f9a-lyra": {
            "name": "Lyra",
            "lifecycle": "alive",
            "location": "shrine",
            "condition": "una vecchia cicatrice sull'avambraccio",
            "traits": {
                "role": "ranger che sorveglia il santuario",
                "appearance": "occhi verde scuro, mantello logoro",
            },
            "psychology": {"trust": -20, "fear": 5},
        }
    },
}

CHAR_DATA: dict = {
    "name": "TomProva",
    "hp": 14,
    "max_hp": 14,
    "dex": 14,
    "str": 12,
    "inventory": ["una coperta di lana grezza"],
}

NPC_LINE = "Sei al Santuario della Prima Luce. Io resto qui, e' il mio dovere."


def _campaign() -> SimpleNamespace:
    """Only the attributes build_dm_system_prompt actually reads."""
    return SimpleNamespace(
        world_state=SHRINE_STATE,
        character_data=CHAR_DATA,
        quests={},
        death_mode="cronista",
        world_baseline={},
        persona_xml=None,
        persona_preset=None,
    )


# --- scenarios --------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    why: str
    action: str
    must_call: set[str] = field(default_factory=set)
    must_not_call: set[str] = field(default_factory=set)
    history: list[dict] = field(default_factory=list)
    forbid_quoted_dialogue: bool = False


_FOLLOWUP_HISTORY: list[dict] = [
    {"role": "user", "content": "chi sei tu? chi sono io? non ricordo nulla..."},
    {
        "role": "assistant",
        "content": "Il corvo tace. La ranger ti misura con lo sguardo.",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "invoke_npc",
                    "arguments": '{"name": "Lyra", "context": "il giocatore chiede chi sia"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "invoke_npc",
        "content": f'{{"npc": "Lyra", "dialogue": "{NPC_LINE}", "action": "ti lancia una coperta"}}',
    },
]

SCENARIOS: list[Scenario] = [
    Scenario(
        name="npc_speaks",
        why="dm.yaml:31 — a present NPC answering MUST go through invoke_npc (#52)",
        action="chi sei tu? chi sono io? non ricordo nulla...",
        must_call={"invoke_npc"},
    ),
    Scenario(
        name="npc_followup",
        why="dm.yaml:42 — after an invoke_npc result, do not restate the line (#53)",
        action="",
        history=_FOLLOWUP_HISTORY,
        must_not_call={"invoke_npc"},
        forbid_quoted_dialogue=True,
    ),
    Scenario(
        name="item_pickup",
        why="dm.yaml:30 — acquiring an object MUST call add_item",
        action="raccolgo il coltello arrugginito ai piedi del menhir",
        must_call={"add_item"},
    ),
    Scenario(
        name="passive_turn",
        why="dm.yaml:20/35 — a passive turn still advances the clock",
        action="aspetto",
        must_call={"advance_time"},
    ),
]

# --- checks -----------------------------------------------------------------

_IT_WORDS = {
    "che",
    "non",
    "di",
    "il",
    "la",
    "un",
    "una",
    "sono",
    "per",
    "con",
    "del",
    "nel",
    "ti",
    "si",
    "e'",
    "sul",
    "come",
    "tuo",
    "tua",
    "quando",
}
_EN_WORDS = {
    "the",
    "you",
    "and",
    "of",
    "to",
    "is",
    "your",
    "with",
    "from",
    "that",
    "into",
    "his",
    "her",
    "they",
    "for",
    "at",
    "on",
    "as",
    "it",
    "are",
}

_MARKDOWN = re.compile(r"\*\*|^#{1,6}\s|^\s*[-*]\s", re.MULTILINE)
_MECHANICS = re.compile(
    r"\bDC\s*\d|\bd20\b|\b(?:Mood|Time|Roll|Suggested actions|Tool Call)\s*:", re.IGNORECASE
)
_QUOTED = re.compile(r"[«\"“][^»\"”]{12,}[»\"”]")


def _language(text: str) -> str:
    words = re.findall(r"[a-zà-ù']+", text.lower())
    it = sum(w in _IT_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    if it == en:
        return "?"
    return "it" if it > en else "en"


def _grade(scenario: Scenario, text: str, called: set[str]) -> list[str]:
    """Returns the list of failed check names — empty means a clean pass."""
    failed = []
    missing = scenario.must_call - called
    if missing:
        failed.append(f"missing:{','.join(sorted(missing))}")
    forbidden = scenario.must_not_call & called
    if forbidden:
        failed.append(f"forbidden:{','.join(sorted(forbidden))}")
    if text.strip() and _language(text) == "en":
        failed.append("language:en")
    if _MARKDOWN.search(text):
        failed.append("markdown")
    if _MECHANICS.search(text):
        failed.append("mechanics-leak")
    # Proxy, not proof: a long quoted span after an NPC result is a restatement.
    if scenario.forbid_quoted_dialogue and _QUOTED.search(text):
        failed.append("restates-npc")
    return failed


# --- runner -----------------------------------------------------------------


@dataclass
class Result:
    scenario: str
    failed: list[str]
    seconds: float
    error: str = ""


async def _run_once(provider_name: str, model: str, scenario: Scenario) -> Result:
    system_prompt = build_dm_system_prompt(_campaign())  # type: ignore[arg-type]
    tools = get_tool_schemas(allowed=resolve_active_tools_from_state(SHRINE_STATE))
    messages = list(scenario.history) or [{"role": "user", "content": scenario.action}]

    started = time.monotonic()
    try:
        response = await get_provider(provider_name).generate_with_tools(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            model=model,
            temperature=0.8,
            max_tokens=1200,
        )
    except Exception as exc:  # a failing provider is a result, not a crash (#50)
        return Result(scenario.name, ["error"], time.monotonic() - started, str(exc)[:120])

    called = {tc.name for tc in response.tool_calls}
    return Result(
        scenario.name,
        _grade(scenario, response.text or "", called),
        time.monotonic() - started,
    )


async def _run_model(provider: str, model: str, runs: int) -> list[Result]:
    results = []
    for scenario in SCENARIOS:
        # Sequential on purpose: the candidates are free-tier, where concurrent
        # calls buy you a rate limit instead of a measurement.
        batch = [await _run_once(provider, model, scenario) for _ in range(runs)]
        results.extend(batch)
        passed = sum(not r.failed for r in batch)
        print(f"    {scenario.name:<16} {passed}/{runs}")
    return results


def _report(model: str, results: list[Result], runs: int) -> None:
    print(f"\n=== {model} ===")
    for scenario in SCENARIOS:
        rows = [r for r in results if r.scenario == scenario.name]
        passed = sum(not r.failed for r in rows)
        reasons = sorted({f for r in rows for f in r.failed})
        avg = sum(r.seconds for r in rows) / max(len(rows), 1)
        detail = f"  {', '.join(reasons)}" if reasons else ""
        print(f"  {scenario.name:<16} {passed}/{runs}  {avg:5.1f}s{detail}")
        print(f"      {scenario.why}")
    errors = [r.error for r in results if r.error]
    if errors:
        print(f"  provider errors ({len(errors)}): {errors[0]}")
    total = sum(not r.failed for r in results)
    print(f"  TOTAL {total}/{len(results)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", action="append", required=True, dest="models")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    all_results: list[tuple[str, list[Result]]] = []
    for model in args.models:
        print(f"\nrunning {model} ({args.runs} runs x {len(SCENARIOS)} scenarios)")
        all_results.append((model, await _run_model(args.provider, model, args.runs)))

    for model, results in all_results:
        _report(model, results, args.runs)


if __name__ == "__main__":
    asyncio.run(main())
