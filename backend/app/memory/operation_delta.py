import copy
import json
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue, TypeAdapter

from app.memory.operation_contracts import AbsentValue, PresentValue, StateDelta

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True)
class OperationState:
    world_state: dict[str, JsonValue]
    character_data: dict[str, JsonValue]
    quests: dict[str, JsonValue]

    @classmethod
    def capture(
        cls, world_state: object, character_data: object, quests: object
    ) -> "OperationState":
        values = [
            _JSON_OBJECT.validate_python(value) for value in (world_state, character_data, quests)
        ]
        json.dumps(values, allow_nan=False)
        return cls(*copy.deepcopy(values))


def state_delta(before: OperationState, after: OperationState) -> tuple[StateDelta, ...]:
    changes: list[StateDelta] = []
    for scope in ("world_state", "character_data", "quests"):
        _compare(scope, (), getattr(before, scope), getattr(after, scope), changes)
    return tuple(changes)


def _compare(
    scope: Literal["world_state", "character_data", "quests"],
    path: tuple[str, ...],
    before: JsonValue,
    after: JsonValue,
    changes: list[StateDelta],
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            if key in before and key in after:
                _compare(scope, (*path, key), before[key], after[key], changes)
            else:
                changes.append(
                    StateDelta(
                        scope=scope,
                        path=(*path, key),
                        before=PresentValue(value=before[key]) if key in before else AbsentValue(),
                        after=PresentValue(value=after[key]) if key in after else AbsentValue(),
                    )
                )
    elif json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True):
        changes.append(
            StateDelta(
                scope=scope,
                path=path,
                before=PresentValue(value=before),
                after=PresentValue(value=after),
            )
        )
