"""Tests for combat typed world-state update handlers."""

from app.memory.updater import apply_typed_updates


def _base_state() -> dict:
    return {
        "combat_state": {
            "active": False,
            "round": 0,
            "initiative_order": [],
            "current_turn_index": 0,
        },
        "destino_lives": 3,
    }


def _char(current_hp: int = 10, max_hp: int = 10) -> dict:
    return {
        "name": "Hero",
        "hp": {"current": current_hp, "max": max_hp},
        "abilities": {"DEX": 14},
    }


class TestCombatStart:
    def test_combat_becomes_active(self):
        state = _base_state()
        updates = [
            {
                "key": "combat_start",
                "target": "",
                "change": {"enemies": [{"name": "Goblin", "hp": 7, "max_hp": 7}]},
            }
        ]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        assert new_state["combat_state"]["active"] is True

    def test_round_starts_at_1(self):
        state = _base_state()
        updates = [{"key": "combat_start", "target": "", "change": {"enemies": []}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        assert new_state["combat_state"]["round"] == 1

    def test_player_included_in_initiative(self):
        state = _base_state()
        updates = [{"key": "combat_start", "target": "", "change": {"enemies": []}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        names = [c["name"] for c in new_state["combat_state"]["initiative_order"]]
        assert "Hero" in names

    def test_enemies_included_in_initiative(self):
        state = _base_state()
        updates = [
            {
                "key": "combat_start",
                "target": "",
                "change": {
                    "enemies": [
                        {"name": "Orc", "hp": 15, "max_hp": 15},
                        {"name": "Troll", "hp": 30, "max_hp": 30},
                    ]
                },
            }
        ]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        names = [c["name"] for c in new_state["combat_state"]["initiative_order"]]
        assert "Orc" in names
        assert "Troll" in names

    def test_initiative_order_sorted_descending(self):
        state = _base_state()
        updates = [
            {
                "key": "combat_start",
                "target": "",
                "change": {
                    "enemies": [
                        {"name": "E1", "hp": 5, "max_hp": 5},
                        {"name": "E2", "hp": 5, "max_hp": 5},
                    ]
                },
            }
        ]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        initiatives = [c["initiative"] for c in new_state["combat_state"]["initiative_order"]]
        assert initiatives == sorted(initiatives, reverse=True)

    def test_player_type_is_player(self):
        state = _base_state()
        updates = [{"key": "combat_start", "target": "", "change": {"enemies": []}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        player = next(
            c for c in new_state["combat_state"]["initiative_order"] if c["type"] == "player"
        )
        assert player is not None


class TestCombatEnd:
    def test_combat_becomes_inactive(self):
        state = _base_state()
        state["combat_state"]["active"] = True
        state["combat_state"]["round"] = 3
        updates = [{"key": "combat_end", "target": "", "change": {}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        assert new_state["combat_state"]["active"] is False

    def test_initiative_order_cleared(self):
        state = _base_state()
        state["combat_state"]["initiative_order"] = [
            {"name": "Goblin", "hp": 1, "max_hp": 7, "initiative": 12, "type": "enemy"}
        ]
        updates = [{"key": "combat_end", "target": "", "change": {}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        assert new_state["combat_state"]["initiative_order"] == []

    def test_round_reset_to_zero(self):
        state = _base_state()
        state["combat_state"]["round"] = 5
        updates = [{"key": "combat_end", "target": "", "change": {}}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        assert new_state["combat_state"]["round"] == 0


class TestCombatDamage:
    def _active_state(self) -> dict:
        state = _base_state()
        state["combat_state"] = {
            "active": True,
            "round": 1,
            "current_turn_index": 0,
            "initiative_order": [
                {"name": "Hero", "hp": 10, "max_hp": 10, "initiative": 15, "type": "player"},
                {"name": "Goblin", "hp": 7, "max_hp": 7, "initiative": 10, "type": "enemy"},
            ],
        }
        return state

    def test_enemy_takes_damage(self):
        state = self._active_state()
        updates = [{"key": "combat_damage", "target": "Goblin", "change": -3}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        goblin = next(
            c for c in new_state["combat_state"]["initiative_order"] if c["name"] == "Goblin"
        )
        assert goblin["hp"] == 4

    def test_enemy_hp_does_not_go_below_zero(self):
        state = self._active_state()
        updates = [{"key": "combat_damage", "target": "Goblin", "change": -99}]
        new_state, _ = apply_typed_updates(state, _char(), updates)
        goblin = next(
            c for c in new_state["combat_state"]["initiative_order"] if c["name"] == "Goblin"
        )
        assert goblin["hp"] == 0

    def test_player_takes_damage_reflected_in_char_data(self):
        state = self._active_state()
        char = _char(10, 10)
        updates = [{"key": "combat_damage", "target": "Hero", "change": -4}]
        new_state, new_char = apply_typed_updates(state, char, updates)
        assert new_char["hp"]["current"] == 6
        player = next(
            c for c in new_state["combat_state"]["initiative_order"] if c["name"] == "Hero"
        )
        assert player["hp"] == 6

    def test_healing_increases_hp(self):
        state = self._active_state()
        char = _char(3, 10)
        updates = [{"key": "combat_damage", "target": "Hero", "change": 5}]
        new_state, new_char = apply_typed_updates(state, char, updates)
        assert new_char["hp"]["current"] == 8

    def test_healing_capped_at_max_hp(self):
        state = self._active_state()
        char = _char(8, 10)
        updates = [{"key": "combat_damage", "target": "Hero", "change": 99}]
        _, new_char = apply_typed_updates(state, char, updates)
        assert new_char["hp"]["current"] == 10

    def test_unknown_target_no_error(self):
        state = self._active_state()
        updates = [{"key": "combat_damage", "target": "Dragon", "change": -10}]
        # Should not raise
        apply_typed_updates(state, _char(), updates)
