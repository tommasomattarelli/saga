"""Tests for world_updates normalization in the parser."""

from app.ai.parser import parse_dm_response
from app.ai.schemas.dm_response import DMResponse


class TestNormalizeWorldUpdates:
    def test_none_stays_none(self):
        resp = DMResponse(narration="test", world_updates=None)
        from app.ai.parser import _normalize_world_updates

        result = _normalize_world_updates(resp)
        assert result.world_updates is None

    def test_list_stays_list(self):
        updates = [{"key": "hp_change", "target": "player", "change": -5}]
        resp = DMResponse(narration="test", world_updates=updates)
        from app.ai.parser import _normalize_world_updates

        result = _normalize_world_updates(resp)
        assert result.world_updates == updates

    def test_single_typed_dict_wrapped_in_list(self):
        update = {"key": "combat_start", "target": "combat", "change": {"enemies": []}}
        resp = DMResponse(narration="test", world_updates=update)
        from app.ai.parser import _normalize_world_updates

        result = _normalize_world_updates(resp)
        assert isinstance(result.world_updates, list)
        assert len(result.world_updates) == 1
        assert result.world_updates[0]["key"] == "combat_start"

    def test_nested_typed_dict_extracted(self):
        """DM sometimes nests a combat_damage inside combat_start."""
        update = {
            "key": "combat_start",
            "target": "combat",
            "change": {"enemies": [{"name": "Goblin", "hp": 10, "max_hp": 10}]},
            "player_damage": {
                "key": "combat_damage",
                "target": "Tom",
                "change": -6,
            },
        }
        resp = DMResponse(narration="test", world_updates=update)
        from app.ai.parser import _normalize_world_updates

        result = _normalize_world_updates(resp)
        assert isinstance(result.world_updates, list)
        assert len(result.world_updates) == 2
        keys = [u["key"] for u in result.world_updates]
        assert "combat_start" in keys
        assert "combat_damage" in keys
        # The parent should NOT have the nested key anymore
        parent = next(u for u in result.world_updates if u["key"] == "combat_start")
        assert "player_damage" not in parent

    def test_legacy_dict_without_key_stays_dict(self):
        update = {"weather": "rain", "time_of_day": "evening"}
        resp = DMResponse(narration="test", world_updates=update)
        from app.ai.parser import _normalize_world_updates

        result = _normalize_world_updates(resp)
        assert isinstance(result.world_updates, dict)
        assert result.world_updates == update


class TestParseFullResponse:
    def test_parse_with_array_world_updates(self):
        raw = '{"narration": "test", "world_updates": [{"key": "hp_change", "target": "player", "change": -3}]}'
        result = parse_dm_response(raw)
        assert isinstance(result.world_updates, list)
        assert len(result.world_updates) == 1

    def test_parse_with_single_dict_world_updates_normalized(self):
        raw = '{"narration": "test", "world_updates": {"key": "combat_start", "target": "combat", "change": {"enemies": []}}}'
        result = parse_dm_response(raw)
        assert isinstance(result.world_updates, list)
        assert len(result.world_updates) == 1
        assert result.world_updates[0]["key"] == "combat_start"

    def test_parse_with_code_fences_stripped(self):
        raw = '```json\n{"narration": "test", "world_updates": [{"key": "hp_change", "target": "player", "change": -2}]}\n```'
        result = parse_dm_response(raw)
        assert result.narration == "test"
        assert isinstance(result.world_updates, list)

    def test_parse_with_nested_updates_extracted(self):
        raw = '{"narration": "battle", "world_updates": {"key": "combat_start", "target": "combat", "change": {"enemies": [{"name": "Orc", "hp": 20, "max_hp": 20}]}, "player_damage": {"key": "combat_damage", "target": "Hero", "change": -4}}}'
        result = parse_dm_response(raw)
        assert isinstance(result.world_updates, list)
        assert len(result.world_updates) == 2
