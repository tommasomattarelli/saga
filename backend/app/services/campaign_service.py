"""Campaign service - business logic for campaign management."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus


async def get_user_campaigns(user_id: uuid.UUID, db: AsyncSession) -> list[Campaign]:
    """Get all campaigns for a user."""
    result = await db.execute(
        select(Campaign).where(Campaign.user_id == user_id).order_by(Campaign.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_active_campaign(user_id: uuid.UUID, db: AsyncSession) -> Campaign | None:
    """Get the user's most recently updated active campaign."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.user_id == user_id, Campaign.status == CampaignStatus.ACTIVE)
        .order_by(Campaign.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
