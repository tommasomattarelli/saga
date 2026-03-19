"""Save service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.save import Save


async def get_campaign_saves(campaign_id: uuid.UUID, db: AsyncSession) -> list[Save]:
    """Get all saves for a campaign, ordered by most recent."""
    result = await db.execute(
        select(Save).where(Save.campaign_id == campaign_id).order_by(Save.created_at.desc())
    )
    return list(result.scalars().all())
