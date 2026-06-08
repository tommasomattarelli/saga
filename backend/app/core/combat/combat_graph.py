"""Combat sub-graph for the LangGraph DM agent.

Handles initiative rolling and combat state initialisation.
The sub-graph is invoked from tools_node when start_combat is detected;
it returns immediately after setting combat_state.active = True so the
main graph can continue with combat tools unlocked.
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from app.core.dice import roll_dice
from app.core.dm.game_state import GameState

logger = structlog.get_logger()


def init_combat_node(state: GameState) -> dict[str, Any]:
    """Roll initiative for all combatants and set combat_state.active = True.

    The enemies list is carried via world_state["_pending_combat_enemies"],
    placed there by tools_node before invoking this sub-graph.
    """
    world_state = dict(state["world_state"])
    char_data = state["char_data"]

    enemies_data: list[dict] = world_state.pop("_pending_combat_enemies", [])

    # Player initiative (DEX modifier)
    abilities = char_data.get("abilities", {})
    dex_score = abilities.get("DEX", abilities.get("dexterity", 10))
    dex_mod = (dex_score - 10) // 2
    player_init = roll_dice("1d20").total + dex_mod

    initiative_order: list[dict] = [
        {
            "name": char_data.get("name", "Player"),
            "initiative": player_init,
            "dex_mod": dex_mod,
            "hp": char_data.get("hp", {}).get("current", 10),
            "max_hp": char_data.get("hp", {}).get("max", 10),
            "type": "player",
        }
    ]

    for enemy in enemies_data:
        name = enemy.get("name", "Enemy") if isinstance(enemy, dict) else str(enemy)
        hp = enemy.get("hp", 10) if isinstance(enemy, dict) else 10
        max_hp = enemy.get("max_hp", hp) if isinstance(enemy, dict) else hp
        initiative_order.append(
            {
                "name": name,
                "initiative": roll_dice("1d20").total,
                "dex_mod": enemy.get("dex_mod", 0) if isinstance(enemy, dict) else 0,
                "hp": hp,
                "max_hp": max_hp,
                "type": "enemy",
            }
        )

    # Deterministic order: initiative desc, then DEX modifier desc, then name (B-L5)
    initiative_order.sort(key=lambda c: (-c["initiative"], -c.get("dex_mod", 0), c["name"]))

    world_state["combat_state"] = {
        "active": True,
        "round": 1,
        "initiative_order": initiative_order,
        "current_turn_index": 0,
    }

    logger.info(
        "combat_initialised",
        combatants=[c["name"] for c in initiative_order],
    )

    return {"world_state": world_state}


def build_combat_graph() -> Any:
    """Return a compiled combat sub-graph."""
    builder: StateGraph = StateGraph(GameState)
    builder.add_node("init_combat", init_combat_node)
    builder.set_entry_point("init_combat")
    builder.add_edge("init_combat", END)
    return builder.compile()


combat_graph = build_combat_graph()
