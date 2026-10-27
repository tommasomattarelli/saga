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
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scenario as scenarios  # noqa: E402
from actor_probe import run_actor  # noqa: E402
from ledger import Attempt, BudgetExhaustedError, RequestLedger  # noqa: E402
from probes import PROBES, grade  # noqa: E402

from app.ai.prompts.dm import build_dm_system_prompt  # noqa: E402
from app.ai.providers.base import get_provider  # noqa: E402
from app.ai.router import get_instance_default  # noqa: E402
from app.ai.tools.dm_tools import get_tool_schemas  # noqa: E402
from app.ai.tools.tool_groups import resolve_active_tools_from_state  # noqa: E402


@dataclass
class Result:
    scenario: str
    probe: str
    failed: list[str]
    seconds: float
    error: str = ""


def _record(ledger: RequestLedger | None, attempt: Attempt, result: Result) -> None:
    if ledger is None:
        return
    attempt.status = "error" if result.error else "ok"
    attempt.failed = result.failed
    attempt.seconds = result.seconds
    attempt.error = result.error
    ledger.record(attempt)


async def _run_once(
    provider: str,
    model: str,
    sc: scenarios.Scenario,
    probe_name: str,
    run: int,
    ledger: RequestLedger | None,
) -> Result:
    probe = next(p for p in PROBES if p.name == probe_name)
    attempt = Attempt(
        key=f"{model}|{sc.name}|{probe_name}|{run}",
        scenario=sc.name,
        probe=probe_name,
        run=run,
    )
    if ledger:
        ledger.reserve(attempt)

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
            max_tokens=get_instance_default().max_tokens,
        )
    except Exception as exc:  # a failing provider is a result, not a crash (#50)
        result = Result(sc.name, probe_name, ["error"], time.monotonic() - started, str(exc)[:160])
        _record(ledger, attempt, result)
        return result

    called = {tc.name for tc in response.tool_calls}
    result = Result(
        sc.name,
        probe_name,
        grade(probe, response.text or "", called, expect_language=sc.language),
        time.monotonic() - started,
    )
    _record(ledger, attempt, result)
    return result


async def _run_actor_once(
    provider: str,
    model: str,
    sc: scenarios.Scenario,
    run: int,
    ledger: RequestLedger | None,
) -> Result:
    attempt = Attempt(
        key=f"{model}|{sc.name}|actor_language|{run}",
        scenario=sc.name,
        probe="actor_language",
        run=run,
    )
    if ledger:
        ledger.reserve(attempt)

    stimulus = sc.stimuli.get("npc_speaks")
    if stimulus is None:
        result = Result(sc.name, "actor_language", ["no-stimulus"], 0.0)
    else:
        started = time.monotonic()
        outcome = await run_actor(
            provider_name=provider,
            model=model,
            max_tokens=get_instance_default().max_tokens,
            scenario=sc,
            player_action=stimulus.player,
            dm_narration=sc.history[-1]["content"] if sc.history else "",
        )
        result = Result(
            sc.name, "actor_language", outcome.failed, time.monotonic() - started, outcome.error
        )
    _record(ledger, attempt, result)
    return result


async def _run_scenario(
    provider: str,
    model: str,
    sc: scenarios.Scenario,
    runs: int,
    ledger: RequestLedger | None,
    selected: set[str] | None = None,
) -> list[Result]:
    results: list[Result] = []
    for probe in PROBES:
        if probe.name in sc.unsupported:
            continue
        if selected is not None and probe.name not in selected:
            continue
        # Sequential on purpose: the candidates are free-tier, where concurrent
        # calls buy you a rate limit instead of a measurement.
        batch: list[Result] = []
        for run in range(runs):
            if ledger and ledger.completed(f"{model}|{sc.name}|{probe.name}|{run}"):
                continue
            batch.append(await _run_once(provider, model, sc, probe.name, run, ledger))
        results.extend(batch)
        resumed = " (resumed)" if len(batch) < runs else ""
        print(f"    {probe.name:<16} {sum(not r.failed for r in batch)}/{len(batch)}{resumed}")
    return results


REPORT_PROBES = [
    *PROBES,
    SimpleNamespace(
        name="actor_language",
        why="real actor call — the NPC prompt's own language, not the DM's (#51)",
    ),
]


def _ratio(results: list[Result], scenario: str, probe: str) -> tuple[int, int]:
    rows = [r for r in results if r.scenario == scenario and r.probe == probe]
    return sum(not r.failed for r in rows), len(rows)


