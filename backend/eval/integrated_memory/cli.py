from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from app.ai.embedding_config import EmbeddingSpace

from .plan import load_plan, prepare_plan, write_plan
from .report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline integrated memory evaluation tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--sources", required=True, type=Path)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--language", default="en")
    prepare.add_argument("--generation-model")
    prepare.add_argument("--generation-request-cap", type=int)
    prepare.add_argument("--allow-paid-generation", action="store_true")
    prepare.add_argument("--embedding-space", type=Path)
    prepare.add_argument("--embedding-request-cap", type=int)
    prepare.add_argument("--embedding-text-cap", type=int)
    prepare.add_argument("--embedding-max-retries", type=int)
    prepare.add_argument("--unified-sidecar", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("--output", required=True, type=Path)
    report = subparsers.add_parser("report")
    report.add_argument("--output", required=True, type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--user", required=True, type=UUID)
    run.add_argument("--authorized", action="store_true", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        space = (
            EmbeddingSpace(**json.loads(args.embedding_space.read_text(encoding="utf-8")))
            if args.embedding_space
            else None
        )
        plan = prepare_plan(
            sources=args.sources,
            run_id=args.run_id,
            language=args.language,
            generation_model=args.generation_model,
            generation_request_cap=args.generation_request_cap,
            embedding_space=space,
            embedding_request_cap=args.embedding_request_cap,
            embedding_text_cap=args.embedding_text_cap,
            embedding_max_retries=args.embedding_max_retries,
            unified_sidecar=args.unified_sidecar,
            allow_paid_generation=args.allow_paid_generation,
        )
        write_plan(plan, args.output)
        print(f"Prepared offline manifest: {args.output / 'manifest.json'}")
    elif args.command == "validate":
        plan = load_plan(args.output)
        print(f"Manifest valid; executable={str(plan.executable).lower()}; approved=false")
    elif args.command == "report":
        print(write_report(args.output))
    else:
        plan = load_plan(args.output)
        from .runner import run_plan

        asyncio.run(run_plan(plan, args.output, args.user, authorized=args.authorized))


if __name__ == "__main__":
    main()
