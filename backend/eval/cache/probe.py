import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from app.ai.providers.local import LocalProvider
from eval.cache.plan import MODELS, Plan, build_plan, write_plan
from eval.cache.report import write_report
from eval.cache.runner import run_block
from eval.support.live_calls import resolve_eval_generation, validate_eval_models


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded cache diagnostic; prepare is entirely offline."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--model", choices=MODELS, required=True)
    prepare.add_argument("--phase", choices=("identical", "replay"), required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--max-output-tokens", type=int, default=1024)
    prepare.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--user", type=UUID, required=True)
    report = commands.add_parser("report")
    report.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            plan = await build_plan(args.model, args.phase, args.run_id, args.max_output_tokens)
            write_plan(plan, args.out)
            print(
                json.dumps(
                    {
                        "model": plan.model,
                        "phase": plan.phase,
                        "requests": len(plan.requests),
                        "max_output_tokens_per_request": plan.max_tokens,
                        "payload_characters": {
                            name: len(json.dumps(p.body(), ensure_ascii=False))
                            for name, p in plan.payloads.items()
                        },
                        "manifest": str(args.out / "manifest.json"),
                        "source_hash": plan.source_hash,
                        "dirty": plan.dirty,
                        "network_requests": 0,
                    },
                    indent=2,
                )
            )
            return
        plan = Plan.model_validate_json((args.out / "manifest.json").read_text())
        if args.command == "report":
            write_report(args.out, plan)
            return
        if (args.out / "started.json").exists():
            parser.error("This block already started; review evidence instead of repeating it.")
        current = await build_plan(plan.model, plan.phase, plan.run_id, plan.max_tokens)
        if current != plan:
            parser.error(
                "Source or payload identity changed; prepare a fresh manifest before running."
            )
        await validate_eval_models([plan.model], {plan.model})
        provider, _ = await resolve_eval_generation(args.user, plan.model, allow_paid=True)
        if not isinstance(provider, LocalProvider):
            parser.error("The cache probe requires the owner's OpenRouter client.")
        await run_block(plan, provider, args.out, args.user)
        print(
            "Block stopped. Review report.md and the dashboard before starting another phase/model."
        )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    asyncio.run(main())
