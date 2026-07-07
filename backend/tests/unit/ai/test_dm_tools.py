"""Unit tests for DM tool definitions and execution."""

from app.ai.tools.dm_tools import (
    VISIBLE_TOOLS,
    AddItem,
    ApplyDamage,
    ChangeNpcPsychology,
    EndCombat,
    LogEvent,
    MoveTo,
    RemoveItem,
    SetSceneMood,
    StartCombat,
    UpdateHp,
    UpdateQuest,
    execute_tool,
    get_tool_schemas,
)

# ── Schema generation ─────────────────────────────────────────────────────────


def test_get_tool_schemas_returns_all():
    schemas = get_tool_schemas()
    assert len(schemas) == 14
    names = {s["function"]["name"] for s in schemas}
    assert "start_combat" in names
    assert "request_dice" in names
    assert "invoke_npc" in names


def test_schema_openai_format():
    schema = StartCombat.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "start_combat"
    assert "parameters" in schema["function"]
    assert schema["function"]["parameters"]["type"] == "object"
    assert "enemies" in schema["function"]["parameters"]["properties"]


def test_visible_tools_set():
    assert "request_dice" in VISIBLE_TOOLS
    assert "apply_damage" in VISIBLE_TOOLS
    assert "start_combat" in VISIBLE_TOOLS
    assert "log_event" not in VISIBLE_TOOLS
    assert "change_npc_psychology" not in VISIBLE_TOOLS


# ── Combat tools ──────────────────────────────────────────────────────────────


def test_start_combat_initializes_state():
    enemies = [{"name": "Goblin", "hp": 10, "max_hp": 10}]
    tool = StartCombat(enemies=enemies)
    ws = {}
    cd = {"abilities": {"DEX": 14}, "hp": {"current": 20, "max": 20}, "name": "Hero"}
    result = tool.execute(ws, cd)
    assert result.world_state.get("combat_state", {}).get("active") is True
    order = result.world_state["combat_state"]["initiative_order"]
    names = [c["name"] for c in order]
    assert "Goblin" in names
    assert "Hero" in names


def test_end_combat_resets_state():
    ws = {"combat_state": {"active": True, "round": 3}}
    result = EndCombat().execute(ws, {})
    assert result.world_state["combat_state"]["active"] is False
    assert result.world_state["combat_state"]["round"] == 0


def test_apply_damage_reduces_hp():
    ws = {
        "combat_state": {
            "active": True,
            "initiative_order": [{"name": "Goblin", "hp": 15, "max_hp": 15, "type": "enemy"}],
            "current_turn_index": 0,
        }
    }
    cd = {}
    result = ApplyDamage(target="Goblin", amount=8).execute(ws, cd)
    order = result.world_state["combat_state"]["initiative_order"]
    goblin = next(c for c in order if c["name"] == "Goblin")
    assert goblin["hp"] == 7


# ── HP tool ───────────────────────────────────────────────────────────────────


def test_update_hp_heals_player():
    cd = {"hp": {"current": 5, "max": 20}}
    result = UpdateHp(change=8, reason="potion").execute({}, cd)
    assert result.char_data["hp"]["current"] == 13


def test_update_hp_clamps_to_max():
    cd = {"hp": {"current": 18, "max": 20}}
    result = UpdateHp(change=10, reason="overheal").execute({}, cd)
    assert result.char_data["hp"]["current"] == 20


def test_update_hp_clamps_to_zero():
    cd = {"hp": {"current": 3, "max": 20}}
    result = UpdateHp(change=-10, reason="trap").execute({}, cd)
    assert result.char_data["hp"]["current"] == 0


# ── Inventory tools ───────────────────────────────────────────────────────────


def test_add_item_appends_to_inventory():
    cd = {"inventory": []}
    result = AddItem(name="Torch", description="A wooden torch").execute({}, cd)
    names = [i["name"] for i in result.char_data["inventory"]]
    assert "Torch" in names


def test_remove_item_removes_from_inventory():
    cd = {"inventory": [{"name": "Sword", "quantity": 1}]}
    result = RemoveItem(name="Sword").execute({}, cd)
    assert all(i["name"] != "Sword" for i in result.char_data.get("inventory", []))


# ── World tools ───────────────────────────────────────────────────────────────


def _example_world():
    from pathlib import Path

    from app.core.world_instantiation import instantiate_world
    from app.core.world_loader import load_world

    world_dir = Path(__file__).parents[4] / "worlds" / "the-awakening"
    baseline, state, _ = instantiate_world(load_world(world_dir))
    return baseline, state


