"""Tests for the typed World State Updater."""

from app.memory.updater import apply_typed_updates


class TestNPCDisposition:
    def test_update_existing_npc(self):
        state = {"npcs": {"Grenda": {"name": "Grenda", "disposition_toward_player": 10}}}
        updates = [{"key": "npc_disposition", "target": "Grenda", "change": 15}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state["npcs"]["Grenda"]["disposition_toward_player"] == 25

    def test_create_npc_if_missing(self):
        state = {"npcs": {}}
        updates = [{"key": "npc_disposition", "target": "NewNPC", "change": 5}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert "NewNPC" in new_state["npcs"]
        assert new_state["npcs"]["NewNPC"]["disposition_toward_player"] == 5

    def test_clamp_disposition_max(self):
        state = {"npcs": {"Grenda": {"name": "Grenda", "disposition_toward_player": 95}}}
        updates = [{"key": "npc_disposition", "target": "Grenda", "change": 20}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state["npcs"]["Grenda"]["disposition_toward_player"] == 100

    def test_clamp_disposition_min(self):
        state = {"npcs": {"Grenda": {"name": "Grenda", "disposition_toward_player": -90}}}
        updates = [{"key": "npc_disposition", "target": "Grenda", "change": -20}]
        new_state, _ = apply_typed_updates(state, {}, updates)
        assert new_state["npcs"]["Grenda"]["disposition_toward_player"] == -100


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
        new_state, _ = apply_typed_updates(state, {}, [{"key": "companion_loyalty", "target": "Lyra", "change": 10}])
        assert new_state["companions"]["Lyra"]["loyalty"] == 60

    def test_clamp_loyalty(self):
        state = {"companions": {"Lyra": {"loyalty": 95}}}
        new_state, _ = apply_typed_updates(state, {}, [{"key": "companion_loyalty", "target": "Lyra", "change": 20}])
        assert new_state["companions"]["Lyra"]["loyalty"] == 100


class TestQuestUpdate:
    def test_add_quest(self):
        char = {"active_quests": []}
        _, new_char = apply_typed_updates(
            {}, char, [{"key": "quest_update", "target": "DragonHunt", "change": "active", "description": "Slay the dragon"}]
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
        state = {"npcs": {"Grenda": {"name": "Grenda", "disposition_toward_player": 0}}}
        char = {"hp": {"current": 20, "max": 30}, "inventory": []}
        updates = [
            {"key": "npc_disposition", "target": "Grenda", "change": 10},
            {"key": "hp_change", "change": -5},
            {"key": "inventory_change", "target": "Potion", "change": "add"},
        ]
        new_state, new_char = apply_typed_updates(state, char, updates)
        assert new_state["npcs"]["Grenda"]["disposition_toward_player"] == 10
        assert new_char["hp"]["current"] == 15
        assert len(new_char["inventory"]) == 1
