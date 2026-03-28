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


@_register_handler("combat_start")
def _handle_combat_start(state: dict, update: dict, char_data: dict) -> dict:
    """Initialize combat state when the DM signals combat begins."""
    from app.core.dice import roll_dice

    change = update.get("change", {})
    enemies_data = change.get("enemies", []) if isinstance(change, dict) else []

    initiative_order: list[dict] = []

    # Player initiative
    dex_mod = 0
    abilities = char_data.get("abilities", {})
    if "DEX" in abilities or "dexterity" in abilities:
        dex_score = abilities.get("DEX", abilities.get("dexterity", 10))
        dex_mod = (dex_score - 10) // 2
    player_init = roll_dice("1d20").total + dex_mod
    initiative_order.append(
        {
            "name": char_data.get("name", "Player"),
            "initiative": player_init,
            "hp": char_data.get("hp", {}).get("current", 10),
            "max_hp": char_data.get("hp", {}).get("max", 10),
            "type": "player",
        }
    )

    # Enemy initiatives
    for enemy in enemies_data:
        enemy_name = enemy.get("name", "Enemy") if isinstance(enemy, dict) else str(enemy)
        enemy_hp = enemy.get("hp", 10) if isinstance(enemy, dict) else 10
        enemy_max = enemy.get("max_hp", enemy_hp) if isinstance(enemy, dict) else enemy_hp
        enemy_init = roll_dice("1d20").total
        initiative_order.append(
            {
                "name": enemy_name,
                "initiative": enemy_init,
                "hp": enemy_hp,
                "max_hp": enemy_max,
                "type": "enemy",
            }
        )

    # Sort by initiative descending
    initiative_order.sort(key=lambda c: c["initiative"], reverse=True)

    state["combat_state"] = {
        "active": True,
        "round": 1,
        "initiative_order": initiative_order,
        "current_turn_index": 0,
    }
    return state


@_register_handler("combat_end")
def _handle_combat_end(state: dict, update: dict, char_data: dict) -> dict:
    """Reset combat state when combat ends."""
    state["combat_state"] = {
        "active": False,
        "round": 0,
        "initiative_order": [],
        "current_turn_index": 0,
    }
    return state


@_register_handler("combat_damage")
def _handle_combat_damage(state: dict, update: dict, char_data: dict) -> dict:
    """Apply damage to a combatant. Negative change = damage, positive = healing."""
    target = update.get("target", "")
    change = int(update.get("change", 0))

    combat = state.get("combat_state", {})
    initiative_order = combat.get("initiative_order", [])

    for combatant in initiative_order:
        if combatant["name"].lower() == target.lower():
            if combatant["type"] == "player":
                # Update character_data HP (source of truth for player)
                hp = char_data.get("hp", {})
                current = hp.get("current", hp.get("max", 10))
                max_hp = hp.get("max", 10)
                hp["current"] = max(0, min(max_hp, current + change))
                char_data["hp"] = hp
                # Sync to combat tracker
                combatant["hp"] = hp["current"]
            else:
                # Update enemy/companion HP in combat state
                combatant["hp"] = max(0, combatant["hp"] + change)
            break

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
                logger.warning(
                    "typed_update_handler_failed",
                    update_type=update_type,
                    update=update,
                    exc_info=True,
                )
        else:
            # Fallback: treat as generic world_state merge
            target = update.get("target", update.get("key", ""))
            value = update.get("value", update.get("change"))
            if target and value is not None:
                state = merge_world_state(state, {target: value})
                logger.debug(
                    "typed_update_generic_fallback", update_type=update_type, target=target
                )

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
