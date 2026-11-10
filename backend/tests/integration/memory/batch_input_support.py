from uuid import uuid4

from app.memory.operation_contracts import OperationPayload, RecordedOperation
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation
from tests.integration.memory.storage_support import HistoryFixture


def payload(
    name: str,
    arguments: dict[str, object],
    *,
    deltas: list[dict[str, object]] | None = None,
    result: dict[str, object] | None = None,
) -> OperationPayload:
    return OperationPayload.model_validate(
        {
            "origin": "npc" if name == "invoke_npc" else "tool",
            "name": name,
            "outcome": "succeeded",
            "arguments": arguments,
            "result": result or {"kind": "message", "description": "Done."},
            "deltas": deltas or [],
        }
    )


async def recorded_turn(
    f: HistoryFixture,
    *,
    parent: Turn | None,
    number: int,
    action: str,
    narration: str,
    operations: list[RecordedOperation] | None = None,
) -> Turn:
    turn = Turn(
        id=uuid4(),
        campaign_id=f.campaign.id,
        continuation_id=f.root.id,
        parent_turn_id=parent.id if parent else None,
        history_depth=(parent.history_depth + 1) if parent else 1,
        turn_number=number,
        operations_version=1,
        operation_count=len(operations or []),
        player_action=action,
        narration=narration,
        model_used="test",
    )
    f.session.add(turn)
    await f.session.flush()
    f.session.add_all(
        [
            TurnOperation(
                id=operation.id,
                campaign_id=f.campaign.id,
                turn_id=turn.id,
                ordinal=operation.ordinal,
                step=operation.step,
                beat=operation.beat,
                payload=operation.payload,
            )
            for operation in operations or []
        ]
    )
    await f.session.flush()
    return turn


def op(ordinal: int, item: OperationPayload) -> RecordedOperation:
    return RecordedOperation(ordinal=ordinal, payload=item)


def delta(scope: str, path: list[str], before: object, after: object) -> dict[str, object]:
    return {
        "scope": scope,
        "path": path,
        "before": {"presence": "present", "value": before},
        "after": {"presence": "present", "value": after},
    }


def projection_operations() -> list[RecordedOperation]:
    routine_mood = payload(
        "set_scene_mood",
        {"mood": "tense_anticipation"},
        deltas=[delta("world_state", ["scene_mood"], "neutral", "tense_anticipation")],
    )
    routine_clock = payload(
        "advance_time",
        {"minutes": 5},
        deltas=[delta("world_state", ["clock", "minute"], 0, 5)],
    )
    no_delta_dice = payload(
        "request_dice",
        {"check": "stealth", "stat": "DEX", "difficulty": "normal"},
        result={
            "kind": "check",
            "description": "Mira fails to hide.",
            "checks": {
                "Mira": {
                    "expression": "1d20",
                    "rolls": [4],
                    "modifier": 0,
                    "difficulty": "normal",
                    "difficulty_draw": 10,
                    "total": 4,
                    "success": False,
                    "outcome": "hard_failure",
                    "is_critical": False,
                }
            },
        },
    )
    travel = payload(
        "move_to",
        {"location": "The ruined tower"},
        deltas=[
            delta("world_state", ["clock", "minute"], 5, 35),
            delta("world_state", ["location"], "Village", "The ruined tower"),
        ],
    )
    time_with_side_effect = payload(
        "advance_time",
        {"minutes": 30},
        deltas=[
            delta("world_state", ["clock", "minute"], 35, 65),
            delta("world_state", ["factions", "guard", "alert"], 0, 1),
        ],
    )
    clock_only_travel = payload(
        "move_to",
        {"location": "The crossroads"},
        deltas=[delta("world_state", ["clock", "minute"], 65, 90)],
    )
    no_delta_npc = payload(
        "invoke_npc",
        {"name": "Captain", "context": "The journey"},
        result={
            "kind": "npc",
            "description": "The captain refuses to answer.",
            "npc_id": "captain",
            "status": "silent",
            "lines": [],
        },
    )
    finalization = OperationPayload.model_validate(
        {
            "origin": "finalization",
            "name": "check_player_death",
            "outcome": "succeeded",
            "arguments": {"difficulty": "normal"},
            "result": {
                "kind": "death",
                "description": "The player remains alive.",
                "action": "alive",
                "is_dead": False,
            },
            "deltas": [],
        }
    )
    recorded_interaction = OperationPayload.model_validate(
        {
            "origin": "finalization",
            "name": "record_interactions",
            "outcome": "succeeded",
            "arguments": {"npc_id": "captain"},
            "result": {"kind": "message", "description": "Interaction archived."},
            "deltas": [
                delta("world_state", ["npcs", "captain", "last_interactions"], [], ["spoke"])
            ],
        }
    )
    return [
        op(1, routine_mood),
        op(2, routine_clock),
        op(3, no_delta_dice),
        op(4, travel),
        op(5, no_delta_npc),
        op(6, finalization),
        op(7, time_with_side_effect),
        op(8, clock_only_travel),
        op(9, recorded_interaction),
    ]
