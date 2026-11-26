from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.ai.generation_attempt import single_generation_attempt
from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution_ledger import GenerationRecoveryPolicy, InMemoryGenerationLedger
from app.ai.providers.base import AIProvider
from app.ai.router import ModelConfig
from app.memory.producer_prompts import prepare_request
from app.memory.producers import execute_memory_generation
from app.memory.production_policy import configured_memory_policy
from eval.attribution.manifest import (
    LIVE_MODEL,
    AttributionManifest,
    load_manifest,
    prepare_manifest,
    write_manifest,
)
from eval.attribution.scoring import overall, score_scenario
from eval.integrated_memory.evidence_io import append_json
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger
from eval.support.live_calls import resolve_eval_generation
from eval.support.provider_trace import ProviderTrace

REAL_BATCH = "real_batch_anonymized"


class _LedgerProvider:
    def __init__(self, provider: AIProvider, ledger: IntegratedLedger) -> None:
        self.provider = provider
        self.ledger = ledger
        self.trace: ProviderTrace | None = None
        self.latency_ms = 0.0

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.ledger.ensure_healthy()
        self.ledger.require_scope(provider=request.provider, model=request.model)
        input_hash = hashlib.sha256(request.snapshot_json.encode()).hexdigest()
        self.ledger.reserve(
            "generation",
            {"provider": request.provider, "model": request.model, "input_hash": input_hash},
            texts=0,
        )
        trace = ProviderTrace(self.provider, role=f"attribution_{request.role}")
        started = time.monotonic()
        try:
            with single_generation_attempt():
                receipt = await trace.send(request)
        except asyncio.CancelledError:
            self.ledger.cancel()
            raise
        except BaseException:
            self.ledger.fail(retrying=True)
            raise
        self.ledger.complete()
        self.trace = trace
        self.latency_ms = (time.monotonic() - started) * 1000
        return receipt


def _tokens(trace: ProviderTrace | None) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for name in ("input", "output"):
        values = (
            [item.input_tokens if name == "input" else item.output_tokens for item in trace.usage]
            if trace
            else []
        )
        result[name] = (
            sum(value for value in values if value is not None)
            if any(value is not None for value in values)
            else None
        )
    return result


async def run_plan(
    manifest: AttributionManifest, directory: Path, user_id: UUID, *, authorized: bool
) -> None:
    if not authorized:
        raise ValueError("A live attribution run requires explicit owner authorization.")
    ledger = IntegratedLedger(
        directory / "ledger.jsonl",
        generation_cap=manifest.request_cap,
        embedding_cap=0,
        text_cap=0,
        run_seal=manifest.seal,
    )
    provider, config = await resolve_eval_generation(user_id, manifest.model)
    if not isinstance(config, ModelConfig) or config.provider != "openrouter":
        raise ValueError("Live attribution evaluation requires the owner's OpenRouter profile.")
    guarded = _LedgerProvider(provider, ledger)
    policy = GenerationRecoveryPolicy(1)
    for scenario in manifest.scenarios:
        ledger.ensure_healthy()
        request = prepare_request(
            "batch",
            scenario.source,
            language=manifest.language,
            facts_policy=configured_memory_policy().facts,
        )
        scope = AttemptScope(
            run_id=manifest.run_id,
            campaign_id=uuid5(NAMESPACE_URL, scenario.name),
            source_turn_ids=tuple(turn.turn_id for turn in scenario.source.turns),
            input_hash=request.source_hash,
            role="facts",
            provider="openrouter",
            model=manifest.model,
        )
        with ledger.scope(scope):
            generation = await execute_memory_generation(
                request,
                provider=guarded,
                ledger=InMemoryGenerationLedger(),
                config=replace(config, model=manifest.model),
                policy=policy,
                adapter=Adapter(config.provider),
                session_affinity=None,
            )
        append_json(
            directory / "runs.jsonl",
            {
                "name": scenario.name,
                "raw": generation.raw,
                "facts": [
                    {
                        "content": fact.content,
                        "assertion_type": fact.assertion_type,
                        "entities": [
                            entity.model_dump(mode="json") for entity in fact.metadata.entities
                        ],
                        "attribution": list(fact.metadata.attribution),
                    }
                    for fact in generation.facts
                ],
                "tokens": _tokens(guarded.trace),
                "latency_ms": guarded.latency_ms,
            },
        )


def write_report(directory: Path) -> dict[str, object]:
    manifest = load_manifest(directory)
    evidence = [
        json.loads(line)
        for line in (directory / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_name = {item["name"]: item for item in evidence}
    scores = tuple(
        score_scenario(scenario, by_name.get(scenario.name, {})) for scenario in manifest.scenarios
    )
    result = {
        **overall(scores, REAL_BATCH),
        "scenarios": [
            {
                "name": score.name,
                "matched": score.matched,
                "expected": score.expected,
                "coverage": score.coverage,
                "wrong_speaker": score.wrong_speaker,
                "bundled": score.bundled,
                "forbidden_hits": score.forbidden_hits,
                "extra_declarative": score.extra_declarative,
                "tokens": score.tokens,
                "latency_ms": score.latency_ms,
                "raw_output": score.raw_output,
            }
            for score in scores
        ],
    }
    (directory / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Speaker-attribution memory evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.add_argument("--model", default=LIVE_MODEL)
    prepare.add_argument("--request-cap", type=int)
    prepare.add_argument("--language", default="en")
    for name in ("validate", "report"):
        command = commands.add_parser(name)
        command.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--user", required=True, type=UUID)
    run.add_argument("--authorized", action="store_true", required=True)
    args = parser.parse_args()

    if args.command == "prepare":
        manifest = prepare_manifest(
            run_id=args.run_id,
            model=args.model,
            request_cap=args.request_cap,
            language=args.language,
        )
        write_manifest(manifest, args.output)
        print(f"Prepared offline manifest: {args.output / 'manifest.json'}")
    elif args.command == "validate":
        manifest = load_manifest(args.output)
        print(
            f"Manifest valid; scenarios={len(manifest.scenarios)}; "
            f"model={manifest.model}; approved=false"
        )
    elif args.command == "report":
        result = write_report(args.output)
        print(
            f"Green={str(result['green']).lower()}; "
            f"synthetic_coverage={result['synthetic_coverage']:.2f}; "
            f"real={result['real_covered']}/{result['real_expected']}"
        )
    else:
        manifest = load_manifest(args.output)
        asyncio.run(run_plan(manifest, args.output, args.user, authorized=args.authorized))


if __name__ == "__main__":
    main()
