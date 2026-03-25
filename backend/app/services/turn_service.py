"""Turn processing service - orchestrates the turn pipeline."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_embedding
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.core.engine import process_game_turn
from app.memory.compressor import compress_turn_to_summary
from app.models.campaign import Campaign
from app.models.save import Save
from app.models.turn import Turn
from app.models.user import User
from app.schemas.campaign import TurnResponse

logger = structlog.get_logger()


async def process_turn(
    campaign: Campaign,
    raw_action: str,
    user: User,
    db: AsyncSession,
) -> TurnResponse:
    """Process a player turn end-to-end."""
    action = sanitize_player_input(raw_action)
    if detect_injection(action):
        logger.warning("prompt_injection_detected", user_id=str(user.id))
        action = "[The player looks around cautiously]"

    processed = await process_game_turn(campaign, action, db)

    campaign.turn_number += 1
    summary = await compress_turn_to_summary(processed.narration, action)
    embedding = await generate_embedding(summary)

    turn = Turn(
        campaign_id=campaign.id,
        turn_number=campaign.turn_number,
        player_action=action,
        narration=processed.narration,
        dice_rolls=processed.dice_rolls,
        companion_actions=processed.companion_actions,
        world_updates=processed.world_updates,
        scene_mood=processed.scene_mood,
        suggested_actions=processed.suggested_actions,
        model_used=processed.model_used,
        importance_score=processed.importance_score,
        summary=summary,
        embedding=embedding,
    )
    db.add(turn)

    from sqlalchemy import delete

    await db.execute(
        delete(Save).where(Save.campaign_id == campaign.id, Save.is_auto == True)  # noqa: E712
    )
    auto_save = Save(
        campaign_id=campaign.id,
        name="Auto-save",
        turn_number=campaign.turn_number,
        scene_summary=summary,
        is_auto=True,
        campaign_snapshot={
            "character_data": campaign.character_data,
            "world_state": campaign.world_state,
            "quests": campaign.quests,
            "turn_number": campaign.turn_number,
        },
    )
    db.add(auto_save)

    await db.commit()

    return TurnResponse(
        turn_number=campaign.turn_number,
        narration=processed.narration,
        dice_rolls=processed.dice_rolls,
        companion_actions=processed.companion_actions,
        world_updates=processed.world_updates,
        scene_mood=processed.scene_mood,
        suggested_actions=processed.suggested_actions,
        model_used=processed.model_used,
        invoke_npcs=processed.invoke_npcs,
        time_passed_minutes=processed.time_passed_minutes,
        ambient_detail=processed.ambient_detail,
        requires_player_action=processed.requires_player_action,
    )
