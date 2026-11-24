from pathlib import Path
from uuid import UUID

from app import dependencies
from app.ai.generation_attempt import single_generation_attempt
from app.ai.generation_context import generation_context
from app.memory.batch_input import load_batch_input
from app.memory.producer_prompts import prepare_request
from eval.integrated_memory.evidence_io import append_json
from eval.integrated_memory.job_driver import GenerationResolver, record_generation
from eval.integrated_memory.ledger import AttemptScope, IntegratedLedger
from eval.integrated_memory.plan import IntegratedPlan
from eval.integrated_memory.source_evidence import ordered_batch_ids
from eval.support.provider_trace import ProviderTrace


async def run_sidecar(
    plan: IntegratedPlan,
    ledger: IntegratedLedger,
    campaign_id: UUID,
    owner: UUID,
    directory: Path,
    resolve: GenerationResolver,
) -> None:
    batch_ids = await ordered_batch_ids(campaign_id)
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
        with (
            ledger.scope(scope),
            single_generation_attempt(),
            generation_context((trace, config)),
        ):
            await record_generation(request, scope, trace, directory / "sidecar-outputs.jsonl")
