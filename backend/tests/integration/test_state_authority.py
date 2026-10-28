import uuid

from sqlalchemy import select

from app.ai.providers.schemas import ToolCall
from app.models.turn import Turn
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


async def test_conflicting_history_is_retained_but_only_a_tool_changes_position(
    auth_client, generation_clients, db_session
) -> None:
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    invented_arrival = "You have already arrived in Thornhaven. The shrine is behind you."
    captured = _script(
        provider,
        [
            _reply(invented_arrival),
            _reply(
                "You set out from the shrine.",
                ToolCall(id="move", name="move_to", arguments={"location": "Thornhaven"}),
            ),
            _reply("The journey ends at Thornhaven's gate."),
        ],
    )
    action = "I follow the forest path east toward Thornhaven."

    first = await _take_turn(auth_client, campaign["id"], action)
    assert first["world_state"]["player_position"] == campaign["world_state"]["player_position"]
    assert first["time_passed_minutes"] == 0

    second = await _take_turn(auth_client, campaign["id"], action)
    assert len(captured) == 3
    for call in captured[1:]:
        assert "CURRENT STATE IS AUTHORITATIVE:" in call["system_prompt"]
        assert any(message.get("content") == invented_arrival for message in call["messages"])
    assert (
        'location="Shrine of First Light"'
        in captured[1]["system_prompt"].split("</character>", 1)[0]
    )
    assert 'location="Thornhaven"' in captured[2]["system_prompt"].split("</character>", 1)[0]
    assert second["world_state"]["player_position"] != first["world_state"]["player_position"]
    assert second["time_passed_minutes"] == 45
    assert (
        second["world_state"]["clock"]["total_minutes"]
        - first["world_state"]["clock"]["total_minutes"]
        == 45
    )

    stored_narration = await db_session.scalar(
        select(Turn.narration).where(
            Turn.campaign_id == uuid.UUID(campaign["id"]),
            Turn.turn_number == first["turn_number"],
        )
    )
    assert stored_narration == invented_arrival
