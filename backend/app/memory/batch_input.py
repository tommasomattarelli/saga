from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_source_contracts import (
    BatchInput,
    BatchTurnSource,
)
from app.memory.history import HistoryIntegrityError
from app.memory.operation_contracts import RecordedOperation
from app.memory.source_projection import project_operations
from app.models.history import MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation


async def load_batch_input(session: AsyncSession, campaign_id: UUID, batch_id: UUID) -> BatchInput:
    batch = await session.scalar(
        select(MemoryBatch).where(
            MemoryBatch.id == batch_id,
            MemoryBatch.campaign_id == campaign_id,
        )
    )
    if batch is None:
        raise HistoryIntegrityError("The selected batch does not belong to this campaign.")
    policy = await session.get(MemoryPolicy, batch.policy_id)
    turns = list(
        (
            await session.scalars(
                select(Turn)
                .join(MemoryBatchTurn, MemoryBatchTurn.turn_id == Turn.id)
                .where(
                    MemoryBatchTurn.batch_id == batch_id,
                    MemoryBatchTurn.campaign_id == campaign_id,
                    Turn.campaign_id == campaign_id,
                )
                .order_by(MemoryBatchTurn.ordinal)
            )
        ).all()
    )
    if policy is None or len(turns) != policy.payload.batch_turns:
        raise HistoryIntegrityError("The selected batch has incomplete source membership.")
    operations: dict[UUID, list[TurnOperation]] = defaultdict(list)
    for operation in await session.scalars(
        select(TurnOperation)
        .where(
            TurnOperation.campaign_id == campaign_id,
            TurnOperation.turn_id.in_([turn.id for turn in turns]),
        )
        .order_by(TurnOperation.turn_id, TurnOperation.ordinal)
    ):
        operations[operation.turn_id].append(operation)
    sources = []
    for index, turn in enumerate(turns, start=1):
        recorded = operations[turn.id]
        if turn.operations_version is None:
            if recorded:
                raise HistoryIntegrityError("An unrecorded turn cannot contain operation sources.")
            projected = None
        else:
            if (
                turn.operations_version != 1
                or turn.operation_count != len(recorded)
                or [op.ordinal for op in recorded] != list(range(1, len(recorded) + 1))
            ):
                raise HistoryIntegrityError("The turn operation recording is incomplete.")
            projected = project_operations(
                tuple(
                    RecordedOperation(
                        id=op.id,
                        ordinal=op.ordinal,
                        step=op.step,
                        beat=op.beat,
                        payload=op.payload,
                    )
                    for op in recorded
                )
            )
        sources.append(
            BatchTurnSource(
                reference=f"t{index}",
                turn_id=turn.id,
                player_action=turn.player_action,
                narration=turn.narration,
                operations=projected,
            )
        )
    return BatchInput(turns=tuple(sources))
