from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_compatibility import batch_is_compatible
from app.memory.job_coverage import load_coverage
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_batch import MemoryBatch
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary


async def activate_artifact(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    batch: MemoryBatch,
    checkpoint: MemoryGlobalCheckpoint | None = None,
) -> bool:
    if (
        campaign.active_memory_state_id != state.id
        or campaign.context_epoch != state.context_epoch
        or batch.campaign_id != campaign.id
        or batch.policy_id != state.policy_id
        or not await batch_is_compatible(db, campaign.id, batch.id, campaign.active_head_turn_id)
    ):
        return False
    summary = await db.scalar(select(MemorySummary).where(MemorySummary.batch_id == batch.id))
    if summary is None:
        return False
    policy = await db.get(MemoryPolicy, state.policy_id)
    if policy is None:
        return False
    coverage = await load_coverage(db, campaign, state, policy.payload)
    total_turns = len(coverage.raw_turn_ids) + len(coverage.batches) * policy.payload.batch_turns
    batch_limit = max(total_turns - policy.payload.raw_turns, 0) // policy.payload.batch_turns
    if checkpoint is not None:
        if (
            checkpoint.campaign_id != campaign.id
            or checkpoint.policy_id != state.policy_id
            or checkpoint.previous_checkpoint_id != state.global_checkpoint_id
            or checkpoint.batch_id != batch.id
            or not coverage.intermediates
            or coverage.batches[coverage.global_batches].id != batch.id
        ):
            return False
        global_limit = max(batch_limit - policy.payload.intermediate_limit, 0)
        if coverage.global_batches + 1 > global_limit:
            return False
        state.global_checkpoint_id = checkpoint.id
    else:
        if batch.previous_batch_id != state.last_compacted_batch_id:
            return False
        if len(coverage.batches) + 1 > batch_limit:
            return False
        state.last_compacted_batch_id = batch.id
    state.revision += 1
    return True
