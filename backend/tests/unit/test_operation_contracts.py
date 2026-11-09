import json

import pytest
from pydantic import ValidationError

from app.memory.operation_contracts import OperationPayload, StateDelta
from app.memory.operation_delta import OperationState, state_delta


def test_presence_distinguishes_absence_from_null() -> None:
    delta = StateDelta.model_validate_json(
        '{"scope":"world_state","path":["clue"],'
        '"before":{"presence":"absent"},"after":{"presence":"present","value":null}}'
    )
    assert delta.before.model_dump() == {"presence": "absent"}
    assert delta.after.model_dump() == {"presence": "present", "value": None}
    with pytest.raises(ValidationError):
        StateDelta.model_validate_json(
            '{"scope":"world_state","path":["clue"],'
            '"before":{"presence":"absent","value":null},"after":{"presence":"absent"}}'
        )


def test_delta_is_per_operation_and_preserves_json_types() -> None:
    first = OperationState.capture({"flag": 1, "old": None}, {}, {})
    middle = OperationState.capture({"flag": True, "new": None}, {}, {})
    forward = state_delta(first, middle)
    backward = state_delta(middle, first)
    assert [change.path for change in forward] == [("flag",), ("new",), ("old",)]
    assert forward[0].before.value == 1
    assert forward[0].after.value is True
    assert len(backward) == 3
    assert state_delta(first, first) == ()


def test_snapshots_do_not_alias_in_place_mutations() -> None:
    world = {"npc": {"name": "Mira"}}
    before = OperationState.capture(world, {}, {})
    world["npc"]["name"] = "Neris"
    changes = state_delta(before, OperationState.capture(world, {}, {}))
    assert changes[0].path == ("npc", "name")
    assert changes[0].before.value == "Mira"


def test_known_successful_arguments_use_the_real_tool_schema() -> None:
    payload = {
        "origin": "tool",
        "name": "move_to",
        "outcome": "succeeded",
        "arguments": {"location": "Thornhaven"},
        "result": {"kind": "message", "description": "Moved."},
        "deltas": [],
    }
    assert OperationPayload.model_validate_json(json.dumps(payload)).outcome == "succeeded"
    payload["arguments"] = {"unknown": "invalid"}
    with pytest.raises(ValidationError):
        OperationPayload.model_validate_json(json.dumps(payload))
    payload["outcome"] = "rejected"
    payload["result"] = {
        "kind": "error",
        "reason": "invalid_arguments",
        "description": "Invalid input.",
    }
    assert OperationPayload.model_validate_json(json.dumps(payload)).outcome == "rejected"


def test_rejection_cannot_carry_an_unrelated_success_result() -> None:
    with pytest.raises(ValidationError):
        OperationPayload.model_validate_json(
            '{"origin":"tool","name":"move_to","outcome":"rejected",'
            '"arguments":{"location":"Here"},'
            '"result":{"kind":"message","description":"Moved."},"deltas":[]}'
        )


@pytest.mark.parametrize("value", [float("nan"), object()])
def test_snapshot_rejects_non_json_values(value: object) -> None:
    with pytest.raises((ValidationError, ValueError)):
        OperationState.capture({"value": value}, {}, {})
