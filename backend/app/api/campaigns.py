import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignResponse
from app.security.auth import get_current_user
from app.services import campaign_service

router = APIRouter()


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    return await campaign_service.create_campaign(db, user, body)


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Campaign]:
    """List all campaigns for current user."""
    result = await db.execute(
        select(Campaign).where(Campaign.user_id == user.id).order_by(Campaign.updated_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    """Get a single campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: uuid.UUID,
    new_status: CampaignStatus,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update campaign status."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = new_status
    await db.commit()
    return {"status": new_status}


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your campaign")
    await db.delete(campaign)
    await db.commit()


@router.get("/{campaign_id}/map")
async def get_campaign_map(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Read-only world map data (ADR 0008 B4): nodes, edges, player position."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    from app.core.world_access import WorldView

    baseline = campaign.world_baseline or {}
    overlay = campaign.world_state or {}
    view = WorldView(baseline, overlay)
    if not view.has_world:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="This campaign has no world map"
        )

    nodes = {
        node_id: {
            "name": node["name"],
            "kind": node["kind"],
            "scale": node.get("scale", "outdoor"),
            "position": node.get("position"),
            "parent": node.get("parent"),
            "children": node.get("children", []),
            "has_status": bool(overlay.get("node_status", {}).get(node_id)),
        }
        for node_id, node in baseline["nodes"].items()
    }
    edges = [
        {"from": e["from"], "to": e["to"], "mode": e.get("mode", "")}
        for e in view.edges().values()
    ]
    return {
        "root": baseline["root"],
        "player_position": overlay.get("player_position"),
        "nodes": nodes,
        "edges": edges,
    }
