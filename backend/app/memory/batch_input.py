from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_source_contracts import (
    BatchInput,
    BatchTurnSource,
    NPCSourceResult,
    SourceOperation,
    SourceOperationPayload,
)
from app.memory.history import HistoryIntegrityError
from app.memory.operation_contracts import OperationPayload
from app.memory.operation_results import DeathResult, NPCResult
from app.models.history import MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation


def _routine(payload: OperationPayload) -> bool:
    if payload.outcome != "succeeded":
        return False
    if payload.origin == "tool" and payload.name in {"set_scene_mood", "advance_time"}:
        field = "scene_mood" if payload.name == "set_scene_mood" else "clock"
        return all(d.scope == "world_state" and d.path[0] == field for d in payload.deltas)
    if payload.origin == "finalization" and payload.name == "record_interactions":
        return all(
            d.scope == "world_state"
            and len(d.path) == 3
            and d.path[0] == "npcs"
            and d.path[2] == "last_interactions"
            for d in payload.deltas
        )
    return (
        isinstance(payload.result, DeathResult)
        and payload.result.action == "alive"
        and not payload.deltas
    )


def _project(operation: TurnOperation) -> SourceOperation:
    payload = operation.payload.model_copy(deep=True)
    result = payload.result
    projected = (
        NPCSourceResult(
            npc_id=result.npc_id,
            status=result.status,
            action=result.action,
            axis_changes=result.axis_changes,
        )
        if isinstance(result, NPCResult)
        else result
    )
    return SourceOperation(
        id=operation.id,
        ordinal=operation.ordinal,
        step=operation.step,
        beat=operation.beat,
        payload=SourceOperationPayload(
            origin=payload.origin,
            name=payload.name,
            outcome=payload.outcome,
            arguments=payload.arguments,
            result=projected,
            deltas=payload.deltas,
        ),
    )


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
            projected = tuple(_project(op) for op in recorded if not _routine(op.payload))
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
