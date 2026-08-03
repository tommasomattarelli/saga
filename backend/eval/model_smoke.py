"""Model smoke harness — does a candidate model honour the DM's tool obligations?

Not a test suite: an evaluation tool. It drives SAGA's *real* DM system prompt and
*real* tool schemas against a candidate model and scores the behaviours the
v0.2.0-beta.1 playtest found broken — invoke_npc skipped (#52), NPC output
paraphrased (#53), narration language drifting (#51).

Compliance is stochastic, so a single sample says nothing: every probe runs
--runs times and the score is a ratio. Provider errors are recorded as results,
not raised — a model that fails under load is answering the question too (#50).

Pass --scenario more than once to get the number that actually matters. The
absolute score of a model on one context is close to meaningless; the **drop**
between an empty context and a saturated one is the thing prompt work has to
improve, and it is printed as a Δ column.

Usage:
  cd backend
  uv run python eval/model_smoke.py --model MODEL
  uv run python eval/model_smoke.py --model MODEL --scenario empty --scenario gold
  uv run python eval/model_smoke.py --model MODEL --scenario gold --scenario bloat --runs 5
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scenario as scenarios  # noqa: E402
from probes import PROBES, grade  # noqa: E402

from app.ai.prompts.dm import build_dm_system_prompt  # noqa: E402
from app.ai.providers.base import get_provider  # noqa: E402
from app.ai.tools.dm_tools import get_tool_schemas  # noqa: E402
from app.ai.tools.tool_groups import resolve_active_tools_from_state  # noqa: E402


@dataclass
class Result:
    scenario: str
    probe: str
    failed: list[str]
    seconds: float
    error: str = ""


async def _run_once(provider: str, model: str, sc: scenarios.Scenario, probe_name: str) -> Result:
    probe = next(p for p in PROBES if p.name == probe_name)
    system_prompt = build_dm_system_prompt(
        sc.campaign,  # type: ignore[arg-type]
        summary_context=sc.summary_context,
        global_summary=sc.global_summary,
        recalled_memories=sc.recalled_memories(probe_name),
    )
    tools = get_tool_schemas(allowed=resolve_active_tools_from_state(sc.campaign.world_state))

    started = time.monotonic()
    try:
        response = await get_provider(provider).generate_with_tools(
            system_prompt=system_prompt,
            messages=sc.messages(probe_name),
            tools=tools,
            model=model,
            temperature=0.8,
            max_tokens=1200,
        )
    except Exception as exc:  # a failing provider is a result, not a crash (#50)
        return Result(sc.name, probe_name, ["error"], time.monotonic() - started, str(exc)[:160])

    called = {tc.name for tc in response.tool_calls}
    return Result(
        sc.name,
        probe_name,
        grade(probe, response.text or "", called, expect_language=sc.language),
        time.monotonic() - started,
    )


async def _run_scenario(
    provider: str, model: str, sc: scenarios.Scenario, runs: int
) -> list[Result]:
    results: list[Result] = []
    for probe in PROBES:
        # Sequential on purpose: the candidates are free-tier, where concurrent
        # calls buy you a rate limit instead of a measurement.
        batch = [await _run_once(provider, model, sc, probe.name) for _ in range(runs)]
        results.extend(batch)
        print(f"    {probe.name:<16} {sum(not r.failed for r in batch)}/{runs}")
    return results


def _ratio(results: list[Result], scenario: str, probe: str) -> tuple[int, int]:
    rows = [r for r in results if r.scenario == scenario and r.probe == probe]
    return sum(not r.failed for r in rows), len(rows)


def _report(model: str, results: list[Result], scenario_names: list[str]) -> None:
    print(f"\n=== {model} ===")
    width = max(len(n) for n in scenario_names) + 2
    header = "  probe".ljust(20) + "".join(n.ljust(width) for n in scenario_names)
    print(header + ("Δ" if len(scenario_names) > 1 else ""))

    for probe in PROBES:
        cells, rates = [], []
        for name in scenario_names:
            passed, total = _ratio(results, name, probe.name)
            rates.append(passed / total if total else 0.0)
            cells.append(f"{passed}/{total}".ljust(width))
        delta = f"{(rates[-1] - rates[0]) * 100:+.0f}%" if len(rates) > 1 else ""
        print("  " + probe.name.ljust(18) + "".join(cells) + delta)
        # Per scenario, not pooled: the point of a comparison is seeing whether the
        # saturated context introduced a failure mode the empty one never showed.
        for name in scenario_names:
            reasons = sorted(
                {
                    f
                    for r in results
                    if r.probe == probe.name and r.scenario == name
                    for f in r.failed
                }
            )
            if reasons:
                print(" " * 20 + f"{name}: {', '.join(reasons)}")
        print(" " * 20 + probe.why)

    for name in scenario_names:
        rows = [r for r in results if r.scenario == name]
        errors = [r.error for r in rows if r.error]
        total = sum(not r.failed for r in rows)
        line = f"  TOTAL {name}: {total}/{len(rows)}"
        if errors:
            line += f"  ({len(errors)} provider errors)"
        print(line)
    if first := next((r.error for r in results if r.error), None):
        print(f"  first provider error: {first}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--model", action="append", required=True, dest="models")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="repeat to compare; the Δ column is last-vs-first (default: empty)",
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="assemble every prompt and report its size, calling no model",
    )
    args = parser.parse_args()

    names = args.scenarios or ["empty"]
    loaded = [scenarios.load(n) for n in names]
    for sc in loaded:
        if not sc.derived:
            print(
                f"WARNING: scenario '{sc.name}' is not derived — its summaries and recall "
                "are empty, so it does not yet saturate the context it was built for."
            )

    if args.dry_run:
        for sc in loaded:
            tools = get_tool_schemas(
                allowed=resolve_active_tools_from_state(sc.campaign.world_state)
            )
            for probe in PROBES:
                # Recall is per-probe, so the system prompt is too.
                system_prompt = build_dm_system_prompt(
                    sc.campaign,  # type: ignore[arg-type]
                    summary_context=sc.summary_context,
                    global_summary=sc.global_summary,
                    recalled_memories=sc.recalled_memories(probe.name),
                )
                history = sum(len(str(m.get("content") or "")) for m in sc.messages(probe.name))
                print(
                    f"{sc.name:<14} {probe.name:<16} system {len(system_prompt):>6} "
                    f"+ history {history:>6} = {len(system_prompt) + history:>6} chars"
                    f"  | {len(tools)} tools, lang {sc.language}"
                )
        return

    for model in args.models:
        results: list[Result] = []
        for sc in loaded:
            print(f"\n{model} / {sc.name} ({args.runs} runs x {len(PROBES)} probes)")
            results.extend(await _run_scenario(args.provider, model, sc, args.runs))
        _report(model, results, names)


if __name__ == "__main__":
    asyncio.run(main())
