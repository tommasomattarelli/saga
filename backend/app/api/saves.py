import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.campaign import Campaign
from app.models.save import Save
from app.models.user import User
from app.schemas.save import SaveCreate, SaveResponse
from app.security.auth import get_current_user

router = APIRouter()

# TODO: endpoints implemented but not yet wired to the frontend (manual save/load — roadmap).


@router.get("/{campaign_id}", response_model=list[SaveResponse])
async def list_saves(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Save]:
    """List all saves."""
    campaign = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    if not campaign.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    result = await db.execute(
        select(Save).where(Save.campaign_id == campaign_id).order_by(Save.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{campaign_id}", response_model=SaveResponse, status_code=status.HTTP_201_CREATED)
async def create_save(
    campaign_id: uuid.UUID,
    body: SaveCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Save:
    """Create a manual save."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Block save during combat
    combat_active = (campaign.world_state or {}).get("combat_state", {}).get("active", False)
    if combat_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot save during combat",
        )

    save = Save(
        campaign_id=campaign.id,
        name=body.name,
        turn_number=campaign.turn_number,
        scene_summary=f"Turn {campaign.turn_number}",
        is_auto=False,
        campaign_snapshot={
            "character_data": campaign.character_data,
            "world_state": campaign.world_state,
            "quests": campaign.quests,
            "turn_number": campaign.turn_number,
        },
    )
    db.add(save)
    await db.commit()
    await db.refresh(save)
    return save


@router.post("/{campaign_id}/load/{save_id}")
async def load_save(
    campaign_id: uuid.UUID,
    save_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Restore campaign state."""
    result = await db.execute(
        select(Save).where(Save.id == save_id, Save.campaign_id == campaign_id)
    )
    save = result.scalar_one_or_none()
    if not save:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    snapshot = save.campaign_snapshot
    campaign.character_data = snapshot.get("character_data", {})
    campaign.world_state = snapshot.get("world_state", {})
    campaign.quests = snapshot.get("quests", {})
    campaign.turn_number = snapshot.get("turn_number", 0)
    await db.commit()

    return {"message": "Save loaded", "turn_number": campaign.turn_number}
