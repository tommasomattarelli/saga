"""World state manager — handles JSON state updates and schema migrations."""

from __future__ import annotations

import copy
from collections.abc import Callable

import structlog
from pydantic import BaseModel, computed_field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign

logger = structlog.get_logger()


class GameClock(BaseModel):
    total_minutes: int = 0

    @computed_field
    @property
    def current_hour(self) -> int:
        return (self.total_minutes // 60) % 24

    @computed_field
    @property
    def current_day(self) -> int:
        return (self.total_minutes // (60 * 24)) + 1

    @computed_field
    @property
    def current_season(self) -> str:
        day = self.current_day
        cycle = (day - 1) % 120
        if cycle < 30:
            return "spring"
        if cycle < 60:
            return "summer"
        if cycle < 90:
            return "autumn"
        return "winter"

    @computed_field
    @property
    def time_of_day(self) -> str:
        h = self.current_hour
        if 6 <= h < 12:
            return "morning"
        if 12 <= h < 17:
            return "afternoon"
        if 17 <= h < 21:
            return "evening"
        return "night"


ALLOWED_WORLD_STATE_KEYS: frozenset[str] = frozenset(
    {
        "meta",
        "locations",
        "factions",
        "npcs",
        "companions",
        "time_of_day",
        "weather",
        "global_flags",
        "clock",
        "narrative",
    }
)


CURRENT_SCHEMA_VERSION: int = 3

_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


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


@_register_migration(1)
def _migrate_v1_to_v2(state: dict) -> dict:
    if "clock" not in state:
        state["clock"] = {
            "total_minutes": 480,  # start at 8:00 AM
        }
    state["meta"]["schema_version"] = 2
    return state


@_register_migration(2)
def _migrate_v2_to_v3(state: dict) -> dict:
    state.setdefault("npcs", {})
    state.setdefault("companions", {})
    state.setdefault("narrative", {"event_log": []})
    state["meta"]["schema_version"] = 3
    return state


def migrate_world_state(state: dict) -> dict:
    """Apply pending schema migrations to a world state dict."""
    state = copy.deepcopy(state)

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

    def _deep_merge(d1: dict, d2: dict) -> dict:
        result = copy.deepcopy(d1)
        for k, v in d2.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    return _deep_merge(current, updates)


def advance_game_clock(world_state: dict, minutes: int) -> dict:
    """Advance the game clock by the given minutes and sync derived fields."""
    state = copy.deepcopy(world_state)
    clock_data = state.get("clock", {"total_minutes": 480})
    clock = GameClock(total_minutes=clock_data["total_minutes"] + minutes)
    state["clock"] = clock.model_dump()
    state["time_of_day"] = clock.time_of_day
    if "meta" in state:
        state["meta"]["current_season"] = clock.current_season
    return state


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
