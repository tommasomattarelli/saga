from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.operation_contracts import RecordedOperation
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation

_RECORDING = TypeAdapter(list[RecordedOperation])


def add_operation_recording(session: AsyncSession, turn: Turn, raw_operations: object) -> None:
    if raw_operations is None:
        return
    operations = _RECORDING.validate_python(raw_operations)
    turn.operations_version = 1
    turn.operation_count = len(operations)
    session.add_all(
        [
            TurnOperation(
                id=operation.id,
                campaign_id=turn.campaign_id,
                turn_id=turn.id,
                ordinal=operation.ordinal,
                step=operation.step,
                beat=operation.beat,
                payload=operation.payload,
            )
            for operation in operations
        ]
    )
