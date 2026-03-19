"""Session recap generator."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.turn import Turn


async def generate_recap(
    campaign: Campaign,
    db: AsyncSession,
    num_turns: int = 5,
) -> str:
    """Generate a recap of recent events for session continuity.

    Used when a player returns to a campaign after a break.
    """
    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign.id)
        .order_by(Turn.turn_number.desc())
        .limit(num_turns)
    )
    recent_turns = list(reversed(result.scalars().all()))

    if not recent_turns:
        return "Your adventure is about to begin..."

    recap_parts = ["When last we left our story..."]
    for turn in recent_turns:
        summary = turn.summary or turn.narration[:150]
        recap_parts.append(f"- {summary}")

    return "\n".join(recap_parts)