def test_move_to_travels_and_advances_clock():
    baseline, state = _example_world()
    result = MoveTo(location="Thornhaven").execute_with_baseline(state, {}, baseline)
    assert result.world_state["player_position"] == baseline["slug_map"]["thornhaven"]
    assert result.world_state["clock"]["total_minutes"] > state["clock"]["total_minutes"]
    assert "Thornhaven" in result.description


def test_move_to_rejects_unknown_place():
    baseline, state = _example_world()
    result = MoveTo(location="Atlantis").execute_with_baseline(state, {}, baseline)
    assert result.world_state is state or result.world_state == state
    assert "rejected" in result.description.lower()


def test_move_to_without_baseline_reports_no_map():
    result = MoveTo(location="Anywhere").execute({}, {})
    assert "no world map" in result.description.lower()


def test_update_quest_adds_active_quest():
    cd = {}
    result = UpdateQuest(
        name="Dragon Hunt", status="active", description="Find the dragon"
    ).execute({}, cd)
    quests = result.char_data.get("active_quests", [])
    assert any(q["name"] == "Dragon Hunt" for q in quests)


def test_update_quest_completes_quest():
    cd = {"active_quests": [{"name": "Dragon Hunt", "description": "..."}]}
    result = UpdateQuest(name="Dragon Hunt", status="completed").execute({}, cd)
    assert all(q["name"] != "Dragon Hunt" for q in result.char_data.get("active_quests", []))


def test_change_npc_psychology_updates_axes():
    ws = {"npcs": {"Grenda": {"name": "Grenda", "met_player": True, "psychology": {"trust": 0}}}}
    result = ChangeNpcPsychology(npc="Grenda", changes={"trust": 8}, reason="helped her").execute(
        ws, {}
    )
    assert result.world_state["npcs"]["Grenda"]["psychology"]["trust"] == 8
    assert "trust: 8 (neutral)" in result.description
    assert "(helped her)" in result.description


def test_change_npc_psychology_rejects_unknown_axis_with_candidates():
    ws = {"npcs": {"Grenda": {"name": "Grenda"}}}
    result = ChangeNpcPsychology(npc="Grenda", changes={"honor": 5}).execute(ws, {})
    assert "Unknown axis 'honor'" in result.description
    assert "trust, respect, affection, fear" in result.description
    assert result.world_state == ws  # state untouched on reject


def test_change_npc_psychology_uses_world_axes_from_baseline():
    baseline = {
        "taxonomy": {
            "psychology": {
                "axes": {
                    "honor": {
                        "range": [-50, 50],
                        "default": 0,
                        "bands": [{"min": -50, "label": "shamed"}, {"min": 0, "label": "honored"}],
                    }
                }
            }
        }
    }
    ws = {"npcs": {"Kira": {"name": "Kira", "met_player": True}}}
    result = ChangeNpcPsychology(npc="Kira", changes={"honor": 5}).execute_with_baseline(
        ws, {}, baseline
    )
    assert result.world_state["npcs"]["Kira"]["psychology"]["honor"] == 5
    reject = ChangeNpcPsychology(npc="Kira", changes={"trust": 5}).execute_with_baseline(
        ws, {}, baseline
    )
    assert "Unknown axis 'trust'" in reject.description


def test_log_event_appends_entry():
    ws = {}
    result = LogEvent(description="Player found the hidden passage").execute(ws, {})
    log = result.world_state.get("narrative", {}).get("event_log", [])
    assert any("hidden passage" in e.get("description", "") for e in log)


def test_set_scene_mood_valid():
    result = SetSceneMood(mood="combat_fury").execute({}, {})
    assert result.extra["mood"] == "combat_fury"
    assert result.world_state.get("scene_mood") == "combat_fury"


def test_set_scene_mood_invalid_falls_back_to_neutral():
    result = SetSceneMood(mood="not_a_real_mood").execute({}, {})
    assert result.extra["mood"] == "neutral"


# ── execute_tool helper ───────────────────────────────────────────────────────


def test_execute_tool_valid():
    baseline, state = _example_world()
    result = execute_tool("move_to", {"location": "Thornhaven"}, state, {}, baseline=baseline)
    assert result.world_state["player_position"] == baseline["slug_map"]["thornhaven"]


def test_execute_tool_unknown_returns_gracefully():
    result = execute_tool("nonexistent_tool", {}, {}, {})
    assert "Unknown tool" in result.description


def test_execute_tool_invalid_args_returns_gracefully():
    # start_combat requires enemies list — passing wrong type should not crash
    result = execute_tool("update_hp", {"change": "not_an_int"}, {}, {})
    assert "failed" in result.description.lower()
