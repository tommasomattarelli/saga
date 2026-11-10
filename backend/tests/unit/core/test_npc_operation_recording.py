from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from app.ai.npc_outcomes import NPCFailure, NPCSilent
from app.core.dm.dm_nodes import post_process_node
from app.core.dm.dm_tools_executor import tools_node
from tests.unit.core.test_operation_recording import call
from tests.unit.core.test_tools_node import _make_state


async def test_autocreation_is_separate_from_a_failed_actor() -> None:
    state = _make_state(
        allowed_tools=["invoke_npc"],
        messages=[
            AIMessage(
                content="",
                tool_calls=[
                    call("invoke_npc", name="New Farmer"),
                ],
            )
        ],
    )
    with patch(
        "app.core.dm.npc_beat.invoke_npcs_parallel",
        new=AsyncMock(return_value=[NPCFailure("New Farmer")]),
    ):
        result = await tools_node(state)
    records = result["operations"]
    assert [(r.payload.name, r.payload.outcome) for r in records] == [
        ("create_npc", "succeeded"),
        ("invoke_npc", "failed"),
    ]
    assert records[0].payload.deltas[0].before.presence == "absent"
    assert records[1].payload.deltas == ()
    assert records[0].payload.result.npc_id == records[1].payload.result.npc_id


async def test_npc_silence_is_success_and_rejections_are_recorded() -> None:
    state = _make_state(
        allowed_tools=["invoke_npc"],
        messages=[
            AIMessage(
                content="",
                tool_calls=[
                    call("invoke_npc", name="New Farmer"),
                    call("invoke_npc", name="new farmer"),
                    call("invoke_npc", wrong="invalid"),
                ],
            )
        ],
    )
    with patch(
        "app.core.dm.npc_beat.invoke_npcs_parallel",
        new=AsyncMock(return_value=[NPCSilent("New Farmer", ())]),
    ):
        result = await tools_node(state)
    records = result["operations"]
    assert [r.payload.outcome for r in records] == [
        "rejected",
        "rejected",
        "succeeded",
        "succeeded",
    ]
    assert records[-1].payload.result.status == "silent"
    assert records[-1].payload.deltas[0].path[-1] == "met_player"
    assert records[-1].payload.deltas[0].after.value is True
    assert all(r.beat == 0 and r.step == 0 for r in records)


def test_finalization_captures_death_hp_change_without_mutating_its_input() -> None:
    state = _make_state(char_data={"hp": {"current": 0, "max": 10}}, difficulty="easy")
    result = post_process_node(state)
    record = result["operations"][-1]
    assert record.payload.name == "check_player_death"
    assert record.payload.result.action == "near_death"
    assert record.payload.deltas[0].scope == "character_data"
    assert record.payload.deltas[0].path == ("hp", "current")
    assert result["char_data"]["hp"]["current"] == 1
    assert state["char_data"]["hp"]["current"] == 0
