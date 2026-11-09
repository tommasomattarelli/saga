from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.history import history_ancestry
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn


async def batch_is_compatible(
    session: AsyncSession,
    campaign_id: UUID,
    batch_id: UUID,
    head_turn_id: UUID | None,
) -> bool:
    if head_turn_id is None:
        return False
    ancestry = history_ancestry(campaign_id, head_turn_id)
    source_ids = select(MemoryBatchTurn.turn_id).where(
        MemoryBatchTurn.batch_id == batch_id,
        MemoryBatchTurn.campaign_id == campaign_id,
    )
    in_path = exists(
        select(ancestry.c.id)
        .where(ancestry.c.id == MemoryBatchTurn.turn_id)
        .correlate(MemoryBatchTurn)
    )
    incompatible = exists(source_ids.where(~in_path))
    return bool(
        await session.scalar(
            select(
                exists().where(
                    MemoryBatch.id == batch_id,
                    MemoryBatch.campaign_id == campaign_id,
                    ~incompatible,
                    exists(select(ancestry.c.id)),
                )
            )
        )
    )
