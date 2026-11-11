from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_compatibility import batch_is_compatible
from app.memory.history import HistoryIntegrityError, history_path
from app.memory.production_policy import MemoryProductionPolicy
from app.models.campaign import Campaign
from app.models.memory_batch import MemoryBatch
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState
from app.models.turn import Turn


@dataclass(frozen=True)
class MemoryCoverage:
    raw_turn_ids: tuple[UUID, ...]
    batches: tuple[MemoryBatch, ...]
    global_batches: int

    @property
    def intermediates(self) -> int:
        return len(self.batches) - self.global_batches

    def projected_intermediates(self, policy: MemoryProductionPolicy) -> int:
        debt = max(len(self.raw_turn_ids) - policy.raw_turns, 0) // policy.batch_turns
        return self.intermediates + debt


async def batch_chain(
    db: AsyncSession, campaign_id: UUID, last_batch_id: UUID | None
) -> tuple[MemoryBatch, ...]:
    if last_batch_id is None:
        return ()
    chain = (
        select(MemoryBatch.id, MemoryBatch.previous_batch_id)
        .where(
            MemoryBatch.id == last_batch_id,
            MemoryBatch.campaign_id == campaign_id,
        )
        .cte("batch_chain", recursive=True)
    )
    chain = chain.union_all(
        select(MemoryBatch.id, MemoryBatch.previous_batch_id)
        .join(
            chain,
            MemoryBatch.id == chain.c.previous_batch_id,
        )
        .where(MemoryBatch.campaign_id == campaign_id)
    )
    return tuple(
        await db.scalars(
            select(MemoryBatch)
            .join(chain, MemoryBatch.id == chain.c.id)
            .join(Turn, Turn.id == MemoryBatch.source_head_turn_id)
            .order_by(Turn.history_depth)
        )
    )


async def load_coverage(
    db: AsyncSession,
    campaign: Campaign,
    state: MemoryState,
    policy: MemoryProductionPolicy,
) -> MemoryCoverage:
    turns = await history_path(db, campaign.id, campaign.active_head_turn_id)
    batches = await batch_chain(db, campaign.id, state.last_compacted_batch_id)
    compacted = len(batches) * policy.batch_turns
    if batches and not await batch_is_compatible(
        db,
        campaign.id,
        batches[-1].id,
        campaign.active_head_turn_id,
    ):
        raise HistoryIntegrityError("The memory coverage does not belong to this history.")
    if compacted > len(turns):
        raise HistoryIntegrityError("The memory coverage exceeds this history.")
    global_batches = 0
    if state.global_checkpoint_id is not None:
        checkpoint = await db.get(MemoryGlobalCheckpoint, state.global_checkpoint_id)
        ids = [batch.id for batch in batches]
        if checkpoint is None or checkpoint.batch_id not in ids:
            raise HistoryIntegrityError(
                "The memory checkpoint does not belong to its batch chain."
            )
        global_batches = ids.index(checkpoint.batch_id) + 1
    return MemoryCoverage(tuple(turn.id for turn in turns[compacted:]), batches, global_batches)
