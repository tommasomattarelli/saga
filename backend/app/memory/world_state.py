"""World state manager — handles JSON state updates and schema migrations."""

from __future__ import annotations

import copy
from collections.abc import Callable
from uuid import uuid4

import structlog
from pydantic import BaseModel, computed_field

from app.core.npc_classes import DEFAULT_NPC_CLASSES, draw_statblock
from app.core.psychology import DEFAULT_PSYCHOLOGY, default_values
from app.models.npc import NpcEngineRecord

logger = structlog.get_logger()


class GameClock(BaseModel):
    total_minutes: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def current_hour(self) -> int:
        return (self.total_minutes // 60) % 24

    @computed_field  # type: ignore[prop-decorator]
    @property
    def current_day(self) -> int:
        return (self.total_minutes // (60 * 24)) + 1

    @computed_field  # type: ignore[prop-decorator]
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

    @computed_field  # type: ignore[prop-decorator]
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
        "clock",
        "narrative",
        "fate_interventions_left",
        "player_position",
        "node_status",
        "edge_overrides",
        "consumed_encounters",
        "pending_travel",
    }
)


CURRENT_SCHEMA_VERSION: int = 8

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


@_register_migration(3)
def _migrate_v3_to_v4(state: dict) -> dict:
    state.setdefault(
        "combat_state",
        {
            "active": False,
            "round": 0,
            "initiative_order": [],
            "current_turn_index": 0,
        },
    )
    state.setdefault("destino_lives", 3)
    state["meta"]["schema_version"] = 4
    return state


@_register_migration(4)
def _migrate_v4_to_v5(state: dict) -> dict:
    # ADR 0008: hierarchical world overlay containers (C11). Old flat-location
    # saves gain the keys but not a baseline — pre-1.0, no such saves exist (J2).
    state.setdefault("player_position", None)
    state.setdefault("node_status", {})
    state.setdefault("edge_overrides", [])
    state.setdefault("consumed_encounters", {})
    state["meta"]["schema_version"] = 5
    return state


@_register_migration(5)
def _migrate_v5_to_v6(state: dict) -> dict:
    # ADR 0005: multi-axis psychology. No scalar lift — dev volume wiped,
    # pre-1.0, no such saves exist (C2). met_player=True: never retro-amplify.
    defaults = default_values(DEFAULT_PSYCHOLOGY)
    for npc in state.get("npcs", {}).values():
        npc.setdefault("psychology", dict(defaults))
        npc.setdefault("met_player", True)
        npc.pop("disposition_toward_player", None)
    state["meta"]["schema_version"] = 6
    return state


@_register_migration(6)
def _migrate_v6_to_v7(state: dict) -> dict:
    # ADR 0009 F4: UUID identity + engine/traits split. Defensive — pre-1.0
    # dev saves wiped (J2); normalizes any stray data. Order matters:
    # name backfill from the old dict key MUST precede the rekey.
    engine_keys = set(NpcEngineRecord.model_fields)
    rekeyed: dict[str, dict] = {}
    for old_key, npc in state.get("npcs", {}).items():
        npc.setdefault("name", old_key)
        status = npc.pop("status", "alive")
        if npc.pop("is_dead", False):
            status = "dead"
        npc.setdefault("lifecycle", status if status in ("alive", "dead", "removed") else "alive")
        npc.setdefault("condition", None)
        npc.setdefault("slug", None)
        traits = npc.setdefault("traits", {})
        for key in [k for k in npc if k not in engine_keys]:
            traits[key] = npc.pop(key)
        rekeyed[str(uuid4())] = npc
    state["npcs"] = rekeyed
    state["meta"]["schema_version"] = 7
    return state


@_register_migration(7)
def _migrate_v7_to_v8(state: dict) -> dict:
    # ADR 0003 F: combat stops being a mode, so `combat_state` goes; everyone
    # hittable is an NPC record, so every record gains a statblock backfilled from
    # its class template. A save frozen mid-fight loses the in-flight combatants —
    # accepted pre-1.0 (0008-J2). auto_created stays False: these predate the mook
    # hook, and only what the engine invented is ever prunable (B2).
    state.pop("combat_state", None)
    for npc in state.get("npcs", {}).values():
        npc.setdefault("auto_created", False)
        if npc.get("max_hp") is None:
            npc.update(draw_statblock(npc.get("npc_class") or "", DEFAULT_NPC_CLASSES))
    # B8 renames the death modes away, and the counter with them.
    state["fate_interventions_left"] = state.pop("destino_lives", 3)
    state["meta"]["schema_version"] = 8
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
    return _expire_node_statuses(state)


def _expire_node_statuses(state: dict) -> dict:
    """Drop timed node statuses whose duration has elapsed (ADR 0008 G4)."""
    statuses = state.get("node_status")
    if not statuses:
        return state
    now = state["clock"]["total_minutes"]
    expired = [
        node_id
        for node_id, entry in statuses.items()
        if entry.get("duration_minutes") is not None
        and now >= entry.get("applied_at", 0) + entry["duration_minutes"]
    ]
    for node_id in expired:
        del statuses[node_id]
    return state
