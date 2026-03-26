"""Typed World State Updater — handler registry for structured updates."""

from __future__ import annotations

import copy
from collections.abc import Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.world_state import merge_world_state, migrate_world_state
from app.models.campaign import Campaign

logger = structlog.get_logger()

_HANDLERS: dict[str, Callable[[dict, dict, dict], dict]] = {}


def _register_handler(update_type: str):
    def decorator(fn: Callable[[dict, dict, dict], dict]):
        _HANDLERS[update_type] = fn
        return fn

    return decorator


@_register_handler("npc_disposition")
def _handle_npc_disposition(state: dict, update: dict, char_data: dict) -> dict:
    """Update an NPC's disposition toward the player."""
    target = update.get("target", "")
    change = update.get("change", 0)
    npcs = state.setdefault("npcs", {})
    if target not in npcs:
        npcs[target] = {"name": target, "disposition_toward_player": 0}
    current = npcs[target].get("disposition_toward_player", 0)
    npcs[target]["disposition_toward_player"] = max(-100, min(100, current + int(change)))
    return state


@_register_handler("hp_change")
def _handle_hp_change(state: dict, update: dict, char_data: dict) -> dict:
    """Adjust player HP, clamped to [0, max]."""
    change = int(update.get("change", 0))
    hp = char_data.get("hp", {})
    current = hp.get("current", hp.get("max", 10))
    max_hp = hp.get("max", 10)
    hp["current"] = max(0, min(max_hp, current + change))
    char_data["hp"] = hp
    return state


@_register_handler("inventory_change")
def _handle_inventory(state: dict, update: dict, char_data: dict) -> dict:
    """Add or remove an item from inventory."""
    action = update.get("change", "add") if isinstance(update.get("change"), str) else "add"
    target = update.get("target", "")
    inventory = char_data.setdefault("inventory", [])

    if action == "remove":
        char_data["inventory"] = [i for i in inventory if i.get("name") != target]
    else:
        description = update.get("description", "")
        inventory.append({"name": target, "quantity": 1, "description": description})
    return state


@_register_handler("quest_update")
def _handle_quest(state: dict, update: dict, char_data: dict) -> dict:
    """Update active/completed quests."""
    target = update.get("target", "")
    change = update.get("change", "active")
    state.setdefault("narrative", {"event_log": []})
    active_quests = char_data.setdefault("active_quests", [])

    if change == "completed":
        char_data["active_quests"] = [q for q in active_quests if q.get("name") != target]
    elif change == "active" and not any(q.get("name") == target for q in active_quests):
        active_quests.append({"name": target, "description": update.get("description", "")})
    return state


@_register_handler("companion_loyalty")
def _handle_companion_loyalty(state: dict, update: dict, char_data: dict) -> dict:
    """Adjust a companion's loyalty, clamped to [0, 100]."""
    target = update.get("target", "")
    change = int(update.get("change", 0))
    companions = state.setdefault("companions", {})
    if target in companions:
        current = companions[target].get("loyalty", 50)
        companions[target]["loyalty"] = max(0, min(100, current + change))
    return state


@_register_handler("reputation_change")
def _handle_reputation(state: dict, update: dict, char_data: dict) -> dict:
    """Adjust player reputation with a faction or group."""
    target = update.get("target", "")
    change = int(update.get("change", 0))
    reputation = char_data.setdefault("reputation", {})
    current = reputation.get(target, 0)
    reputation[target] = max(-100, min(100, current + change))
    return state


@_register_handler("event_log_entry")
def _handle_event_log(state: dict, update: dict, char_data: dict) -> dict:
    """Append an entry to the narrative event log."""
    narrative = state.setdefault("narrative", {"event_log": []})
    event_log = narrative.setdefault("event_log", [])
    event_log.append({"description": update.get("description", update.get("target", ""))})
    return state


def apply_typed_updates(
    world_state: dict,
    character_data: dict,
    updates: list[dict],
) -> tuple[dict, dict]:
    """Apply a list of typed updates. Returns (updated_world_state, updated_character_data).

    Each update dict should have: {"key": "update_type", "target": "...", "change": ..., ...}
    Falls back to generic merge for unknown types.
    """
    state = copy.deepcopy(world_state)
    char_data = copy.deepcopy(character_data) if character_data else {}

    for update in updates:
        update_type = update.get("key", update.get("type", ""))
        handler = _HANDLERS.get(update_type)

        if handler:
            try:
                state = handler(state, update, char_data)
            except Exception:
                logger.warning("typed_update_handler_failed", update_type=update_type, update=update, exc_info=True)
        else:
            # Fallback: treat as generic world_state merge
            target = update.get("target", update.get("key", ""))
            value = update.get("value", update.get("change"))
            if target and value is not None:
                state = merge_world_state(state, {target: value})
                logger.debug("typed_update_generic_fallback", update_type=update_type, target=target)

    return state, char_data


async def apply_typed_updates_to_campaign(
    campaign: Campaign,
    updates: list[dict],
    db: AsyncSession,
) -> None:
    """Apply typed updates directly to a campaign and flush."""
    current_state = migrate_world_state(campaign.world_state or {})
    current_char = campaign.character_data or {}

    new_state, new_char = apply_typed_updates(current_state, current_char, updates)

    campaign.world_state = new_state
    campaign.character_data = new_char
    await db.flush()
