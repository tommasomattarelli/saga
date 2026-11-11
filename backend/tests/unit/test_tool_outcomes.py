from types import SimpleNamespace
from unittest.mock import patch

from app.ai.tools.dm_tools import execute_tool

NPC_ID = "11111111-1111-1111-1111-111111111111"


def _npc_state() -> dict:
    return {
        "meta": {"current_location": "tavern"},
        "npcs": {
            NPC_ID: {
                "name": "Mirella",
                "lifecycle": "alive",
                "location": "tavern",
                "psychology": {"trust": 0},
                "traits": {"role": "healer"},
            }
        },
    }


def test_move_unavailable_is_rejected():
    result = execute_tool("move_to", {"location": "Elsewhere"}, {}, {})

    assert result.outcome == "rejected"


def test_invalid_quest_is_rejected():
    result = execute_tool(
        "update_quest", {"quest_id": "", "status": "active", "name": "Quest"}, {}, {}
    )

    assert result.outcome == "rejected"


def test_unknown_psychology_axis_is_rejected():
    result = execute_tool(
        "change_npc_psychology",
        {"npc": "Mirella", "changes": {"courage": 1}},
        _npc_state(),
        {},
    )

    assert result.outcome == "rejected"


def test_missing_psychology_npc_is_rejected():
    result = execute_tool(
        "change_npc_psychology",
        {"npc": "Unknown", "changes": {"trust": 1}},
        _npc_state(),
        {},
    )

    assert result.outcome == "rejected"


def test_update_npc_rejection_is_rejected_outcome():
    result = execute_tool(
        "update_npc", {"name": "Mirella", "updates": {"lifecycle": "dead"}}, _npc_state(), {}
    )

    assert result.outcome == "rejected"


def test_lifecycle_rejection_is_rejected():
    result = execute_tool("restore_npc", {"name": "Mirella"}, _npc_state(), {})

    assert result.outcome == "rejected"


def test_attack_domain_error_is_rejected():
    result = execute_tool("attack", {"attacker": "Nobody", "target": "Mirella"}, _npc_state(), {})

    assert result.outcome == "rejected"


def test_heal_domain_rejection_is_rejected():
    result = execute_tool(
        "heal",
        {"healer": "Mirella", "target": "Unknown", "heal_class": "minor"},
        _npc_state(),
        {"name": "Player", "hp": {"current": 5, "max": 10}},
    )

    assert result.outcome == "rejected"


def test_attack_miss_is_still_succeeded():
    miss = SimpleNamespace(
        error=None,
        damage=0,
        attacker="Player",
        target="Mirella",
        outcome=SimpleNamespace(value="miss"),
        target_hp=10,
        target_max_hp=10,
        target_died=False,
        world_state=_npc_state(),
        char_data={},
    )
    with patch("app.ai.tools.tools_resolution.resolve_attack", return_value=miss):
        result = execute_tool("attack", {"attacker": "Player", "target": "Mirella"}, {}, {})

    assert result.outcome == "succeeded"


def test_unknown_and_invalid_calls_are_rejected() -> None:
    assert execute_tool("missing", {}, {}, {}).outcome == "rejected"
    assert execute_tool("advance_time", {"minutes": "invalid"}, {}, {}).outcome == "rejected"


def test_technical_failure_is_explicit_and_sanitized() -> None:
    with patch(
        "app.ai.tools.tools_inventory.AddItem.execute",
        side_effect=RuntimeError("/internal/path: secret traceback"),
    ):
        result = execute_tool("add_item", {"name": "Key"}, {}, {})
    assert result.outcome == "failed"
    assert "/internal" not in result.description
    assert "RuntimeError" not in result.description
