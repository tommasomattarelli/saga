"""Campaign service - business logic for campaign management."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.world_state import migrate_world_state
from app.models.campaign import Campaign, CampaignStatus
from app.models.template import Template
from app.models.user import User
from app.schemas.campaign import CampaignCreate


def build_initial_world_state(template: Template) -> dict:
    content = template.content
    world = content.get("world", {})
    opening = content.get("opening", {})

    locations = {
        loc["name"]: {k: v for k, v in loc.items() if k != "name"}
        for loc in world.get("locations", [])
    }
    npcs = {
        npc["name"]: {
            **{k: v for k, v in npc.items() if k != "name"},
            "disposition": 0,
            "last_interactions": [],
        }
        for npc in world.get("npcs", [])
    }
    companions = {
        comp["name"]: {k: v for k, v in comp.items() if k != "name"}
        for comp in world.get("companions", [])
    }
    factions = {
        fact["name"]: {k: v for k, v in fact.items() if k != "name"}
        for fact in world.get("factions", [])
    }

    return {
        "meta": {
            "setting": world.get("setting", ""),
            "current_location": opening.get("location", ""),
        },
        "locations": locations,
        "npcs": npcs,
        "companions": companions,
        "factions": factions,
        "time_of_day": opening.get("time_of_day", "morning"),
        "weather": opening.get("weather", "clear"),
    }


def build_initial_quests(template: Template) -> dict:
    opening = template.content.get("opening", {})
    initial_quests = opening.get("initial_quests", [])
    return {"active": initial_quests} if initial_quests else {}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


async def create_campaign(db: AsyncSession, user: User, body: CampaignCreate) -> Campaign:
    if _is_uuid(body.template_id):
        result = await db.execute(select(Template).where(Template.id == uuid.UUID(body.template_id)))
    else:
        result = await db.execute(select(Template).where(Template.slug == body.template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{body.template_id}' not found",
        )

    initial_state = build_initial_world_state(template)
    seeded_world_state = migrate_world_state(initial_state)
    initial_quests = build_initial_quests(template)

    campaign = Campaign(
        user_id=user.id,
        template_id=template.slug,
        name=body.name,
        death_mode=body.death_mode,
        character_data=body.character_data,
        world_state=seeded_world_state,
        quests=initial_quests,
        persona_preset=template.persona_preset,
        persona_xml=template.persona_xml,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


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
