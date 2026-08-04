import uuid

import pytest

from app.ai.context import _enforce_token_budget, build_context, score_importance
from app.models.campaign import Campaign, Difficulty


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
    assert score == 3


def test_score_importance_bounds():
    campaign = Campaign(world_state={"in_combat": True})
    assert score_importance("I attack and fight and betray!", campaign) <= 10


class TestTokenBudget:
    def test_under_cap_returns_unchanged(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "current"},
        ]
        result = _enforce_token_budget("system", messages, token_cap=10000)
        assert result == messages

    def test_drops_oldest_pair_when_over_cap(self):
        # Each message ~250 tokens (1000 chars / 4)
        messages = [
            {"role": "user", "content": "x" * 1000},
            {"role": "assistant", "content": "y" * 1000},
            {"role": "user", "content": "a" * 1000},
            {"role": "assistant", "content": "b" * 1000},
            {"role": "user", "content": "current action"},
        ]
        result = _enforce_token_budget("", messages, token_cap=600)
        # Trailing message always preserved
        assert result[-1]["content"] == "current action"
        # Oldest pair dropped first
        assert len(result) < len(messages)
        assert all(m["content"] != "x" * 1000 for m in result)

    def test_preserves_trailing_message(self):
        messages = [
            {"role": "user", "content": "x" * 10000},
            {"role": "assistant", "content": "y" * 10000},
            {"role": "user", "content": "final"},
        ]
        result = _enforce_token_budget("", messages, token_cap=100)
        assert result[-1]["content"] == "final"


@pytest.mark.asyncio
async def test_build_context(mocker):
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

    mocker.patch("app.ai.context.search_similar_facts", mocker.AsyncMock(return_value=[]))

    campaign = Campaign(
        id=uuid.uuid4(),
        world_state={"time": {"time_of_day": "morning"}},
        difficulty=Difficulty.HARD,
        quests={"active": [{"title": "Quest"}]},
        character_data={"hp": 10},
    )

    ctx = await build_context(campaign, "I look around.", mock_db)

    assert ctx.importance_score == 3
    # ADR 0003 B8 — death instructions no longer ride every prompt.
    assert "IRONMAN" not in ctx.system_prompt.upper()
    assert len(ctx.active_quests) == 1
    assert ctx.messages[-1]["role"] == "user"
    assert ctx.messages[-1]["content"] == "I look around."
    assert "Walked." in ctx.recent_events[0]


@pytest.mark.asyncio
async def test_build_context_injects_recalled_memories(mocker):
    class MockResult:
        def scalars(self):
            class MockScalars:
                def all(self):
                    return []

            return MockScalars()

        def all(self):
            return []

    mock_db = mocker.Mock()
    mock_db.execute = mocker.AsyncMock(return_value=MockResult())

    fact1 = mocker.Mock(content="Lyra is the blacksmith of Ironveil.")
    fact2 = mocker.Mock(content="The dragon's hoard lies under the old keep.")
    mocker.patch(
        "app.ai.context.search_similar_facts",
        mocker.AsyncMock(return_value=[fact1, fact2]),
    )

    campaign = Campaign(
        id=uuid.uuid4(),
        world_state={},
        difficulty=Difficulty.EASY,
        quests={},
        character_data={"name": "Hero", "hp": 10, "max_hp": 10},
    )

    ctx = await build_context(campaign, "I ask about the dragon", mock_db)

    assert "<recalled_memories>" in ctx.system_prompt
    assert "Lyra is the blacksmith" in ctx.system_prompt
    assert "dragon's hoard" in ctx.system_prompt


@pytest.mark.asyncio
async def test_build_context_includes_global_summary(mocker):
    class MockResult:
        def scalars(self):
            class MockScalars:
                def all(self):
                    return []

            return MockScalars()

        def all(self):
            return []

    mock_db = mocker.Mock()
    mock_db.execute = mocker.AsyncMock(return_value=MockResult())
    mocker.patch("app.ai.context.search_similar_facts", mocker.AsyncMock(return_value=[]))

    campaign = Campaign(
        id=uuid.uuid4(),
        world_state={},
        difficulty=Difficulty.EASY,
        quests={},
        character_data={"name": "Hero", "hp": 10, "max_hp": 10},
        global_summary="The hero crossed the mountains and bargained with the witch.",
    )

    ctx = await build_context(campaign, "I continue", mock_db)

    assert "<global_summary>" in ctx.system_prompt
    assert "crossed the mountains" in ctx.system_prompt


@pytest.mark.asyncio
async def test_build_context_token_cap_drops_oldest(mocker):
    """When prompt + messages exceed token_cap, oldest verbatim turn pairs are dropped."""
    big_turn = mocker.Mock(
        player_action="A" * 2000,
        narration="B" * 2000,
        summary=None,
        turn_number=1,
    )
    recent_turn = mocker.Mock(
        player_action="I say hi",
        narration="The NPC responds.",
        summary=None,
        turn_number=2,
    )

    class MockResult:
        def scalars(self):
            class MockScalars:
                def all(self):
                    # build_context reverses this, so order matters: DESC => [recent, big]
                    return [recent_turn, big_turn]

            return MockScalars()

        def all(self):
            return []

    mock_db = mocker.Mock()
    mock_db.execute = mocker.AsyncMock(return_value=MockResult())
    mocker.patch("app.ai.context.search_similar_facts", mocker.AsyncMock(return_value=[]))

    # Force a tiny token cap
    mock_cfg = mocker.Mock(
        context_window_turns=8,
        context_token_cap=200,
    )
    mocker.patch("app.ai.context.get_gameplay_config", return_value=mock_cfg)

    campaign = Campaign(
        id=uuid.uuid4(),
        world_state={},
        difficulty=Difficulty.EASY,
        quests={},
        character_data={"name": "Hero", "hp": 10, "max_hp": 10},
    )

    ctx = await build_context(campaign, "current action", mock_db)

    # Current action always preserved
    assert ctx.messages[-1]["content"] == "current action"
    # Oldest big turn dropped under budget
    contents = [m.get("content", "") for m in ctx.messages]
    assert not any(c == "A" * 2000 for c in contents)
