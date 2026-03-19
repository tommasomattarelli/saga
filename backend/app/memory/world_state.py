"""World state manager - handles JSON state updates."""

import copy

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign


def merge_world_state(current: dict, updates: dict) -> dict:
    """Deep merge world state updates into current state."""
    result = copy.deepcopy(current)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_world_state(result[key], value)
        else:
            result[key] = value
    return result


async def apply_world_updates(
    campaign: Campaign,
    updates: dict,
    db: AsyncSession,
) -> dict:
    """Apply world state updates to a campaign."""
    campaign.world_state = merge_world_state(campaign.world_state, updates)
    await db.flush()
    return campaign.world_state
