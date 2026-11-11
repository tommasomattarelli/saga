from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_input import load_batch_input, load_turn_input
from app.memory.job_activation import activate_artifact
from app.memory.job_claims import lock_campaign
from app.memory.job_coverage import MemoryCoverage, load_coverage
from app.memory.job_requests import build_job_manifest, job_manifest_hash
from app.memory.producer_prompts import PRODUCER_VERSION, canonical, digest
from app.memory.production_policy import MemoryProductionPolicy
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_job import MemoryJob


async def _existing_batch(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    turn_ids: tuple[UUID, ...],
) -> MemoryBatch | None:
    return await db.scalar(
        select(MemoryBatch).where(
            MemoryBatch.campaign_id == campaign.id,
            MemoryBatch.policy_id == state.policy_id,
            MemoryBatch.previous_batch_id == state.last_compacted_batch_id,
            MemoryBatch.source_head_turn_id == turn_ids[-1],
        )
    )


async def _reserve_batch(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    turn_ids: tuple[UUID, ...],
) -> MemoryBatch:
    existing = await _existing_batch(db, campaign, state, turn_ids)
    if existing is not None:
        return existing
    source = await load_turn_input(db, campaign.id, turn_ids)
    batch = MemoryBatch(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=state.policy_id,
        previous_batch_id=state.last_compacted_batch_id,
        source_head_turn_id=turn_ids[-1],
        manifest_hash=source.source_hash(),
    )
    db.add(batch)
    await db.flush()
    db.add_all(
        [
            MemoryBatchTurn(
                campaign_id=campaign.id, batch_id=batch.id, ordinal=index, turn_id=turn_id
            )
            for index, turn_id in enumerate(turn_ids, start=1)
        ]
    )
    await db.flush()
    return batch


async def _ensure_job(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    policy: MemoryProductionPolicy,
    batch: MemoryBatch,
    kind: Literal["batch", "global"],
) -> UUID:
    previous_id = state.global_checkpoint_id if kind == "global" else None
    existing = await db.scalar(
        select(MemoryJob)
        .where(
            MemoryJob.campaign_id == campaign.id,
            MemoryJob.policy_id == state.policy_id,
            MemoryJob.batch_id == batch.id,
            MemoryJob.kind == kind,
            MemoryJob.previous_checkpoint_id == previous_id,
        )
        .order_by(MemoryJob.created_at, MemoryJob.id)
        .limit(1)
    )
    if existing is not None:
        return existing.id
    previous = await db.get(MemoryGlobalCheckpoint, previous_id) if previous_id else None
    source = await load_batch_input(db, campaign.id, batch.id)
    manifest = build_job_manifest(
        kind,
        source,
        language=campaign.language,
        facts_policy=policy.facts,
        global_policy=policy.global_ if kind == "global" else None,
        previous=previous.payload if previous else None,
    )
    manifest_hash = job_manifest_hash(manifest)
    key = digest(
        canonical(
            {
                "policy": str(state.policy_id),
                "batch": str(batch.id),
                "kind": kind,
                "previous": str(previous_id) if previous_id else None,
                "manifest": manifest_hash,
                "producer": PRODUCER_VERSION,
            }
        )
    )
    job = MemoryJob(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=state.policy_id,
        batch_id=batch.id,
        memory_state_id=state.id,
        context_epoch=state.context_epoch,
        kind=kind,
        previous_checkpoint_id=previous_id,
        logical_key=key,
        manifest=manifest,
        manifest_hash=manifest_hash,
        producer_version=PRODUCER_VERSION,
        prompt_version=manifest.instruction_version,
        state="queued",
        attempt_count=0,
        retry_cycle=0,
        cycle_attempt_count=0,
        activation_state="pending",
    )
    db.add(job)
    await db.flush()
    return job.id


async def _reconcile_one(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    policy: MemoryProductionPolicy,
    coverage: MemoryCoverage,
) -> bool:
    if len(coverage.raw_turn_ids) >= policy.raw_turns + policy.batch_turns:
        batch = await _existing_batch(
            db, campaign, state, coverage.raw_turn_ids[: policy.batch_turns]
        )
        if (
            batch is not None
            and await db.scalar(
                select(MemorySummary.id).where(
                    MemorySummary.batch_id == batch.id,
                )
            )
            is not None
            and await activate_artifact(db, campaign, state, batch, None)
        ):
            return True
    if (
        coverage.projected_intermediates(policy) > policy.intermediate_limit
        and coverage.intermediates
    ):
        batch = coverage.batches[coverage.global_batches]
        checkpoint = await db.scalar(
            select(MemoryGlobalCheckpoint).where(
                MemoryGlobalCheckpoint.batch_id == batch.id,
                MemoryGlobalCheckpoint.previous_checkpoint_id == state.global_checkpoint_id,
                MemoryGlobalCheckpoint.campaign_id == campaign.id,
            )
        )
        if checkpoint is not None and await activate_artifact(
            db, campaign, state, batch, checkpoint
        ):
            return True
    return False


async def coordinate_memory(db: AsyncSession, campaign_id: UUID) -> tuple[UUID, ...]:
    campaign = await lock_campaign(db, campaign_id)
    if campaign is None or campaign.active_memory_state_id is None:
        return ()
    state = await db.scalar(
        select(MemoryState)
        .where(
            MemoryState.id == campaign.active_memory_state_id,
            MemoryState.campaign_id == campaign_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if state is None or state.context_epoch != campaign.context_epoch:
        return ()
    stored_policy = await db.get(MemoryPolicy, state.policy_id)
    if stored_policy is None:
        return ()
    policy = stored_policy.payload
    coverage = await load_coverage(db, campaign, state, policy)
    limit = len(coverage.raw_turn_ids) // policy.batch_turns + len(coverage.batches) + 1
    for _ in range(limit):
        if not await _reconcile_one(db, campaign, state, policy, coverage):
            break
        await db.flush()
        coverage = await load_coverage(db, campaign, state, policy)
    jobs = []
    if len(coverage.raw_turn_ids) >= policy.raw_turns + policy.batch_turns:
        batch = await _reserve_batch(
            db, campaign, state, coverage.raw_turn_ids[: policy.batch_turns]
        )
        jobs.append(await _ensure_job(db, campaign, state, policy, batch, "batch"))
    if (
        coverage.projected_intermediates(policy) > policy.intermediate_limit
        and coverage.intermediates
    ):
        jobs.append(
            await _ensure_job(
                db,
                campaign,
                state,
                policy,
                coverage.batches[coverage.global_batches],
                "global",
            )
        )
    return tuple(jobs)
