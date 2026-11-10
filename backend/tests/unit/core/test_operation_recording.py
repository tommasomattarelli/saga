from langchain_core.messages import AIMessage

from app.core.dm.dm_tools_executor import tools_node
from tests.unit.core.test_tools_node import _make_state


def call(tool_name: str, **args: object) -> dict:
    return {"name": tool_name, "args": args, "id": "same", "type": "tool_call"}


async def test_invisible_operations_preserve_intermediate_quest_changes() -> None:
    calls = [
        call("update_quest", quest_id="lead", status="active", name="A lead"),
        call("update_quest", quest_id="lead", status="completed"),
        call("update_quest", quest_id="lead", status="active"),
    ]
    result = await tools_node(_make_state(messages=[AIMessage(content="", tool_calls=calls)]))
    records = result["operations"]
    assert [record.ordinal for record in records] == [1, 2, 3]
    assert len({record.id for record in records}) == 3
    assert all(record.payload.outcome == "succeeded" for record in records)
    assert all(record.payload.deltas for record in records)
    assert result["tool_events"] == []
    assert result["quests"].active[0].id == "lead"


async def test_rejected_and_unknown_calls_are_not_lost_on_early_returns() -> None:
    calls = [
        call("missing"),
        call("request_dice", stat="DEX"),
        call("move_to", location="Nowhere"),
    ]
    result = await tools_node(_make_state(messages=[AIMessage(content="", tool_calls=calls)]))
    records = result["operations"]
    assert len(records) == 3
    assert {record.payload.result.reason for record in records} == {
        "unknown_tool",
        "invalid_arguments",
        "domain_rejection",
    }
    assert all(
        record.payload.outcome == "rejected" and not record.payload.deltas for record in records
    )


async def test_check_without_delta_still_records_the_mechanical_result() -> None:
    calls = [call("request_dice", stat="DEX", check="Balance", difficulty="normal")]
    result = await tools_node(_make_state(messages=[AIMessage(content="", tool_calls=calls)]))
    record = result["operations"][0]
    assert record.payload.outcome == "succeeded"
    assert record.payload.result.kind == "check"
    assert record.payload.deltas == ()
    assert isinstance(record.payload.result.checks["Balance"].success, bool)


async def test_operations_accumulate_across_steps_in_execution_order() -> None:
    first = await tools_node(
        _make_state(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[
                        call("set_scene_mood", mood="neutral"),
                    ],
                )
            ]
        )
    )
    second = await tools_node(
        _make_state(
            **{
                **first,
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            call("set_scene_mood", mood="dread_horror"),
                            call("request_dice", stat="DEX", check="Balance", difficulty="normal"),
                        ],
                    )
                ],
                "step_count": 2,
            }
        )
    )
    assert [r.payload.name for r in second["operations"]] == [
        "set_scene_mood",
        "request_dice",
        "set_scene_mood",
    ]
    assert [r.ordinal for r in second["operations"]] == [1, 2, 3]
