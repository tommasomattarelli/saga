"""Final ADR 0017 foreground suite. Dry-run never contacts a provider or catalog."""

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogue_cases import CASES, scenario_for  # noqa: E402
from dialogue_plan import MODELS, manifest, trial_key  # noqa: E402
from dialogue_requests import SuiteProvider  # noqa: E402
from dialogue_trial import run_case  # noqa: E402
from ledger import RequestLedger  # noqa: E402
from live_calls import resolve_eval_generation, validate_eval_models  # noqa: E402
from usage_report import usage_csv, usage_markdown  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def json_default(value: object) -> object:
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError("Evaluation evidence contains a non-JSON value.")


def read_evidence(path: Path) -> tuple[dict[str, dict], set[str]]:
    completed: dict[str, dict] = {}
    latest: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            latest[row["key"]] = row["event"]
            if row["event"] == "result":
                completed[row["key"]] = row
    return completed, {key for key, event in latest.items() if event == "started"}


def append_evidence(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=json_default) + "\n")


def write_inventory(
    path: Path, plan: dict, completed: dict[str, dict], ledger: RequestLedger
) -> None:
    pending = [
        {"case": case.name, "model": model, "run": run}
        for run in range(plan["runs_per_model_case"])
        for case in (next(c for c in CASES if c.name == name) for name in plan["cases"])
        for model in plan["models"]
        if trial_key(plan, case.name, model, run) not in completed
        or completed[trial_key(plan, case.name, model, run)].get("retryable")
        or completed[trial_key(plan, case.name, model, run)].get("trial_status")
        in {"request_budget_stopped", "provider_paused"}
    ]
    result = {
        "suite": plan["suite"],
        "source_hash": plan["source_hash"],
        "recorded_trials": len(completed),
        "target_trials": plan["trials"],
        "all_trials_recorded": not pending,
        "acceptance": "pending complete-suite owner review",
        "daily_spent": ledger.spent,
        "daily_remaining": ledger.remaining,
        "pending": pending,
        "retryable": [
            {"case": row["case"], "model": row["model"], "run": row["run"]}
            for row in completed.values()
            if row.get("retryable")
        ],
    }
    path.with_suffix(".summary.json").write_text(json.dumps(result, indent=2))
    ledger_paths = {ledger.path.resolve()}
    ledger_paths.update(
        Path(row["ledger"]).resolve() for row in completed.values() if row.get("ledger")
    )
    if path.exists():
        for text in path.read_text().splitlines():
            row = json.loads(text)
            if row.get("ledger"):
                ledger_paths.add(Path(row["ledger"]).resolve())
    rows = [
        {**asdict(attempt), "ledger": str(ledger_path)}
        for ledger_path in sorted(ledger_paths)
        if ledger_path.exists()
        for attempt in RequestLedger(ledger_path).results()
    ]
    path.with_suffix(".usage.csv").write_text(usage_csv(rows), encoding="utf-8")
    path.with_suffix(".usage.md").write_text(usage_markdown(rows), encoding="utf-8")
    print(
        f"Recorded {len(completed)}/{plan['trials']} trials; daily requests {ledger.spent}/{ledger.budget}."
    )
    print(f"Retryable failures: {len(result['retryable'])}.")
    print("No acceptance judgment is made by this runner.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--suite", default="adr-0017-final-v2")
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--cases", nargs="+", default=[case.name for case in CASES])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--allow-paid-model", action="append", default=[], metavar="MODEL_ID")
    parser.add_argument("--user")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument(
        "--budget", type=int, help="remaining authorized requests for this ledger/day"
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        plan = manifest(args.models, args.cases, args.runs, args.suite, set(args.allow_paid_model))
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if not all([args.user, args.ledger, args.results, args.budget]) or args.budget < 1:
        parser.error("Live runs need --user, --ledger, --results and a positive --budget.")
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            ".",
            ":!scratch",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    if dirty:
        parser.error("Commit the tested tree before a live suite; scratch is excluded.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    completed, interrupted = read_evidence(args.results)
    ledger = RequestLedger(args.ledger, budget=args.budget)
    if interrupted or ledger.interrupted():
        parser.error(
            "Interrupted evidence requires owner review; it is never retried automatically."
        )
    if (completed or ledger.spent) and not args.resume:
        parser.error("Existing evidence requires --resume.")
    manifest_path = args.results.with_suffix(".manifest.json")
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != plan:
        parser.error("Code/scenario/model/config identity changed; keep prior evidence immutable.")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(plan, indent=2))
    await validate_eval_models(plan["models"], set(args.allow_paid_model))
    owner = uuid.UUID(args.user)
    paid_models = set(args.allow_paid_model)
    generations = {
        model: await resolve_eval_generation(owner, model, allow_paid=model in paid_models)
        for model in plan["models"]
    }
    try:
        for run in range(plan["runs_per_model_case"]):
            for case in (next(c for c in CASES if c.name == name) for name in plan["cases"]):
                for model in plan["models"]:
                    key = trial_key(plan, case.name, model, run)
                    recorded = completed.get(key)
                    retry = args.resume and recorded is not None and recorded.get("retryable")
                    unstarted = (
                        recorded is not None
                        and recorded.get("requests") == 0
                        and recorded.get("trial_status") == "request_budget_stopped"
                    )
                    if recorded is not None and not retry and not unstarted:
                        continue
                    if retry and any(
                        attempt.key.startswith(f"{key}|request-") for attempt in ledger.results()
                    ):
                        parser.error(
                            "Retrying a failed trial requires a fresh ledger; prior attempts remain immutable."
                        )
                    if ledger.remaining is not None and ledger.remaining < case.ceiling:
                        stopped = {
                            "event": "result",
                            "key": key,
                            "case": case.name,
                            "model": model,
                            "run": run,
                            "requests": 0,
                            "data": {},
                            "trial_status": "request_budget_stopped",
                            "observed_checks": [],
                            "retryable": False,
                        }
                        append_evidence(args.results, stopped)
                        completed[key] = stopped
                        return
                    provider, config = generations[model]
                    row = {
                        "event": "started",
                        "key": key,
                        "case": case.name,
                        "model": model,
                        "run": run,
                        "commit": commit,
                        "source_hash": plan["source_hash"],
                        "ledger": str(ledger.path.resolve()),
                    }
                    append_evidence(args.results, row)
                    trace = SuiteProvider(
                        provider,
                        ledger,
                        key=key,
                        case=case.name,
                        model=model,
                        run=run,
                        commit=commit,
                        ceiling=case.ceiling,
                        checkpoint=plan["suite"],
                    )
                    try:
                        data, failed = await run_case(
                            case.name, scenario_for(case.name), trace, config, owner
                        )
                    except Exception:
                        data, failed = {}, ["foreground-run-incomplete"]
                    if trace.errors:
                        failed.append("provider-error")
                    if trace.exhausted:
                        failed.append("evaluation-request-cap")
                    row.update(
                        event="result",
                        requests=trace.count,
                        data=data,
                        observed_checks=(
                            [] if trace.exhausted or trace.paused else sorted(set(failed))
                        ),
                        trial_status=(
                            "request_budget_stopped"
                            if trace.exhausted
                            else "provider_paused"
                            if trace.paused
                            else "provider_error"
                            if trace.errors
                            else "evaluation_error"
                            if "foreground-run-incomplete" in failed
                            else "model_result"
                        ),
                        provider_error=trace.errors,
                        request_cap_reached=trace.exhausted,
                        retryable=bool(
                            {"foreground-run-incomplete", "provider-error"} & set(failed)
                        )
                        and not trace.exhausted,
                    )
                    append_evidence(args.results, row)
                    completed[key] = row
                    print(
                        f"Recorded {case.name}/{model}/{run}: {trace.count} requests.", flush=True
                    )
                    if trace.paused:
                        print("Provider quota/rate limit: saved evidence; stopping without retry.")
                        return
    finally:
        write_inventory(args.results, plan, completed, ledger)


if __name__ == "__main__":
    asyncio.run(main())
