import copy
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.schemas import ToolCall
from app.memory.world_state import advance_game_clock
from app.models.campaign import Campaign
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


@pytest.mark.parametrize(
    "case,expected",
    [("advance", 15), ("travel", 45), ("mixed", 48), ("rejected", 0), ("interrupted", 22)],
)
async def test_clock_has_one_writer_and_reports_actual_elapsed_time(
    auth_client, db_session: AsyncSession, generation_clients: dict, case: str, expected: int
) -> None:
    created = await _create_campaign(auth_client)
    campaign_id = created["id"]
    campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert campaign is not None
    campaign.world_state = advance_game_clock(campaign.world_state, 2640 - 480)
    origin = campaign.world_state["player_position"]
    if case == "interrupted":
        baseline = copy.deepcopy(campaign.world_baseline)
        baseline["edges"]["forest-path"].update(encounter_chance=1, encounter_table="test-ambush")
        baseline.setdefault("encounters", {})["test-ambush"] = {
            "dice": "1d1",
            "entries": [
                {
                    "roll": [1, 1],
                    "type": "combat",
                    "description": "Bandits block the path.",
                    "once": True,
                }
            ],
        }
        campaign.world_baseline = baseline
    await db_session.commit()
    provider = await _openai_provider(auth_client, generation_clients)
    if case == "advance":
        calls = [ToolCall(id="time", name="advance_time", arguments={"minutes": 15})]
    else:
        calls = [
            ToolCall(
                id="move",
                name="move_to",
                arguments={"location": "Nowhere" if case == "rejected" else "Thornhaven"},
            )
        ]
        if case == "mixed":
            calls.append(ToolCall(id="time", name="advance_time", arguments={"minutes": 3}))
    captured = _script(provider, [_reply("", *calls), _reply("The outcome is clear.")])
    result = await _take_turn(auth_client, campaign_id, "I continue.")
    assert result["world_state"]["clock"]["total_minutes"] == 2640 + expected
    assert result["time_passed_minutes"] == expected
    await db_session.refresh(campaign)
    assert campaign.world_state["clock"]["total_minutes"] == 2640 + expected
    feedback = " ".join(
        message.get("content", "")
        for message in captured[1]["messages"]
        if message["role"] == "tool"
    )
    if case == "advance":
        assert "Day 2, evening" in feedback
    elif case == "interrupted":
        assert result["world_state"]["player_position"] == origin
        assert result["world_state"]["pending_travel"]["minutes_remaining"] == 23
        assert "INTERRUPTED after 22 minutes" in feedback
    elif case == "rejected":
        assert result["world_state"]["player_position"] == origin
        assert "rejected" in feedback
    else:
        assert result["world_state"]["player_position"] != origin
