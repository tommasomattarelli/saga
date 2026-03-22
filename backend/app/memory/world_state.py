"""World state manager — handles JSON state updates and schema migrations."""

from __future__ import annotations

import copy

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign

logger = structlog.get_logger()


ALLOWED_WORLD_STATE_KEYS: frozenset[str] = frozenset(
    {
        "meta",  # schema_version, world_name, current_season
        "locations",  # location state (visited, discovered, status)
        "factions",  # faction disposition scores
        "npcs",  # per-NPC state (alive/dead, mood, known info)
        "companions",  # companion HP, loyalty, trust, mood
        "time_of_day",  # "morning" | "afternoon" | "evening" | "night"
        "weather",  # current weather string
        "global_flags",  # arbitrary boolean flags set by story arcs
    }
)


CURRENT_SCHEMA_VERSION: int = 1

# Map from source version → migration function
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}  # noqa: F821  populated below


def _register_migration(from_version: int):

    def decorator(fn):
        _MIGRATIONS[from_version] = fn
        return fn

    return decorator




@_register_migration(0)
def _migrate_v0_to_v1(state: dict) -> dict:
    if "meta" not in state:
        state["meta"] = {}
    state["meta"].setdefault("schema_version", 1)
    state["meta"].setdefault("world_name", "Unknown Land")
    state["meta"].setdefault("current_season", "spring")
    return state




def migrate_world_state(state: dict) -> dict:
    """Apply pending schema migrations to a world state dict."""
    state = copy.deepcopy(state)

    # Detect version — campaigns without meta/schema_version are treated as v0
    current_version: int = state.get("meta", {}).get("schema_version", 0)

    if current_version == CURRENT_SCHEMA_VERSION:
        return state   

    while current_version < CURRENT_SCHEMA_VERSION:
        migration_fn = _MIGRATIONS.get(current_version)
        if migration_fn is None:
            logger.error(
                "world_state_migration_missing",
                from_version=current_version,
                to_version=current_version + 1,
            )
            break
        logger.info(
            "world_state_migrating",
            from_version=current_version,
            to_version=current_version + 1,
        )
        state = migration_fn(state)
        current_version += 1

    state.setdefault("meta", {})["schema_version"] = CURRENT_SCHEMA_VERSION
    return state


def validate_world_state(state: dict) -> dict:
    """Strip any top-level keys not in ALLOWED_WORLD_STATE_KEYS."""
    rejected = set(state.keys()) - ALLOWED_WORLD_STATE_KEYS
    if rejected:
        logger.warning(
            "world_state_invalid_keys_stripped",
            stripped_keys=sorted(rejected),
        )
    return {k: v for k, v in state.items() if k in ALLOWED_WORLD_STATE_KEYS}


def merge_world_state(current: dict, updates: dict) -> dict:
    """Deep merge world state updates into current state."""
    updates = validate_world_state(updates)
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
    current = migrate_world_state(campaign.world_state)
    campaign.world_state = merge_world_state(current, updates)
    await db.flush()
    return campaign.world_state
