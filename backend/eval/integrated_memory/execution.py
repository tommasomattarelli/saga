from __future__ import annotations

from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import dependencies
from app.ai.generation_context import Generation
from app.ai.providers.local import LocalProvider
from app.ai.router import get_user_embedding
from app.ai.session_affinity import campaign_session
from app.config_loader import load_saga_config
from app.main import create_app
from app.memory.context_snapshot import capture_turn_context
from app.memory.embedding_lifecycle import new_index
from app.memory.job_identity import effective_session_affinity, memory_job_session_scope
from app.models.campaign import Campaign
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.security.auth import create_access_token
from app.services.campaign_export import build_campaign_export
from eval.dialogue.limits import FreeRequestLimiter
from eval.integrated_memory.embedding_driver import drain_embeddings
from eval.integrated_memory.evidence_io import write_json
from eval.integrated_memory.job_driver import MemoryDriver
from eval.integrated_memory.ledger import IntegratedLedger
from eval.integrated_memory.plan import IntegratedPlan, resolve_effective_embedding
from eval.integrated_memory.provider_guard import guard_generation
from eval.integrated_memory.sidecar import run_sidecar
from eval.support.dialogue_affinity import provider_with_session, session_id_for_model
from eval.support.live_calls import resolve_eval_generation


async def execute_plan(plan: IntegratedPlan, directory: Path, owner: UUID) -> None:
    from eval.integrated_memory.replay import (
        authored_boundaries,
        create_replay_campaign,
        replay_sources,
    )
    from eval.integrated_memory.source_evidence import collect_batch_evidence

    assert plan.generation_request_cap is not None
    assert plan.embedding_request_cap is not None
    assert plan.embedding_text_cap is not None
    assert plan.generation_model is not None
    assert plan.embedding_space is not None
    ledger = IntegratedLedger(
        directory / "requests.jsonl",
        generation_cap=plan.generation_request_cap,
        embedding_cap=plan.embedding_request_cap,
        text_cap=plan.embedding_text_cap,
        run_seal=plan.seal,
    )
    session_id = session_id_for_model(plan.session_scope, plan.generation_model)
    limiter = FreeRequestLimiter()

    async def resolve(user_id: UUID) -> Generation:
        if user_id != owner:
            raise ValueError("integrated evaluation cannot resolve a different owner")
        provider, config = await resolve_eval_generation(
            owner, plan.generation_model or "", allow_paid=plan.allow_paid_generation
        )
        if not isinstance(provider, LocalProvider) or config.provider != "openrouter":
            raise ValueError("integrated generation requires the guarded OpenRouter adapter")
        if config.max_tokens != plan.output_cap:
            raise ValueError("resolved output cap differs from the frozen manifest")
        generation_config = load_saga_config().get("generation", {})
        affinity_enabled = generation_config.get("openrouter_session_affinity", True)
        if not isinstance(affinity_enabled, bool):
            raise ValueError("generation session affinity configuration is invalid")
        affinity = effective_session_affinity(config.provider, session_id, affinity_enabled)
        session_provider = provider_with_session(provider, affinity)
        if not isinstance(session_provider, LocalProvider):
            raise ValueError("evaluation session binding changed the guarded adapter")
        return guard_generation(session_provider, ledger, limiter=limiter), config

    write_json(directory / "run-start.json", {"manifest_seal": plan.seal, "state": "started"})
    campaign_id: UUID | None = None
    try:
        await resolve(owner)
        resolve_effective_embedding(
            plan, await get_user_embedding(owner, space=plan.embedding_space)
        )
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://integrated-eval",
            headers={"Authorization": f"Bearer {create_access_token(owner)}"},
        ) as client:
            async with authored_boundaries(plan.sources):
                campaign_id = await create_replay_campaign(
                    client, name=f"Memory evaluation {plan.run_id}", language=plan.language
                )
                async with dependencies.async_session() as db:
                    db.add(new_index(campaign_id, plan.embedding_space))
                    await db.commit()
                driver = MemoryDriver(plan, ledger, campaign_id, directory, resolve)
                with campaign_session(campaign_id), memory_job_session_scope(session_id):
                    turns = await replay_sources(
                        client,
                        campaign_id,
                        plan.sources,
                        after_turn=driver.drain,
                        evidence_path=directory / "turns.jsonl",
                    )
                    await driver.drain()
                    batches = await collect_batch_evidence(campaign_id, turns)
                    await verify_pipeline(plan, campaign_id, ledger)
                    write_json(
                        directory / "source-evidence.json",
                        {
                            "turns": [turn.model_dump(mode="json") for turn in turns],
                            "batches": [batch.model_dump(mode="json") for batch in batches],
                        },
                    )
                    if plan.unified_sidecar:
                        await run_sidecar(plan, ledger, campaign_id, owner, directory, resolve)
                    await drain_embeddings(plan, ledger, campaign_id, directory)
            archive = await build_campaign_export(campaign_id, owner)
            write_json(directory / "campaign.json", archive.model_dump(mode="json"))
        ledger.ensure_healthy()
        write_json(
            directory / "run.json",
            {
                "state": "completed",
                "manifest_seal": plan.seal,
                "campaign_id": str(campaign_id),
                "counts": ledger.counts,
            },
        )
    except BaseException:
        write_json(
            directory / "run.json",
            {
                "state": "stopped",
                "manifest_seal": plan.seal,
                "campaign_id": str(campaign_id) if campaign_id else None,
                "counts": ledger.counts,
            },
        )
        raise


async def verify_pipeline(
    plan: IntegratedPlan, campaign_id: UUID, ledger: IntegratedLedger
) -> None:
    async with dependencies.async_session() as db:
        jobs = tuple(
            await db.scalars(select(MemoryJob).where(MemoryJob.campaign_id == campaign_id))
        )
        if any(job.state != "succeeded" or job.attempt_count != 1 for job in jobs):
            raise ValueError("integrated jobs did not all publish on their first attempt")
        if (
            sum(job.kind == "batch" for job in jobs) != plan.batch_count
            or sum(job.kind == "global" for job in jobs) != plan.global_count
        ):
            raise ValueError("persisted job counts differ from the integrated plan")
        calls = tuple(
            await db.scalars(
                select(MemoryGeneration).where(MemoryGeneration.campaign_id == campaign_id)
            )
        )
        if len(calls) != plan.generation_baseline or ledger.counts["generation"] != len(calls):
            raise ValueError("persisted generations and outbound ledger do not agree")
        campaign = await db.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError("integrated evaluation campaign is missing")
        snapshot = await capture_turn_context(db, campaign)
        if snapshot.policy != plan.policy:
            raise ValueError("campaign policy differs from the frozen manifest")
        if len(snapshot.raw_turn_ids) != plan.policy.raw_turns or len(
            snapshot.intermediate_batch_ids
        ) != min(plan.batch_count, plan.policy.intermediate_limit):
            raise ValueError("final raw/intermediate coverage differs from the integrated plan")
