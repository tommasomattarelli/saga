import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.turn_service import process_turn
from app.models.campaign import Campaign
from datetime import datetime




@pytest.mark.asyncio
async def test_process_turn(mocker):
    mock_db = mocker.AsyncMock()
    
    camp = Campaign(
        id=uuid.uuid4(),
        name="Test",
        user_id=uuid.uuid4(),
        template_id="fantasy",
        turn_number=1,
        character_data={"name": "Hero", "hp": 10},
        world_state={"time": 10},
        quests={}
    )
    user = MagicMock()
    user.id = uuid.uuid4()
    user.preferred_language = "en"
    
    # Mock all the heavy context building
    mocker.patch("app.services.turn_service.build_system_context", return_value="SYS")
    mocker.patch("app.services.turn_service.build_action_prompt", return_value="ACT")
    mocker.patch("app.services.turn_service.route_ai_call", AsyncMock(return_value="""{"narration": "You hit it", "scene_mood": "tense", "dice_rolls": {"attack": 15}}"""))
    mocker.patch("app.services.turn_service.parse_ai_response", return_value={"narration": "You hit it", "scene_mood": "tense", "dice_rolls": {"attack": 15}})
    mocker.patch("app.services.turn_service.apply_world_updates")
    mocker.patch("app.services.turn_service.update_quests")
    mocker.patch("app.services.turn_service.apply_combat_effects", return_value=True)
    mocker.patch("app.services.turn_service.check_death_condition", return_value=False)
    mocker.patch("app.services.turn_service.generate_dynamic_embedding", AsyncMock(return_value=[0.1]*384))
    
    turn = await process_turn(camp, "I attack with my sword", user, mock_db)
    
    assert turn.turn_number == 2
    assert turn.player_action == "I attack with my sword"
    assert turn.narration == "You hit it"
    assert turn.model_used is not None
    assert mock_db.add.called
    assert mock_db.commit.called