def _report(
    model: str,
    results: list[Result],
    scenario_names: list[str],
    ledger: RequestLedger | None = None,
) -> None:
    print(f"\n=== {model} ===")
    width = max(len(n) for n in scenario_names) + 2
    header = "  probe".ljust(20) + "".join(n.ljust(width) for n in scenario_names)
    print(header + ("Δ" if len(scenario_names) > 1 else ""))

    for probe in REPORT_PROBES:
        cells, rates = [], []
        for name in scenario_names:
            passed, total = _ratio(results, name, probe.name)
            if total:
                rates.append(passed / total)
                cells.append(f"{passed}/{total}".ljust(width))
            else:
                rates.append(None)
                cells.append("n/a".ljust(width))
        delta = ""
        if len(rates) > 1 and rates[0] is not None and rates[-1] is not None:
            delta = f"{(rates[-1] - rates[0]) * 100:+.0f}%"
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
    if ledger:
        budget = f"/{ledger.budget}" if ledger.budget is not None else ""
        print(f"  requests spent: {ledger.spent}{budget}")
        if interrupted := ledger.interrupted():
            print(f"  interrupted attempts: {len(interrupted)} (counted, re-run with --resume)")


def _code_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _write_results(path: str | None, model: str, results: list[Result]) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "model": model,
                "commit": _code_commit(),
                "results": [result.__dict__ for result in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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
        "--probe",
        action="append",
        dest="probes",
        help="only these probes (repeatable); default is every supported probe",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="assemble every prompt and report its size, calling no model",
    )
    parser.add_argument(
        "--ledger", help="JSONL request ledger; live calls are unaccounted without it"
    )
    parser.add_argument("--budget", type=int, help="request budget for this ledger")
    parser.add_argument(
        "--resume", action="store_true", help="skip attempts already in the ledger"
    )
    parser.add_argument("--out", help="write machine-readable results here")
    parser.add_argument(
        "--actor", action="store_true", help="also run one real actor call per scenario (#51)"
    )
    args = parser.parse_args()

    names = args.scenarios or ["empty"]
    selected = set(args.probes) if args.probes else None
    loaded = [scenarios.load(n) for n in names]
    for sc in loaded:
        if not sc.derived:
            print(
                f"WARNING: scenario '{sc.name}' is not derived — its summaries and recall "
                "are empty, so it does not yet saturate the context it was built for."
            )
        if sc.reconstructed:
            print(f"NOTE: scenario '{sc.name}' is reconstructed, not the historical state.")
        if sc.unsupported:
            unsupported = ", ".join(sorted(sc.unsupported))
            print(f"NOTE: scenario '{sc.name}' cannot ask: {unsupported} (reported n/a)")

    if args.dry_run:
        for sc in loaded:
            tools = get_tool_schemas(
                allowed=resolve_active_tools_from_state(sc.campaign.world_state)
            )
            for probe in PROBES:
                if probe.name in sc.unsupported:
                    continue
                # Recall is per-probe, so the system prompt is too.
                system_prompt = build_dm_system_prompt(
                    sc.campaign,  # type: ignore[arg-type]
                    summary_context=sc.summary_context,
                    global_summary=sc.global_summary,
                    recalled_memories=sc.recalled_memories(probe.name),
                )
                history = sum(len(str(m.get("content") or "")) for m in sc.messages(probe.name))
                print(
                    f"{sc.name:<18} {probe.name:<16} system {len(system_prompt):>6} "
                    f"+ history {history:>6} = {len(system_prompt) + history:>6} chars"
                    f"  | {len(tools)} tools, lang {sc.language}"
                )
        return

    ledger = RequestLedger(args.ledger, budget=args.budget) if args.ledger else None
    if ledger is None:
        print("WARNING: no --ledger — these calls are not accounted.")
    elif ledger.spent and not args.resume:
        raise SystemExit(
            f"{args.ledger} already has {ledger.spent} attempts; pass --resume or a new path"
        )

    for model in args.models:
        collected: list[Result] = []
        try:
            for sc in loaded:
                print(f"\n{model} / {sc.name} ({args.runs} runs x {len(PROBES)} probes)")
                collected.extend(
                    await _run_scenario(
                        args.provider, model, sc, args.runs, ledger, selected=selected
                    )
                )
                wants_actor = args.actor
                if wants_actor and "npc_speaks" in sc.stimuli:
                    for run in range(args.runs):
                        if ledger and ledger.completed(f"{model}|{sc.name}|actor_language|{run}"):
                            continue
                        collected.append(
                            await _run_actor_once(args.provider, model, sc, run, ledger)
                        )
        except BudgetExhaustedError as exc:
            print(f"\nSTOP: {exc}")
            results = (
                [
                    Result(a.scenario, a.probe, a.failed, a.seconds, a.error)
                    for a in ledger.results()
                ]
                if ledger
                else collected
            )
            _report(model, results, names, ledger)
            _write_results(args.out, model, results)
            raise SystemExit(3) from exc

        results = (
            [Result(a.scenario, a.probe, a.failed, a.seconds, a.error) for a in ledger.results()]
            if ledger
            else collected
        )
        _report(model, results, names, ledger)
        _write_results(args.out, model, results)


if __name__ == "__main__":
    asyncio.run(main())
