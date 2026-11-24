from app.memory.batch_source_contracts import (
    NPCSourceResult,
    SourceOperation,
    SourceOperationPayload,
)
from app.memory.operation_contracts import RecordedOperation
from app.memory.operation_results import DeathResult, NPCResult


def _routine(operation: RecordedOperation) -> bool:
    payload = operation.payload
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


def project_operation(operation: RecordedOperation) -> SourceOperation | None:
    if _routine(operation):
        return None
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


def project_operations(
    operations: tuple[RecordedOperation, ...],
) -> tuple[SourceOperation, ...]:
    return tuple(
        projected
        for operation in operations
        if (projected := project_operation(operation)) is not None
    )
