from uuid import uuid4

from app.memory.operation_contracts import RecordedOperation
from app.memory.operation_results import DeathResult
from app.memory.source_projection import project_operation, project_operations


def test_projection_preserves_source_fields_and_projects_npc_result() -> None:
    operation = RecordedOperation.model_validate(
        {
            "id": uuid4(),
            "ordinal": 2,
            "step": 3,
            "beat": 1,
            "payload": {
                "origin": "npc",
                "name": "invoke_npc",
                "outcome": "succeeded",
                "arguments": {"name": "Guard", "context": "asked"},
                "result": {
                    "kind": "npc",
                    "description": "Spoke",
                    "npc_id": "npc-1",
                    "status": "speaking",
                    "lines": ["Answer"],
                    "action": None,
                    "axis_changes": {"trust": 2},
                },
                "deltas": [],
            },
        }
    )

    projected = project_operation(operation)

    assert projected is not None
    assert projected.id == operation.id
    assert projected.ordinal == 2 and projected.step == 3 and projected.beat == 1
    assert projected.payload.result.model_dump() == {
        "kind": "npc",
        "npc_id": "npc-1",
        "status": "speaking",
        "action": None,
        "axis_changes": {"trust": 2},
    }


def test_projection_filters_only_existing_routine_operations() -> None:
    alive_check = RecordedOperation.model_validate(
        {
            "ordinal": 1,
            "payload": {
                "origin": "finalization",
                "name": "check_player_death",
                "outcome": "succeeded",
                "arguments": {"difficulty": "medium"},
                "result": {
                    "kind": "death",
                    "description": "Alive",
                    "action": "alive",
                    "is_dead": False,
                    "fate_interventions_remaining": 3,
                },
                "deltas": [],
            },
        }
    )

    assert isinstance(alive_check.payload.result, DeathResult)
    assert project_operation(alive_check) is None
    assert project_operations((alive_check,)) == ()
