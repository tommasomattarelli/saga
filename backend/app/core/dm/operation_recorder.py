from collections.abc import Sequence

from pydantic import JsonValue, TypeAdapter

from app.memory.operation_contracts import (
    OperationOrigin,
    OperationOutcome,
    OperationPayload,
    OperationResult,
    RecordedOperation,
)
from app.memory.operation_delta import OperationState, state_delta
from app.models.quest import QuestRegistry

_ARGUMENTS = TypeAdapter(dict[str, JsonValue])


def capture_state(world_state: object, char_data: object, quests: QuestRegistry) -> OperationState:
    return OperationState.capture(world_state, char_data, quests.model_dump(mode="json"))


class OperationRecorder:
    def __init__(self, records: Sequence[RecordedOperation] = ()) -> None:
        self.records = list(records)

    def append(
        self,
        *,
        origin: OperationOrigin,
        name: str,
        arguments: object,
        outcome: OperationOutcome,
        result: OperationResult,
        step: int | None,
        beat: int | None = None,
        before: OperationState | None = None,
        after: OperationState | None = None,
    ) -> None:
        self.records.append(
            RecordedOperation(
                ordinal=len(self.records) + 1,
                step=step,
                beat=beat,
                payload=OperationPayload(
                    origin=origin,
                    name=name,
                    arguments=_ARGUMENTS.validate_python(arguments),
                    outcome=outcome,
                    result=result,
                    deltas=state_delta(before, after)
                    if before is not None and after is not None
                    else (),
                ),
            )
        )
