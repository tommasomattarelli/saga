import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.campaign import Campaign
from app.models.memory_fact import MemoryFact
from app.models.turn import Turn
from app.models.user import User
from app.security.auth import get_current_user

router = APIRouter()

# TODO: endpoint implemented but not yet wired to the frontend (campaign export/import — data-sovereignty pillar).


@router.get("/{campaign_id}")
async def export_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export a campaign as JSON."""
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

    facts_result = await db.execute(
        select(MemoryFact)
        .where(MemoryFact.campaign_id == campaign_id)
        .order_by(MemoryFact.turn_number)
    )
    memory_facts = facts_result.scalars().all()

    return {
        "campaign": {
            "name": campaign.name,
            "world_slug": campaign.world_slug,
            "world_version": campaign.world_version,
            "death_mode": campaign.death_mode,
            "character_data": campaign.character_data,
            "world_baseline": campaign.world_baseline,
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
        "memory_facts": [
            {
                "turn_number": f.turn_number,
                "entity_name": f.entity_name,
                "entity_type": f.entity_type,
                "content": f.content,
            }
            for f in memory_facts
        ],
    }
