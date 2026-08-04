"""Hazard damage, healing, and the DM heal budget (ADR 0003 B7/B7b).

Classes are percentage ranges of the target's max HP rather than dice: weapons scale
with their wielder, hazards and cures are ownerless, and a percentage keeps them
relevant at every level. The LLM names a class; every number is drawn here.
"""

from __future__ import annotations

import random
from enum import StrEnum

from app.config_loader import load_saga_config
from app.core.dice import DiceOutcome
from app.memory.world_state import GameClock


class HazardClass(StrEnum):
    MINOR = "minor"
    SERIOUS = "serious"
    DEADLY = "deadly"


class HealClass(StrEnum):
    MINOR = "minor"
    STRONG = "strong"
    FULL = "full"


def _draw_percentage(bands: dict, key: str) -> float:
    low, high = bands[key]
    return random.uniform(min(low, high), max(low, high))


def draw_hazard_damage(hazard_class: HazardClass, outcome: DiceOutcome, max_hp: int) -> int:
    """Draw the hazard's bite, then let the reaction-roll tier dose it."""
    config = load_saga_config()["hazards"]
    scale = float(config["tier_scale"][outcome.value])
    if scale <= 0:
        return 0
    damage = _draw_percentage(config["classes"], hazard_class.value) * max_hp * scale
    return max(1, round(damage))


def draw_heal_amount(heal_class: HealClass, max_hp: int) -> int:
    config = load_saga_config()["healing"]
    return max(1, round(_draw_percentage(config["classes"], heal_class.value) * max_hp))


def hp_band(hp: dict) -> str:
    """Project {current, max} onto the band the DM narrates from — never a number."""
    maximum = int(hp.get("max", 0) or 0)
    if maximum <= 0:
        return ""
    ratio = int(hp.get("current", 0) or 0) / maximum
    bands = load_saga_config()["health"]["bands"]
    return next(
        (name for name, floor in sorted(bands.items(), key=lambda b: -b[1]) if ratio >= floor),
        "",
    )


def _current_day(world_state: dict) -> int:
    return GameClock(
        total_minutes=world_state.get("clock", {}).get("total_minutes", 0)
    ).current_day


def dm_heal_budget_left(world_state: dict) -> int:
    """DM-initiated heals still available today (B7b)."""
    cap = int(load_saga_config()["healing"]["dm_heal_cap"])
    log = world_state.get("dm_heals", {})
    if log.get("day") != _current_day(world_state):
        return cap
    return max(0, cap - int(log.get("used", 0)))


def consume_dm_heal(world_state: dict) -> dict:
    day = _current_day(world_state)
    log = world_state.get("dm_heals", {})
    used = int(log.get("used", 0)) if log.get("day") == day else 0
    return {**world_state, "dm_heals": {"day": day, "used": used + 1}}


PLAYER_TARGET = "player"


def reduce_damage(amount: int, target: dict | None) -> int:
    """The B6 reducer slot. ADR 0010 armor plugs in here; today nothing soaks."""
    return amount


def apply_hp_delta(
    world_state: dict,
    char_data: dict,
    target: str,
    delta: int,
) -> tuple[dict, dict, int, int]:
    """The single HP write path — player and NPC records alike (ADR 0003 B6).

    `target` is either PLAYER_TARGET or an NPC uuid. Damage passes the reducer slot;
    healing does not. An NPC reaching 0 is written dead here, so the 0009 writer works
    off the record rather than off an initiative list that no longer exists.
    """
    if target == PLAYER_TARGET:
        hp = dict(char_data.get("hp", {}))
        max_hp = int(hp.get("max", 10))
        current = int(hp.get("current", max_hp))
        hp["current"] = new_hp = max(0, min(max_hp, current + _reduced(delta, None)))
        return world_state, {**char_data, "hp": hp}, new_hp, max_hp

    record: dict | None = world_state.get("npcs", {}).get(target)
    if record is None:
        return world_state, char_data, 0, 0

    max_hp = int(record.get("max_hp") or 10)
    current = int(record.get("hp") or max_hp)
    record["hp"] = new_hp = max(0, min(max_hp, current + _reduced(delta, record)))
    if new_hp == 0:
        record["lifecycle"] = "dead"

    return world_state, char_data, new_hp, max_hp


def _reduced(delta: int, target: dict | None) -> int:
    """Damage passes the B6 reducer slot; healing does not."""
    return -reduce_damage(-delta, target) if delta < 0 else delta
