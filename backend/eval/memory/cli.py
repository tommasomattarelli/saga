from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from eval.memory.plan import load_plan, prepare_plan, write_plan
from eval.memory.report import write_report


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare offline or explicitly run memory producer evaluation"
    )
    parser.add_argument(
        "--sources", type=Path, required=True, help="JSON list of BatchInput sources"
    )
    parser.add_argument("--facts-policy", type=Path, required=True)
    parser.add_argument("--global-policy", type=Path)
    parser.add_argument("--language", required=True)
    parser.add_argument("--session-scope", required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--allow-paid-model", action="append", default=[])
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--global-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--run", action="store_true", help="Execute live provider calls")
    execution.add_argument("--prepare", action="store_true", help="Write an offline manifest")
    execution.add_argument("--dry-run", action="store_true", help="Validate and prepare offline")
    parser.add_argument(
        "--authorized", action="store_true", help="Explicitly authorize live calls"
    )
    parser.add_argument("--user", type=UUID)
    args = parser.parse_args()
    sources = _json(args.sources)
    if not isinstance(sources, list):
        parser.error("--sources must contain a JSON list")
    facts = _json(args.facts_policy)
    global_policy = _json(args.global_policy) if args.global_policy else None
    if not isinstance(facts, dict) or (
        global_policy is not None and not isinstance(global_policy, dict)
    ):
        parser.error("policy files must contain JSON objects")
    candidate = prepare_plan(
        sources=sources,
        facts_policy=facts,
        global_policy=global_policy,
        language=args.language,
        models=args.model,
        repetitions=args.repetitions,
        global_count=args.global_count,
        session_scope=args.session_scope,
        paid_models=args.allow_paid_model,
    )
    if args.run:
        if not args.authorized or args.user is None:
            parser.error("--run requires --authorized and --user")
        plan = load_plan(args.output)
        if plan != candidate:
            parser.error("manifest changed; use a new evidence directory")
        from eval.memory.runner import run_plan

        asyncio.run(run_plan(plan, args.output, args.user, authorized=True))
    else:
        if args.authorized or args.user is not None:
            parser.error("owner/provider options are only accepted with --run")
        plan = candidate
        write_plan(plan, args.output)
    write_report(args.output, plan)


if __name__ == "__main__":
    main()
