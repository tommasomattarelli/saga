"""Playtest: Combat Turn Baseline Scenario.

Verifies that the current engine (engine.py) correctly processes a combat turn:
- API returns expected response structure (narration, scene_mood, suggested_actions)
- Campaign turn_number increments after a turn
- The mock is at the AI process_game_turn level, letting the rest of process_turn run

This test establishes the CURRENT BEHAVIOR baseline before Engine refactoring.
If the refactored engine changes output structure, THIS TEST MUST BE UPDATED.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _make_mock_game_turn():
    """Return a MagicMock matching what process_game_turn returns."""
    mock = MagicMock()
    mock.narration = "You charge at the goblin! Roll to hit."
    mock.dice_rolls = {"attack": 14}
    mock.companion_actions = None
    mock.world_updates = None
    mock.scene_mood = "intense"
    mock.suggested_actions = ["Attack again", "Retreat", "Use ability"]
    mock.model_used = "gpt-4o"
    mock.importance_score = 7
    return mock


@pytest.mark.asyncio
async def test_scenario_combat_turn_response_structure(auth_client: AsyncClient, db_session):
    """A submitted turn action should return the expected JSON structure."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Combat Test",
            "template_id": "tutorial",
            "death_mode": "destino",
            "character_data": {"name": "Barbarian", "hp": 25, "atk": 8},
        },
    )
    campaign_id = resp.json()["id"]

    # Mock only the AI call (process_game_turn), so process_turn runs real logic
    with (
        patch(
            "app.services.turn_service.process_game_turn", new_callable=AsyncMock
        ) as mock_engine,
        patch(
            "app.services.turn_service.compress_turn_to_summary", new_callable=AsyncMock
        ) as mock_compress,
        patch(
            "app.services.turn_service.generate_embedding", new_callable=AsyncMock
        ) as mock_embed,
    ):
        mock_engine.return_value = _make_mock_game_turn()
        mock_compress.return_value = "Player charges a goblin."
        mock_embed.return_value = [0.0] * 384  # Vector placeholder

        turn_resp = await auth_client.post(
            f"/api/campaigns/{campaign_id}/turn",
            json={"action": "I charge at the nearest goblin with my axe!"},
        )

    assert turn_resp.status_code == 200
    data = turn_resp.json()

    # Baseline contract: these fields must always be present
    assert data["narration"] == "You charge at the goblin! Roll to hit."
    assert data["scene_mood"] == "intense"
    assert isinstance(data["suggested_actions"], list)
    assert len(data["suggested_actions"]) == 3
    assert data["turn_number"] == 1


@pytest.mark.asyncio
async def test_scenario_turn_increments_counter(auth_client: AsyncClient, db_session):
    """Campaign turn_number must be persisted to DB after each turn."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Turn Counter",
            "template_id": "tutorial",
            "death_mode": "destino",
            "character_data": {},
        },
    )
    campaign_id = resp.json()["id"]

    # Verify initial turn_number is 0
    get_resp = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert get_resp.json()["turn_number"] == 0

    with (
        patch(
            "app.services.turn_service.process_game_turn", new_callable=AsyncMock
        ) as mock_engine,
        patch(
            "app.services.turn_service.compress_turn_to_summary", new_callable=AsyncMock
        ) as mock_compress,
        patch(
            "app.services.turn_service.generate_embedding", new_callable=AsyncMock
        ) as mock_embed,
    ):
        mock_engine.return_value = _make_mock_game_turn()
        mock_compress.return_value = "Player looks around."
        mock_embed.return_value = [0.0] * 384

        await auth_client.post(
            f"/api/campaigns/{campaign_id}/turn", json={"action": "Look around"}
        )

    # Turn number should now be 1
    get_resp = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert get_resp.json()["turn_number"] == 1
