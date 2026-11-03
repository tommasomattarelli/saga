"""Final ADR 0017 foreground suite. Dry-run never contacts a provider or catalog."""

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialogue_cases import CASES  # noqa: E402
from dialogue_evidence import append_evidence, read_evidence, write_inventory  # noqa: E402, F401
from dialogue_execution import run_models  # noqa: E402
from dialogue_plan import MODELS, manifest, trial_key  # noqa: E402, F401
from dialogue_trial import run_case  # noqa: E402
from ledger import RequestLedger  # noqa: E402
from live_calls import resolve_eval_generation, validate_eval_models  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


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
        "--budget",
        type=int,
        help="total authorized request cap for this ledger, including prior attempts",
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
        ["git", "status", "--porcelain", "--", ".", ":!scratch"],
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
    for key, row in completed.items():
        if row.get("retryable") and any(
            attempt.key.startswith(f"{key}|request-") for attempt in ledger.results()
        ):
            parser.error(
                "Retrying a failed trial requires a fresh ledger; prior attempts remain immutable."
            )
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
    timing: dict = {}
    try:
        await run_models(
            plan, completed, ledger, args.results, generations, owner, commit, run_case, timing
        )
    finally:
        write_inventory(args.results, plan, completed, ledger, timing)


if __name__ == "__main__":
    asyncio.run(main())
