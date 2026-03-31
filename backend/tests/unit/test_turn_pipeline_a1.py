"""Tests for the updated turn pipeline — dice re-prompt, GameClock, creation mode."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.exceptions import ContentPolicyError
from app.core.engine import CONTENT_POLICY_NARRATION, ProcessedTurn
from app.core.turn import process_game_turn


def _make_campaign(character_data=None, world_state=None):
    campaign = MagicMock()
    campaign.id = "test-campaign-id"
    campaign.character_data = character_data or {
        "name": "Aria",
        "abilities": {"strength": 16, "dexterity": 14},
    }
    campaign.world_state = world_state or {
        "meta": {"schema_version": 2, "world_name": "Test", "current_season": "spring"},
        "clock": {"total_minutes": 480},
    }
    campaign.quests = {}
    campaign.death_mode = "destino"
    campaign.turn_number = 1
    return campaign


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_basic_turn_no_dice(mock_context, mock_route, mock_get_provider):
    dm_response = json.dumps(
        {
            "narration": "You walk into the tavern.",
            "scene_mood": "calm_exploration",
            "time_passed_minutes": 5,
            "suggested_actions": ["Talk to barkeep", "Look around"],
        }
    )

    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=dm_response)
    mock_get_provider.return_value = provider

    campaign = _make_campaign()
    db = AsyncMock()

    result = await process_game_turn(campaign, "enter the tavern", db)

    assert isinstance(result, ProcessedTurn)
    assert "tavern" in result.narration
    assert result.dice_rolls is None
    assert result.scene_mood == "calm_exploration"
    assert result.time_passed_minutes == 5


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_turn_with_dice_reprompt(mock_context, mock_route, mock_get_provider):
    dm_response = json.dumps(
        {
            "narration": "You attempt to sneak past the guard.",
            "dice_required": [{"name": "stealth", "dc": 15, "modifier": 3}],
            "scene_mood": "stealth_danger",
        }
    )
    reprompt_response = json.dumps(
        {
            "narration": "You slip past unnoticed.",
        }
    )

    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(side_effect=[dm_response, reprompt_response])
    mock_get_provider.return_value = provider

    campaign = _make_campaign()
    db = AsyncMock()

    result = await process_game_turn(campaign, "sneak past the guard", db)

    assert result.dice_rolls is not None
    assert "stealth" in result.dice_rolls
    roll = result.dice_rolls["stealth"]
    assert "outcome" in roll
    assert "is_critical" in roll
    assert "You attempt to sneak" in result.narration
    assert "slip past" in result.narration
    # Provider called twice (initial + re-prompt)
    assert provider.generate.call_count == 2


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_content_policy_error_handled(mock_context, mock_route, mock_get_provider):
    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(side_effect=ContentPolicyError("openai", "blocked"))
    mock_get_provider.return_value = provider

    campaign = _make_campaign()
    db = AsyncMock()

    result = await process_game_turn(campaign, "inappropriate action", db)

    assert result.narration == CONTENT_POLICY_NARRATION
    assert result.dice_rolls is None


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_game_clock_advances(mock_context, mock_route, mock_get_provider):
    dm_response = json.dumps(
        {
            "narration": "Time passes.",
            "time_passed_minutes": 60,
        }
    )

    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=dm_response)
    mock_get_provider.return_value = provider

    campaign = _make_campaign()
    db = AsyncMock()

    await process_game_turn(campaign, "rest", db)

    assert campaign.world_state["clock"]["total_minutes"] == 540  # 480 + 60


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_character_generation_saved(mock_context, mock_route, mock_get_provider):
    char_data = {
        "name": "Theron",
        "level": 1,
        "hp": 12,
        "max_hp": 12,
        "ac": 14,
        "abilities": {"strength": 16, "dexterity": 12},
    }
    dm_response = json.dumps(
        {
            "narration": "A warrior emerges from the mist.",
            "character_generation": char_data,
            "scene_mood": "wonder_discovery",
        }
    )

    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(return_value=dm_response)
    mock_get_provider.return_value = provider

    campaign = _make_campaign(character_data={})
    db = AsyncMock()

    result = await process_game_turn(campaign, "I want to be a warrior", db)

    assert campaign.character_data["name"] == "Theron"
    assert campaign.character_data["abilities"]["strength"] == 16
    assert "warrior" in result.narration.lower() or "mist" in result.narration.lower()


@pytest.mark.asyncio
@patch("app.ai.providers.base.get_provider")
@patch("app.core.turn.route_ai_call")
@patch("app.core.turn.build_context")
async def test_ability_modifier_from_character(mock_context, mock_route, mock_get_provider):
    """When dice check name matches an ability, modifier should come from character_data."""
    dm_response = json.dumps(
        {
            "narration": "You try to lift the boulder.",
            "dice_required": [{"name": "strength", "dc": 18, "modifier": 0}],
        }
    )
    reprompt_response = json.dumps({"narration": "You lift it!"})

    mock_context.return_value = MagicMock(system_prompt="test", messages=[], importance_score=5)
    mock_route.return_value = MagicMock(provider="openai", model="gpt-4o", temperature=0.8)
    provider = AsyncMock()
    provider.generate = AsyncMock(side_effect=[dm_response, reprompt_response])
    mock_get_provider.return_value = provider

    campaign = _make_campaign(
        character_data={
            "name": "Aria",
            "abilities": {"strength": 16},  # modifier = +3
        }
    )
    db = AsyncMock()

    result = await process_game_turn(campaign, "lift the boulder", db)

    # The dice should have used the strength modifier (+3) from character
    assert result.dice_rolls is not None
    roll = result.dice_rolls["strength"]
    assert roll["modifier"] == 3  # (16 - 10) // 2 = 3
