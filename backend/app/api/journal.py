import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.memory.history import history_ancestry
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
    campaign_result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.user_id == user.id)
        .execution_options(populate_existing=True)
    )
    campaign = campaign_result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    query = select(Turn).where(Turn.campaign_id == campaign_id)
    turns: Sequence[Turn]
    if campaign.memory_policy_id is not None:
        if campaign.active_continuation_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "campaign_history_inconsistent",
                    "message": "Campaign history is unavailable.",
                },
            )
        if campaign.active_head_turn_id is None:
            turns = []
        else:
            ancestry = history_ancestry(campaign_id, campaign.active_head_turn_id)
            result = await db.execute(
                query.join(ancestry, Turn.id == ancestry.c.id)
                .order_by(Turn.history_depth.desc())
                .offset(offset)
                .limit(limit)
            )
            turns = result.scalars().all()
            if not turns:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "campaign_history_inconsistent",
                        "message": "The active history head is unavailable.",
                    },
                )
    else:
        result = await db.execute(
            query.order_by(Turn.turn_number.desc(), Turn.id.desc()).offset(offset).limit(limit)
        )
        turns = result.scalars().all()
    return [
        {
            "turn_id": str(t.id),
            "turn_number": t.turn_number,
            "player_action": t.player_action,
            "narration": t.narration,
            "narration_segments": t.narration_segments,
            "dice_rolls": t.dice_rolls,
            "scene_mood": t.scene_mood,
            "created_at": t.created_at.isoformat(),
            "context_epoch": campaign.context_epoch,
        }
        for t in turns
    ]
