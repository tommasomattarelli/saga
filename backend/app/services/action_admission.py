from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.job_coverage import load_coverage
from app.memory.job_scheduler import coordinate_memory
from app.memory.production_policy import MemoryProductionPolicy
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_document import MemoryState
from app.models.memory_job import MemoryJob
from app.services.action_errors import ActionError


async def check_action_capacity(
    db: AsyncSession,
    campaign: Campaign,
) -> tuple[MemoryProductionPolicy, ActionError | None]:
    if campaign.memory_policy_id is None or campaign.active_memory_state_id is None:
        raise ActionError(
            "campaign_history_required",
            "This campaign predates the new memory system; create a new campaign to play.",
        )
    jobs = await coordinate_memory(db, campaign.id)
    stored = await db.get(MemoryPolicy, campaign.memory_policy_id)
    state = await db.get(MemoryState, campaign.active_memory_state_id)
    if stored is None or state is None or state.context_epoch != campaign.context_epoch:
        raise ActionError("campaign_history_invalid", "The campaign memory state is inconsistent.")
    policy = stored.payload
    coverage = await load_coverage(db, campaign, state, policy)
    raw = len(coverage.raw_turn_ids)
    projected = coverage.projected_intermediates(policy)
    raw_ceiling = policy.raw_turns + policy.batch_turns * (1 + policy.backlog_batches)
    intermediate_ceiling = policy.intermediate_limit + 1 + policy.backlog_batches
    next_projected = (
        coverage.intermediates + max(raw + 1 - policy.raw_turns, 0) // policy.batch_turns
    )
    raw_full = raw >= raw_ceiling or raw + 1 > raw_ceiling
    global_full = projected >= intermediate_ceiling or next_projected > intermediate_ceiling
    if not raw_full and not global_full:
        return policy, None
    required = set()
    if raw_full or (global_full and not coverage.intermediates):
        required.add("batch")
    if global_full and coverage.intermediates:
        required.add("global")
    blocked = list(
        await db.scalars(
            select(MemoryJob).where(
                MemoryJob.id.in_(jobs),
                MemoryJob.kind.in_(required),
                MemoryJob.state.in_(("blocked", "exhausted")),
            )
        )
    )
    if any(job.state == "blocked" for job in blocked):
        return policy, ActionError(
            "memory_configuration_required",
            "Update your provider settings, then retry memory processing.",
            status_code=503,
        )
    if blocked:
        return policy, ActionError(
            "memory_retry_required",
            "Memory processing exhausted its attempts; retry it explicitly.",
            status_code=503,
        )
    return policy, ActionError(
        "memory_busy",
        "Memory processing is still catching up; retry this action shortly.",
        status_code=503,
    )
