"""Data export/import endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.campaign import Campaign
from app.models.turn import Turn
from app.models.user import User
from app.security.auth import get_current_user

router = APIRouter()


@router.get("/{campaign_id}")
async def export_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export a campaign and all its turns as JSON."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    turns_result = await db.execute(
        select(Turn).where(Turn.campaign_id == campaign_id).order_by(Turn.turn_number)
    )
    turns = turns_result.scalars().all()

    return {
        "campaign": {
            "name": campaign.name,
            "template_id": campaign.template_id,
            "death_mode": campaign.death_mode,
            "character_data": campaign.character_data,
            "world_state": campaign.world_state,
            "quests": campaign.quests,
        },
        "turns": [
            {
                "turn_number": t.turn_number,
                "player_action": t.player_action,
                "narration": t.narration,
                "dice_rolls": t.dice_rolls,
                "scene_mood": t.scene_mood,
            }
            for t in turns
        ],
    }
