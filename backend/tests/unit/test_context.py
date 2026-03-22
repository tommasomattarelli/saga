import uuid

import pytest

from app.ai.context import build_context, score_importance
from app.models.campaign import Campaign, DeathMode


def test_score_importance_default():
    campaign = Campaign(world_state={})
    score = score_importance("I walk to the tavern", campaign)
    assert score == 5


def test_score_importance_high_action():
    campaign = Campaign(world_state={})
    score = score_importance("I attack the guard!", campaign)
    assert score == 7


def test_score_importance_low_action():
    campaign = Campaign(world_state={})
    score = score_importance("I look around the empty room", campaign)
    assert score == 3  # 5 - 2


def test_score_importance_in_combat():
    campaign = Campaign(world_state={"in_combat": True})
    score = score_importance("I attack the guard!", campaign)
    assert score == 9  # 5 + 2 (attack) + 2 (combat)


def test_score_importance_bounds():
    campaign = Campaign(world_state={"in_combat": True})
    # Multiple keywords don't currently stack in the logic, but let's make sure it doesn't exceed 10.
    # Logic: base 5 + 2 (attack) + 2 (combat) = 9. If we added more, it caps at 10.
    # The function caps at 10 anyway via min(10, score).
    assert score_importance("I attack and fight and betray!", campaign) <= 10


@pytest.mark.asyncio
async def test_build_context(mocker):
    # Mock Turn and DB session
    class MockResult:
        def scalars(self):
            class MockScalars:
                def all(self):
                    turn_mock = mocker.Mock(
                        player_action="I walk",
                        narration="You walk.",
                        summary="Walked.",
                        turn_number=1,
                    )
                    return [turn_mock]
            return MockScalars()

    mock_db = mocker.Mock()
    mock_db.execute = mocker.AsyncMock(return_value=MockResult())

    campaign = Campaign(
        id=uuid.uuid4(),
        world_state={"time": {"time_of_day": "morning"}},
        death_mode=DeathMode.IRONMAN,
        quests={"active": [{"title": "Quest"}]},
        character_data={"hp": 10}
    )

    ctx = await build_context(campaign, "I look around.", mock_db)

    assert ctx.importance_score == 3  # "look around"
    assert "IRONMAN" in ctx.system_prompt
    assert len(ctx.active_quests) == 1
    assert ctx.messages[-1]["role"] == "user"
    assert ctx.messages[-1]["content"] == "I look around."
    assert "Walked." in ctx.recent_events[0]
