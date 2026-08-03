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
