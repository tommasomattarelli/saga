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
async def get_journal(
    campaign_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get adventure journal."""
    campaign = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    if not campaign.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign_id)
        .order_by(Turn.turn_number.desc())
        .offset(offset)
        .limit(limit)
    )
    turns = result.scalars().all()
    return [
        {
            "turn_number": t.turn_number,
            "player_action": t.player_action,
            "narration": t.narration,
            "narration_segments": t.narration_segments,
            "dice_rolls": t.dice_rolls,
            "scene_mood": t.scene_mood,
            "created_at": t.created_at.isoformat(),
        }
        for t in turns
    ]
