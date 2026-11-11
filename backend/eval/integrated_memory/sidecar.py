from pathlib import Path
from time import monotonic
from uuid import UUID

from sqlalchemy import select

from app import dependencies
from app.ai.generation_attempt import single_generation_attempt
from app.ai.generation_context import generation_context
from app.memory.batch_input import load_batch_input
from app.memory.producer_prompts import prepare_request
from app.memory.producers import generate_memory
from app.models.memory_batch import MemoryBatch
from app.models.turn import Turn
from eval.integrated_memory.evidence_io import append_json, provider_evidence
from eval.integrated_memory.job_driver import GenerationResolver
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger
from eval.integrated_memory.plan import IntegratedPlan
from eval.support.provider_trace import ProviderTrace


async def run_sidecar(
    plan: IntegratedPlan,
    ledger: IntegratedLedger,
    campaign_id: UUID,
    owner: UUID,
    directory: Path,
    resolve: GenerationResolver,
) -> None:
    async with dependencies.async_session() as db:
        batch_ids = tuple(
            await db.scalars(
                select(MemoryBatch.id)
                .join(Turn, Turn.id == MemoryBatch.source_head_turn_id)
                .where(MemoryBatch.campaign_id == campaign_id)
                .order_by(Turn.history_depth)
            )
        )
    if len(batch_ids) != plan.batch_count:
        raise ValueError("sidecar batch count differs from the integrated replay")
    for batch_id in batch_ids:
        ledger.ensure_healthy()
        async with dependencies.async_session() as db:
            source = await load_batch_input(db, campaign_id, batch_id)
        request = prepare_request(
            "batch", source, language=plan.language, facts_policy=plan.policy.facts
        )
        scope = AttemptScope(
            run_id=plan.run_id,
            campaign_id=campaign_id,
            batch_id=batch_id,
            source_turn_ids=tuple(turn.turn_id for turn in source.turns),
            input_hash=request.source_hash,
            role="unified",
            provider="openrouter",
            model=plan.generation_model or "",
        )
        provider, config = await resolve(owner)
        trace = ProviderTrace(provider, role="memory_unified")
        append_json(
            directory / "sidecar-inputs.jsonl",
            {
                "scope": scope.model_dump(mode="json"),
                "system_prompt": request.system_prompt,
                "user_prompt": request.user_prompt,
            },
        )
        started = monotonic()
        try:
            with (
                ledger.scope(scope),
                single_generation_attempt(),
                generation_context((trace, config)),
            ):
                result = await generate_memory(request)
        except BaseException:
            append_json(
                directory / "sidecar-outputs.jsonl",
                {
                    "scope": scope.model_dump(mode="json"),
                    "raw": str(trace.response.get("text", "")),
                    "valid": False,
                    **provider_evidence(trace, monotonic() - started),
                },
            )
            raise
        append_json(
            directory / "sidecar-outputs.jsonl",
            {
                "scope": scope.model_dump(mode="json"),
                "raw": result.raw,
                "valid": True,
                **provider_evidence(trace, monotonic() - started),
            },
        )
