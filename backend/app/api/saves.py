import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.dependencies import get_db
from app.models.campaign import Campaign
from app.models.save import Save
from app.models.user import User
from app.schemas.save import SaveCreate, SaveResponse
from app.security.auth import get_current_user
from app.services.save_service import SaveHistoryError, create_campaign_save, restore_campaign_save

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
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.user_id == user.id)
        .with_for_update()
        .options(raiseload("*"))
        .execution_options(populate_existing=True)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    try:
        save = await create_campaign_save(db, campaign, name=body.name)
    except SaveHistoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "campaign_history_inconsistent", "message": str(exc)},
        ) from exc
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
    campaign_result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.user_id == user.id)
        .with_for_update()
        .options(raiseload("*"))
        .execution_options(populate_existing=True)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    result = await db.execute(
        select(Save).where(Save.id == save_id, Save.campaign_id == campaign_id)
    )
    save = result.scalar_one_or_none()
    if not save:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    try:
        turn_number = await restore_campaign_save(db, campaign, save)
    except SaveHistoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "campaign_history_required", "message": str(exc)},
        ) from exc
    await db.commit()

    return {
        "message": "Save loaded",
        "turn_number": turn_number,
        "active_head_turn_id": str(campaign.active_head_turn_id)
        if campaign.active_head_turn_id
        else None,
        "context_epoch": campaign.context_epoch,
    }
