import uuid
from unittest.mock import MagicMock

import pytest

from app.core.engine import ProcessedTurn
from app.models.campaign import Campaign
from app.schemas.campaign import TurnResponse
from app.services.turn_service import process_turn


@pytest.mark.asyncio
async def test_process_turn(mocker):
    # Mocking dependencies
    mock_db = mocker.AsyncMock()
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    mock_campaign = Campaign(
        id=uuid.uuid4(),
        name="Test Campaign",
        user_id=mock_user.id,
        turn_number=1,
        character_data={"name": "Hero"},
        world_state={"location": "Forest"},
    )

    # Mock the engine call
    mock_processed = ProcessedTurn(
        narration="You walk into the woods.",
        dice_rolls={"stealth": 15},
        companion_actions={},
        world_updates={},
        scene_mood="quiet",
        suggested_actions=["Look around", "Keep moving"],
        model_used="gpt-4o",
        importance_score=5,
    )

    mocker.patch("app.services.turn_service.sanitize_player_input", side_effect=lambda x: x)
    mocker.patch("app.services.turn_service.detect_injection", return_value=False)
    mocker.patch(
        "app.services.turn_service.process_game_turn",
        mocker.AsyncMock(return_value=mock_processed),
    )
    mocker.patch(
        "app.services.turn_service.compress_turn_to_summary",
        mocker.AsyncMock(return_value="Summary"),
    )
    mocker.patch(
        "app.services.turn_service.generate_embedding", mocker.AsyncMock(return_value=[0.1] * 1536)
    )

    # Mocking Save deletion and creation
    mock_db.execute = mocker.AsyncMock()

    result = await process_turn(mock_campaign, "I go north", mock_user, mock_db)

    assert isinstance(result, TurnResponse)
    assert result.turn_number == 2
    assert result.narration == "You walk into the woods."
    assert mock_db.add.called
    assert mock_db.commit.called
