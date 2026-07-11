"""Tests for the typed World State Updater."""

from app.memory.updater import apply_typed_updates


class TestNpcPsychology:
    def met_npc(self, **psychology):
        return {
            "npcs": {
                "Kira": {
                    "name": "Kira",
                    "psychology": {
                        "trust": 0,
                        "respect": 0,
                        "affection": 0,
                        "fear": 0,
                        **psychology,
                    },
                    "met_player": True,
                }
            }
        }

    def test_applies_deltas_per_axis(self):
        updates = [
            {"key": "npc_psychology", "target": "Kira", "changes": {"trust": -4, "fear": 8}}
        ]
        new_state, _ = apply_typed_updates(self.met_npc(), {}, updates)
        psy = new_state["npcs"]["Kira"]["psychology"]
        assert psy["trust"] == -4
        assert psy["fear"] == 8
        assert psy["respect"] == 0

    def test_delta_clamped_to_per_turn_cap(self):
        updates = [{"key": "npc_psychology", "target": "Kira", "changes": {"trust": 90}}]
        new_state, _ = apply_typed_updates(self.met_npc(), {}, updates)
        assert new_state["npcs"]["Kira"]["psychology"]["trust"] == 10

    def test_value_clamped_to_axis_range(self):
        updates = [{"key": "npc_psychology", "target": "Kira", "changes": {"fear": 10}}]
        new_state, _ = apply_typed_updates(self.met_npc(fear=95), {}, updates)
        assert new_state["npcs"]["Kira"]["psychology"]["fear"] == 100

    def test_unknown_axis_dropped(self):
        updates = [
            {"key": "npc_psychology", "target": "Kira", "changes": {"honor": 5, "trust": 3}}
        ]
        new_state, _ = apply_typed_updates(self.met_npc(), {}, updates)
        psy = new_state["npcs"]["Kira"]["psychology"]
        assert "honor" not in psy
        assert psy["trust"] == 3

    def test_first_impression_amplifies_then_flips(self):
        state = {"npcs": {"Kira": {"name": "Kira", "met_player": False}}}
        updates = [{"key": "npc_psychology", "target": "Kira", "changes": {"fear": 8}}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        kira = new_state["npcs"]["Kira"]
        assert kira["psychology"]["fear"] == 24  # 8 × 3.0
        assert kira["met_player"] is True

    def test_flip_is_immediate_within_same_turn(self):
        state = {"npcs": {"Kira": {"name": "Kira", "met_player": False}}}
        updates = [
            {"key": "npc_psychology", "target": "Kira", "changes": {"fear": 8}},
            {"key": "npc_psychology", "target": "Kira", "changes": {"fear": 8}},
        ]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state["npcs"]["Kira"]["psychology"]["fear"] == 32  # 24 + 8, no double ×3

    def test_zero_delta_interaction_still_flips(self):
        state = {"npcs": {"Kira": {"name": "Kira", "met_player": False}}}
        updates = [{"key": "npc_psychology", "target": "Kira", "changes": {}}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state["npcs"]["Kira"]["met_player"] is True

    def test_creates_missing_npc_at_defaults(self):
        updates = [{"key": "npc_psychology", "target": "Ghost", "changes": {"trust": 2}}]
        new_state, _ = apply_typed_updates({"npcs": {}}, {}, updates)
        # ADR 0009: the defensive stub is uuid-keyed with the engine shape.
        ghost = next(n for n in new_state["npcs"].values() if n["name"] == "Ghost")
        assert ghost["psychology"]["trust"] == 6  # first impression ×3
        assert ghost["psychology"]["respect"] == 0
        assert ghost["met_player"] is True
        assert ghost["lifecycle"] == "alive"

    def test_world_config_overrides_default(self):
        config = {
            "first_impression_multiplier": 2.0,
            "max_delta_per_turn": 5,
            "axes": {
                "honor": {
                    "range": [-50, 50],
                    "default": 0,
                    "bands": [{"min": -50, "label": "shamed"}, {"min": 0, "label": "honored"}],
                }
            },
        }
        state = {"npcs": {"Kira": {"name": "Kira", "met_player": False}}}
        updates = [
            {
                "key": "npc_psychology",
                "target": "Kira",
                "changes": {"honor": 9, "trust": 9},
                "config": config,
            }
        ]
        new_state, _ = apply_typed_updates(state, {}, updates)
        psy = new_state["npcs"]["Kira"]["psychology"]
        assert psy["honor"] == 10  # clamped to 5, ×2
        assert "trust" not in psy  # not an axis of this world


class TestCombatDamageDeathWriter:
    def test_enemy_at_zero_hp_kills_registered_npc(self):
        # ADR 0009 H1: deterministic death writer — unique living NPC at location.
        state = {
            "meta": {"current_location": "node-1"},
            "npcs": {
                "u-1": {"name": "Bandit", "lifecycle": "alive", "location": "node-1"},
            },
            "combat_state": {
                "active": True,
                "initiative_order": [{"name": "Bandit", "type": "enemy", "hp": 4, "max_hp": 10}],
                "current_turn_index": 0,
            },
        }
        update = {"key": "combat_damage", "target": "Bandit", "change": -6}
        new_state, _ = apply_typed_updates(state, {}, [update])
        combatant = new_state["combat_state"]["initiative_order"][0]
        assert combatant["hp"] == 0
        assert combatant["defeated"] is True
        assert new_state["npcs"]["u-1"]["lifecycle"] == "dead"

    def test_mook_at_zero_hp_gets_defeated_only(self):
        # A free {name, hp} enemy with no NPC record: no lifecycle write anywhere.
        state = {
            "npcs": {},
            "combat_state": {
                "active": True,
                "initiative_order": [{"name": "Goblin", "type": "enemy", "hp": 2, "max_hp": 5}],
                "current_turn_index": 0,
            },
        }
        update = {"key": "combat_damage", "target": "Goblin", "change": -2}
        new_state, _ = apply_typed_updates(state, {}, [update])
        assert new_state["combat_state"]["initiative_order"][0]["defeated"] is True
        assert new_state["npcs"] == {}

    def test_ambiguous_combatant_name_no_silent_kill(self):
        state = {
            "meta": {"current_location": "node-1"},
            "npcs": {
                "u-1": {"name": "Guard", "lifecycle": "alive", "location": "node-1"},
                "u-2": {"name": "Guard", "lifecycle": "alive", "location": "node-1"},
            },
            "combat_state": {
                "active": True,
                "initiative_order": [{"name": "Guard", "type": "enemy", "hp": 1, "max_hp": 5}],
                "current_turn_index": 0,
            },
        }
        update = {"key": "combat_damage", "target": "Guard", "change": -1}
        new_state, _ = apply_typed_updates(state, {}, [update])
        assert new_state["combat_state"]["initiative_order"][0]["defeated"] is True
        assert all(n["lifecycle"] == "alive" for n in new_state["npcs"].values())

    def test_healing_from_zero_does_not_resurrect(self):
        # defeated already set → the writer fires once; healing won't re-trigger it.
        state = {
            "npcs": {"u-1": {"name": "Bandit", "lifecycle": "dead", "location": None}},
            "combat_state": {
                "active": True,
                "initiative_order": [
                    {"name": "Bandit", "type": "enemy", "hp": 0, "max_hp": 10, "defeated": True}
                ],
                "current_turn_index": 0,
            },
        }
        update = {"key": "combat_damage", "target": "Bandit", "change": 5}
        new_state, _ = apply_typed_updates(state, {}, [update])
        assert new_state["npcs"]["u-1"]["lifecycle"] == "dead"


class TestHPChange:
    def test_damage(self):
        char = {"hp": {"current": 20, "max": 30}}
        _, new_char = apply_typed_updates({}, char, [{"key": "hp_change", "change": -5}])
        assert new_char["hp"]["current"] == 15

    def test_heal(self):
        char = {"hp": {"current": 10, "max": 30}}
        _, new_char = apply_typed_updates({}, char, [{"key": "hp_change", "change": 10}])
        assert new_char["hp"]["current"] == 20

    def test_clamp_to_zero(self):
        char = {"hp": {"current": 3, "max": 30}}
        _, new_char = apply_typed_updates({}, char, [{"key": "hp_change", "change": -10}])
        assert new_char["hp"]["current"] == 0

    def test_clamp_to_max(self):
        char = {"hp": {"current": 28, "max": 30}}
        _, new_char = apply_typed_updates({}, char, [{"key": "hp_change", "change": 10}])
        assert new_char["hp"]["current"] == 30


class TestInventory:
    def test_add_item(self):
        char = {"inventory": []}
        _, new_char = apply_typed_updates(
            {}, char, [{"key": "inventory_change", "target": "Sword", "change": "add"}]
        )
        assert len(new_char["inventory"]) == 1
        assert new_char["inventory"][0]["name"] == "Sword"

    def test_remove_item(self):
        char = {"inventory": [{"name": "Sword", "quantity": 1}]}
        _, new_char = apply_typed_updates(
            {}, char, [{"key": "inventory_change", "target": "Sword", "change": "remove"}]
        )
        assert len(new_char["inventory"]) == 0


class TestCompanionLoyalty:
    def test_increase_loyalty(self):
        state = {"companions": {"Lyra": {"loyalty": 50}}}
        new_state, _ = apply_typed_updates(
            state, {}, [{"key": "companion_loyalty", "target": "Lyra", "change": 10}]
        )
        assert new_state["companions"]["Lyra"]["loyalty"] == 60

    def test_clamp_loyalty(self):
        state = {"companions": {"Lyra": {"loyalty": 95}}}
        new_state, _ = apply_typed_updates(
            state, {}, [{"key": "companion_loyalty", "target": "Lyra", "change": 20}]
        )
        assert new_state["companions"]["Lyra"]["loyalty"] == 100


class TestQuestUpdate:
    def test_add_quest(self):
        char = {"active_quests": []}
        _, new_char = apply_typed_updates(
            {},
            char,
            [
                {
                    "key": "quest_update",
                    "target": "DragonHunt",
                    "change": "active",
                    "description": "Slay the dragon",
                }
            ],
        )
        assert len(new_char["active_quests"]) == 1
        assert new_char["active_quests"][0]["name"] == "DragonHunt"

    def test_complete_quest(self):
        char = {"active_quests": [{"name": "DragonHunt", "description": "Slay the dragon"}]}
        _, new_char = apply_typed_updates(
            {}, char, [{"key": "quest_update", "target": "DragonHunt", "change": "completed"}]
        )
        assert len(new_char["active_quests"]) == 0


class TestEventLog:
    def test_append_event(self):
        state = {"narrative": {"event_log": []}}
        new_state, _ = apply_typed_updates(
            state, {}, [{"key": "event_log_entry", "description": "The dragon awoke"}]
        )
        assert len(new_state["narrative"]["event_log"]) == 1


class TestReputation:
    def test_increase_reputation(self):
        char = {"reputation": {"Merchants Guild": 10}}
        _, new_char = apply_typed_updates(
            {}, char, [{"key": "reputation_change", "target": "Merchants Guild", "change": 5}]
        )
        assert new_char["reputation"]["Merchants Guild"] == 15


class TestGenericFallback:
    def test_unknown_type_uses_merge(self):
        state = {}
        updates = [{"key": "unknown_type", "target": "weather", "value": "rain"}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state.get("weather") == "rain"


class TestMultipleUpdates:
    def test_sequential_updates(self):
        state = {"npcs": {"Grenda": {"name": "Grenda", "met_player": True, "psychology": {}}}}
        char = {"hp": {"current": 20, "max": 30}, "inventory": []}
        updates = [
            {"key": "npc_psychology", "target": "Grenda", "changes": {"trust": 10}},
            {"key": "hp_change", "change": -5},
            {"key": "inventory_change", "target": "Potion", "change": "add"},
        ]
        new_state, new_char = apply_typed_updates(state, char, updates)
        assert new_state["npcs"]["Grenda"]["psychology"]["trust"] == 10
        assert new_char["hp"]["current"] == 15
        assert len(new_char["inventory"]) == 1
