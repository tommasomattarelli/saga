"""Unit tests for dynamic tool group resolver."""

from unittest.mock import patch

import pytest

_SAMPLE_CONFIG = {
    "tool_groups": {
        "core": {
            "always": True,
            "tools": [
                "move_to",
                "advance_time",
                "set_scene_mood",
                "log_event",
                "update_quest",
                "request_dice",
                "heal",
            ],
        },
        "combat_entry": {
            "always": True,
            "tools": ["start_combat"],
        },
        "combat": {
            "when": "combat_active",
            "tools": ["apply_damage", "end_combat"],
        },
        "social": {
            "when": "npcs_present",
            "tools": ["invoke_npc", "change_npc_psychology"],
        },
        "inventory": {
            "always": True,
            "tools": ["add_item", "remove_item"],
        },
    }
}


@pytest.fixture(autouse=True)
def patch_config():
    with patch("app.ai.tools.tool_groups.load_saga_config", return_value=_SAMPLE_CONFIG):
        yield


def test_resolve_from_state_always_tools():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state

    tools = resolve_active_tools_from_state(
        {"combat_state": {"active": False}, "npcs": {}, "companions": {}}
    )
    assert "move_to" in tools
    assert "add_item" in tools
    assert "start_combat" in tools
    # ADR 0003 A1 — every d20 check is available with no fight in sight.
    assert "request_dice" in tools
    assert "heal" in tools


def test_resolve_from_state_npcs_present():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state

    tools = resolve_active_tools_from_state(
        {"combat_state": {"active": False}, "npcs": {"Marta": {}}, "companions": {}}
    )
    assert "invoke_npc" in tools
    assert "change_npc_psychology" in tools


def test_resolve_from_state_no_npcs():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state

    tools = resolve_active_tools_from_state(
        {"combat_state": {"active": False}, "npcs": {}, "companions": {}}
    )
    assert "invoke_npc" not in tools


def test_get_tool_schemas_filtered():
    from app.ai.tools.dm_tools import get_tool_schemas

    all_schemas = get_tool_schemas()
    filtered = get_tool_schemas(allowed={"move_to", "add_item"})
    assert len(filtered) == 2
    names = {s["function"]["name"] for s in filtered}
    assert names == {"move_to", "add_item"}
    assert len(all_schemas) > len(filtered)
