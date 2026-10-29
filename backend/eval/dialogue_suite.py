"""Final ADR 0017 foreground suite. Dry-run never contacts a provider or catalog."""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogue_cases import CASES, scenario_for  # noqa: E402
from dialogue_requests import SuiteProvider  # noqa: E402
from dialogue_trial import run_case  # noqa: E402
from ledger import RequestLedger  # noqa: E402
from live_calls import resolve_eval_generation, validate_free_models  # noqa: E402

from app.ai.router import get_gameplay_config, get_instance_default  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MODELS = ("nvidia/nemotron-3-ultra-550b-a55b:free", "nvidia/nemotron-3.5-super-vl:free")


def json_default(value: object) -> object:
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError("Evaluation evidence contains a non-JSON value.")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=json_default).encode()
    ).hexdigest()


def source_hash() -> str:
    names = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "backend/app",
                "backend/eval",
                "frontend/src",
                "saga.config.yaml",
            ],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    checksum = hashlib.sha256()
    for name in sorted(filter(None, names)):
        path = ROOT / name
        checksum.update(name.encode() + b"\0")
        checksum.update(path.read_bytes() if path.exists() else b"<deleted>")
    return checksum.hexdigest()


def manifest() -> dict:
    scenarios = {case.name: scenario_for(case.name) for case in CASES}
    return {
        "suite": "adr-0017-final-v1",
        "source_hash": source_hash(),
        "models": list(MODELS),
        "runs_per_model_case": 3,
        "trials": len(CASES) * len(MODELS) * 3,
        "nominal_requests": 66,
        "request_ceiling": sum(c.ceiling for c in CASES) * len(MODELS) * 3,
        "pipeline_dm_cap": 3,
        "max_output_tokens": get_instance_default().max_tokens,
        "gameplay": asdict(get_gameplay_config()),
        "cases": {
            name: {
                "ceiling": next(c.ceiling for c in CASES if c.name == name),
                "scenario_hash": digest(
                    {
                        "campaign": vars(sc.campaign),
                        "history": sc.history,
                        "summary": sc.summary_context,
                        "global": sc.global_summary,
                        "recall": sc.recall,
                        "stimuli": {key: asdict(value) for key, value in sc.stimuli.items()},
                    }
                ),
            }
            for name, sc in scenarios.items()
        },
    }


def trial_key(plan: dict, case: str, model: str, run: int) -> str:
    return digest([plan, case, model, run])


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
        for run in range(3)
        for case in CASES
        for model in MODELS
        if trial_key(plan, case.name, model, run) not in completed
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
    print(
        f"Recorded {len(completed)}/{plan['trials']} trials; daily requests {ledger.spent}/{ledger.budget}."
    )
    print(f"Retryable failures: {len(result['retryable'])}.")
    print("No acceptance judgment is made by this runner.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument(
        "--budget", type=int, help="remaining authorized requests for this ledger/day"
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    plan = manifest()
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
    await validate_free_models(list(MODELS))
    owner = uuid.UUID(args.user)
    generations = {model: await resolve_eval_generation(owner, model) for model in MODELS}
    try:
        for run in range(3):
            for case in CASES:
                for model in MODELS:
                    key = trial_key(plan, case.name, model, run)
                    recorded = completed.get(key)
                    retry = args.resume and recorded is not None and recorded.get("retryable")
                    if (recorded is not None and not retry) or (
                        ledger.remaining is not None and ledger.remaining < case.ceiling
                    ):
                        continue
                    provider, config = generations[model]
                    row = {
                        "event": "started",
                        "key": key,
                        "case": case.name,
                        "model": model,
                        "run": run,
                        "commit": commit,
                        "source_hash": plan["source_hash"],
                        "ledger": str(args.ledger),
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
                        observed_checks=sorted(set(failed)),
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
