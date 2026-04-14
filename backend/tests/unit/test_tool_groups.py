"""Unit tests for dynamic tool group resolver."""

from unittest.mock import MagicMock, patch

import pytest

from app.ai.tools.tool_groups import resolve_active_tools


def _make_campaign(world_state: dict) -> MagicMock:
    c = MagicMock()
    c.world_state = world_state
    return c


_SAMPLE_CONFIG = {
    "tool_groups": {
        "core": {
            "always": True,
            "tools": ["move_to", "advance_time", "set_scene_mood", "log_event", "update_quest"],
        },
        "combat_entry": {
            "always": True,
            "tools": ["start_combat"],
        },
        "combat": {
            "when": "combat_active",
            "tools": ["request_dice", "apply_damage", "end_combat", "update_hp"],
        },
        "social": {
            "when": "npcs_present",
            "tools": ["invoke_npc", "change_npc_disposition"],
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


def test_core_and_inventory_always_active():
    campaign = _make_campaign({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    tools = resolve_active_tools(campaign)
    assert "move_to" in tools
    assert "add_item" in tools
    assert "remove_item" in tools


def test_combat_tools_inactive_when_no_combat():
    campaign = _make_campaign({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    tools = resolve_active_tools(campaign)
    assert "apply_damage" not in tools
    assert "end_combat" not in tools
    # start_combat is in combat_entry group (always active) so the DM can open combat
    assert "start_combat" in tools


def test_start_combat_always_available():
    """combat_entry group exposes start_combat regardless of combat state."""
    campaign = _make_campaign({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    tools = resolve_active_tools(campaign)
    assert "start_combat" in tools


def test_combat_tools_active_when_combat():
    campaign = _make_campaign({"combat_state": {"active": True}, "npcs": {}, "companions": {}})
    tools = resolve_active_tools(campaign)
    assert "apply_damage" in tools
    assert "end_combat" in tools
    assert "request_dice" in tools


def test_social_tools_inactive_when_no_npcs():
    campaign = _make_campaign({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    tools = resolve_active_tools(campaign)
    assert "invoke_npc" not in tools
    assert "change_npc_disposition" not in tools


def test_social_tools_active_when_npcs_present():
    campaign = _make_campaign({
        "combat_state": {"active": False},
        "npcs": {"Marta": {"role": "innkeeper"}},
        "companions": {},
    })
    tools = resolve_active_tools(campaign)
    assert "invoke_npc" in tools
    assert "change_npc_disposition" in tools


def test_all_groups_active_simultaneously():
    campaign = _make_campaign({
        "combat_state": {"active": True},
        "npcs": {"Marta": {}},
        "companions": {"Lyra": {}},
    })
    tools = resolve_active_tools(campaign)
    assert "move_to" in tools       # core
    assert "add_item" in tools      # inventory
    assert "apply_damage" in tools  # combat
    assert "invoke_npc" in tools    # social


def test_returns_set():
    campaign = _make_campaign({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    result = resolve_active_tools(campaign)
    assert isinstance(result, set)


def test_resolve_from_state_always_tools():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state
    tools = resolve_active_tools_from_state({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    assert "move_to" in tools
    assert "add_item" in tools
    assert "start_combat" in tools


def test_resolve_from_state_combat_active():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state
    tools = resolve_active_tools_from_state({"combat_state": {"active": True}, "npcs": {}, "companions": {}})
    assert "apply_damage" in tools
    assert "end_combat" in tools
    assert "request_dice" in tools


def test_resolve_from_state_npcs_present():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state
    tools = resolve_active_tools_from_state({"combat_state": {"active": False}, "npcs": {"Marta": {}}, "companions": {}})
    assert "invoke_npc" in tools
    assert "change_npc_disposition" in tools


def test_resolve_from_state_no_npcs():
    from app.ai.tools.tool_groups import resolve_active_tools_from_state
    tools = resolve_active_tools_from_state({"combat_state": {"active": False}, "npcs": {}, "companions": {}})
    assert "invoke_npc" not in tools


def test_get_tool_schemas_filtered():
    from app.ai.tools.dm_tools import get_tool_schemas
    all_schemas = get_tool_schemas()
    filtered = get_tool_schemas(allowed={"move_to", "add_item"})
    assert len(filtered) == 2
    names = {s["function"]["name"] for s in filtered}
    assert names == {"move_to", "add_item"}
    assert len(all_schemas) > len(filtered)
