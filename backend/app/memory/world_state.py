"""World state manager — handles JSON state updates and schema migrations."""

from __future__ import annotations

import copy
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# World State schema — authoritative list of allowed top-level keys.
#
# Only these keys are persisted to the database.  Any other key that arrives
# via world_updates (e.g. a UI field that leaked from the frontend, or an
# unexpected AI hallucination) is silently stripped and logged as a warning.
#
# When adding a new game-world concept, extend this set AND add a v→v+1
# migration below so old saves get the new field with a sensible default.
# ---------------------------------------------------------------------------

ALLOWED_WORLD_STATE_KEYS: frozenset[str] = frozenset(
    {
        "meta",            # schema_version, world_name, current_season
        "locations",       # location state (visited, discovered, status)
        "factions",        # faction disposition scores
        "npcs",            # per-NPC state (alive/dead, mood, known info)
        "companions",      # companion HP, loyalty, trust, mood
        "time_of_day",     # "morning" | "afternoon" | "evening" | "night"
        "weather",         # current weather string
        "global_flags",    # arbitrary boolean flags set by story arcs
    }
)

#
# Every release that modifies the World State structure increments this
# constant.  On campaign load, ``migrate_world_state`` compares the stored
# ``meta.schema_version`` against CURRENT_SCHEMA_VERSION and applies
# sequential migration functions to bring old saves up to date.
#
# This is the JSON equivalent of Alembic: Alembic handles SQL schema,
# this migrator handles JSONB content.  Without it, every release that
# changes the World State breaks existing saved campaigns.
#
# Adding a new migration:
#   1. Increment CURRENT_SCHEMA_VERSION.
#   2. Write a function _migrate_vN_to_vN1(state: dict) -> dict.
#   3. Add it to _MIGRATIONS in order.
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION: int = 1

# Map from source version → migration function
_MIGRATIONS: dict[int, "Callable[[dict], dict]"] = {}  # noqa: F821  # populated below


def _register_migration(from_version: int):
    """Decorator to register a migration function."""
    def decorator(fn):
        _MIGRATIONS[from_version] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Migration functions — one per version step
# ---------------------------------------------------------------------------

@_register_migration(0)
def _migrate_v0_to_v1(state: dict) -> dict:
    """v0 → v1: introduce the ``meta`` block and seed base fields.

    Campaigns created before schema_version existed have no ``meta`` key.
    This migration adds it and back-fills the version to 1 so subsequent
    migrations can run cleanly.
    """
    if "meta" not in state:
        state["meta"] = {}
    state["meta"].setdefault("schema_version", 1)
    state["meta"].setdefault("world_name", "Unknown Land")
    state["meta"].setdefault("current_season", "spring")
    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def migrate_world_state(state: dict) -> dict:
    """Apply all pending schema migrations to a world state dict.

    Called once on campaign load (before any turn is processed).
    Mutates a deep copy — the original is never modified.

    Args:
        state: Raw world state as loaded from the DB.

    Returns:
        Up-to-date world state dict at CURRENT_SCHEMA_VERSION.
    """
    state = copy.deepcopy(state)

    # Detect version — campaigns without meta/schema_version are treated as v0
    current_version: int = state.get("meta", {}).get("schema_version", 0)

    if current_version == CURRENT_SCHEMA_VERSION:
        return state  # Already up to date — fast path

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

    # Ensure the stored version is always current after migration
    state.setdefault("meta", {})["schema_version"] = CURRENT_SCHEMA_VERSION
    return state


def validate_world_state(state: dict) -> dict:
    """Strip any top-level keys not in ALLOWED_WORLD_STATE_KEYS.

    This is the backend's last defence against UI state leaking into the
    database (e.g. ``sidePanel``, ``soundEnabled``) or unexpected keys
    hallucinated by the AI model.  The function is non-destructive: it
    returns a new dict and logs a warning for every stripped key so that
    developers notice the leak without crashing production.
    """
    rejected = set(state.keys()) - ALLOWED_WORLD_STATE_KEYS
    if rejected:
        logger.warning(
            "world_state_invalid_keys_stripped",
            stripped_keys=sorted(rejected),
        )
    return {k: v for k, v in state.items() if k in ALLOWED_WORLD_STATE_KEYS}


def merge_world_state(current: dict, updates: dict) -> dict:
    """Deep merge world state updates into current state.

    Strips any top-level key in *updates* that is not in
    ``ALLOWED_WORLD_STATE_KEYS`` before merging, so callers never need to
    validate separately.
    """
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
    """Apply world state updates to a campaign.

    Ensures the world state is migrated to the current schema before
    any update is applied.
    """
    # Migrate on first access for campaigns created before this version
    current = migrate_world_state(campaign.world_state)
    campaign.world_state = merge_world_state(current, updates)
    await db.flush()
    return campaign.world_state
