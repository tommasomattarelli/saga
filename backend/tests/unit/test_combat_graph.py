"""Unit tests for app/core/combat/combat_graph.py."""

from __future__ import annotations

from app.core.combat.combat_graph import init_combat_node


def _make_state(**overrides) -> dict:
    base: dict = {
        "messages": [],
        "world_state": {},
        "char_data": {},
        "player_action": "attack",
        "campaign_id": "test",
        "narration": "",
        "step_count": 0,
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "system_prompt": "",
        "model_config": {},
        "model_used": "gpt-4",
        "importance_score": 0,
        "death_event": None,
    }
    base.update(overrides)
    return base


class TestInitCombatNode:
    def test_sets_combat_active(self):
        state = _make_state(
            world_state={"_pending_combat_enemies": []},
            char_data={"name": "Hero", "abilities": {"DEX": 10}},
        )
        result = init_combat_node(state)
        assert result["world_state"]["combat_state"]["active"] is True

    def test_removes_pending_enemies_key(self):
        state = _make_state(
            world_state={"_pending_combat_enemies": []},
            char_data={"name": "Hero"},
        )
        result = init_combat_node(state)
        assert "_pending_combat_enemies" not in result["world_state"]

    def test_player_in_initiative_order(self):
        state = _make_state(
            world_state={"_pending_combat_enemies": []},
            char_data={"name": "Aldric", "abilities": {"DEX": 14}},
        )
        result = init_combat_node(state)
        initiative_order = result["world_state"]["combat_state"]["initiative_order"]
        player_entries = [c for c in initiative_order if c["type"] == "player"]
        assert len(player_entries) == 1
        assert player_entries[0]["name"] == "Aldric"

    def test_enemies_added_to_initiative(self):
        enemies = [{"name": "Goblin", "hp": 8, "max_hp": 8}]
        state = _make_state(
            world_state={"_pending_combat_enemies": enemies},
            char_data={"name": "Hero", "abilities": {}},
        )
        result = init_combat_node(state)
        initiative_order = result["world_state"]["combat_state"]["initiative_order"]
        enemy_entries = [c for c in initiative_order if c["type"] == "enemy"]
        assert len(enemy_entries) == 1
        assert enemy_entries[0]["name"] == "Goblin"
        assert enemy_entries[0]["hp"] == 8

    def test_initiative_order_sorted_descending(self):
        enemies = [{"name": "Dragon", "hp": 100, "max_hp": 100}]
        state = _make_state(
            world_state={"_pending_combat_enemies": enemies},
            char_data={"name": "Hero"},
        )
        result = init_combat_node(state)
        order = result["world_state"]["combat_state"]["initiative_order"]
        initiatives = [c["initiative"] for c in order]
        assert initiatives == sorted(initiatives, reverse=True)

    def test_combat_state_fields(self):
        state = _make_state(
            world_state={"_pending_combat_enemies": []},
            char_data={"name": "Hero"},
        )
        result = init_combat_node(state)
        cs = result["world_state"]["combat_state"]
        assert cs["round"] == 1
        assert cs["current_turn_index"] == 0

    def test_string_enemy_gets_default_values(self):
        state = _make_state(
            world_state={"_pending_combat_enemies": ["Orc"]},
            char_data={"name": "Hero"},
        )
        result = init_combat_node(state)
        order = result["world_state"]["combat_state"]["initiative_order"]
        orc = next(c for c in order if c["name"] == "Orc")
        assert orc["hp"] == 10
        assert orc["type"] == "enemy"

    def test_dex_modifier_applied_to_player(self):
        # DEX 20 → modifier = 5, so min initiative = 6 (1+5)
        state = _make_state(
            world_state={"_pending_combat_enemies": []},
            char_data={"name": "Swift Hero", "abilities": {"DEX": 20}},
        )
        result = init_combat_node(state)
        order = result["world_state"]["combat_state"]["initiative_order"]
        player = next(c for c in order if c["type"] == "player")
        assert player["initiative"] >= 6

    def test_empty_pending_enemies_when_key_missing(self):
        state = _make_state(
            world_state={},
            char_data={"name": "Hero"},
        )
        result = init_combat_node(state)
        order = result["world_state"]["combat_state"]["initiative_order"]
        assert len(order) == 1  # just player
