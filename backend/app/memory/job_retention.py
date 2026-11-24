from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob


async def cleanup_terminal_generation_payloads(
    db: AsyncSession, campaign_id: UUID, retention_days: int
) -> int:
    terminal_job = (
        select(MemoryJob.id)
        .where(
            MemoryJob.id == MemoryGeneration.job_id,
            MemoryJob.campaign_id == campaign_id,
            MemoryJob.state.in_(("succeeded", "exhausted")),
            MemoryJob.terminal_at.is_not(None),
            MemoryJob.terminal_at
            <= func.clock_timestamp() - func.make_interval(0, 0, 0, retention_days),
        )
        .exists()
    )
    result = await db.execute(
        update(MemoryGeneration)
        .where(
            MemoryGeneration.campaign_id == campaign_id,
            terminal_job,
            or_(
                MemoryGeneration.raw_candidate.is_not(None),
                MemoryGeneration.receipt.is_not(None),
            ),
        )
        .values(raw_candidate=None, receipt=None)
        .returning(MemoryGeneration.id)
    )
    return len(result.scalars().all())
