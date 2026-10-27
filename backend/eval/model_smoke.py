"""Quota-bounded smoke probes; --dry-run makes no provider calls.

Live runs require an owner's personal AI profile, a daily shared ledger and an
explicit checkpoint. These probes measure foreground compliance, not a persisted
turn; integration tests cover tool execution and state/persistence contracts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import Attempt, BudgetExhaustedError, RequestLedger  # noqa: E402
from live_calls import (  # noqa: E402
    EvaluationPausedError,
    dm_request,
    resolve_eval_generation,
    run_trial,  # noqa: E402
    validate_free_models,
)
from probes import PROBES_BY_NAME  # noqa: E402
from scenario import load  # noqa: E402

from app.ai.router import get_instance_default  # noqa: E402


def sample_identity(row: Attempt) -> tuple[str, str]:
    return row.commit, row.key.rsplit("|", 1)[-1]


def report(ledger: RequestLedger, checkpoint: str, models: list[str], out: str | None) -> None:
    rows = [
        row for row in ledger.results() if row.checkpoint == checkpoint and row.model in models
    ]
    groups = sorted({(row.model, row.scenario, row.probe, sample_identity(row)) for row in rows})
    for model, scenario, probe, identity in groups:
        trials = [
            row
            for row in rows
            if (row.model, row.scenario, row.probe, sample_identity(row))
            == (model, scenario, probe, identity)
        ]
        passed = sum(not row.failed for row in trials)
        errors = sum(row.status == "error" for row in trials)
        commit, digest = identity
        print(
            f"{model} / {scenario} / {probe} [{commit[:7]}:{digest[:8]}]: {passed}/{len(trials)}; provider errors={errors}"
        )
    for model in models:
        model_rows = [row for row in rows if row.model == model]
        scenarios = list(dict.fromkeys(row.scenario for row in model_rows))
        if len(scenarios) < 2:
            continue
        for probe in sorted({row.probe for row in model_rows}):
            first = [
                row for row in model_rows if row.scenario == scenarios[0] and row.probe == probe
            ]
            last = [
                row for row in model_rows if row.scenario == scenarios[-1] and row.probe == probe
            ]
            if not first or not last:
                continue
            if any(len({sample_identity(row) for row in sample}) != 1 for sample in (first, last)):
                continue
            if first[0].commit != last[0].commit:
                continue
            if first[0].request.get("max_tokens") != last[0].request.get("max_tokens"):
                continue
            delta = sum(not row.failed for row in last) / len(last) - sum(
                not row.failed for row in first
            ) / len(first)
            print(f"Δ {model}/{probe}: {scenarios[-1]} vs {scenarios[0]} {delta:+.0%}")
    print(f"Daily ledger: {ledger.spent}/{ledger.budget} reserved; remaining={ledger.remaining}")
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "checkpoint": checkpoint,
                    "spent": ledger.spent,
                    "remaining": ledger.remaining,
                    "results": [asdict(row) for row in rows],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", required=True, dest="models")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--probe", action="append", dest="probes")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--actor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--user", help="owner UUID; profile and credential are resolved without changing settings"
    )
    parser.add_argument("--provider", default="openrouter", choices=["openrouter"])
    parser.add_argument("--ledger")
    parser.add_argument("--budget", type=int)
    parser.add_argument("--checkpoint")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    selected = args.probes or list(PROBES_BY_NAME)
    if set(selected) - (set(PROBES_BY_NAME) | {"actor_language"}):
        parser.error("Unknown probe")
    if args.actor and "actor_language" not in selected:
        selected.append("actor_language")
    scenarios = [load(name) for name in (args.scenarios or ["empty"])]
    for sc in scenarios:
        print(f"{sc.name}: reconstructed={sc.reconstructed}, unsupported={sorted(sc.unsupported)}")
    if args.dry_run:
        for sc in scenarios:
            for probe in selected:
                if probe == "actor_language" or probe in sc.unsupported:
                    continue
                request = dm_request(sc, probe, get_instance_default())
                print(
                    f"{sc.name} / {probe}: {len(json.dumps(request))} request chars; language={sc.language}"
                )
        return
    if not all([args.user, args.ledger, args.budget, args.checkpoint]):
        parser.error("Live runs require --user, --ledger, --budget and --checkpoint")
    ledger = RequestLedger(args.ledger, budget=args.budget)
    if ledger.spent and not args.resume:
        parser.error("Ledger already contains calls; use --resume")
    await validate_free_models(args.models)
    try:
        for model in args.models:
            generation = await resolve_eval_generation(uuid.UUID(args.user), model)
            for sc in scenarios:
                for probe in selected:
                    if probe != "actor_language" and probe in sc.unsupported:
                        continue
                    for run in range(args.runs):
                        result = await run_trial(
                            generation, sc, probe, run, ledger, checkpoint=args.checkpoint
                        )
                        if result:
                            print(
                                f"{sc.name}/{probe}/{run}: {result.failed or 'pass'}", flush=True
                            )
    except (BudgetExhaustedError, EvaluationPausedError) as exc:
        print(f"PAUSED: {exc}")
        report(ledger, args.checkpoint, args.models, args.out)
        raise SystemExit(3) from exc
    report(ledger, args.checkpoint, args.models, args.out)


if __name__ == "__main__":
    asyncio.run(main())
