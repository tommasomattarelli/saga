"""Campaign service — instantiates a campaign save from a library World (ADR 0008)."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config_loader import load_saga_config
from app.core.world_instantiation import instantiate_world
from app.core.world_library import ensure_library, world_path
from app.core.world_loader import WorldAsset, WorldLoadError, load_world
from app.core.world_validator import validate_world
from app.memory.world_state import migrate_world_state
from app.models.campaign import Campaign
from app.models.user import User
from app.schemas.campaign import CampaignCreate


def _max_depth() -> int:
    return int((load_saga_config().get("world") or {}).get("max_depth", 8))


def load_valid_world(slug: str) -> WorldAsset:
    ensure_library()
    path = world_path(slug)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"World '{slug}' not found in the library",
        )
    try:
        asset = load_world(path)
    except WorldLoadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"World '{slug}' failed to load: {exc}",
        ) from exc
    errors = validate_world(asset, max_depth=_max_depth())
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": f"World '{slug}' is invalid", "errors": errors[:20]},
        )
    return asset


async def create_campaign(db: AsyncSession, user: User, body: CampaignCreate) -> Campaign:
    asset = load_valid_world(body.world_id)
    baseline, world_state, quests = instantiate_world(asset)

    campaign = Campaign(
        user_id=user.id,
        world_slug=asset.root_slug,
        world_version=asset.meta.version,
        name=body.name,
        death_mode=body.death_mode,
        character_data=body.character_data,
        world_baseline=baseline,
        world_state=migrate_world_state(world_state),
        quests=quests,
        persona_xml=asset.scenario.dm_persona if asset.scenario else None,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign
