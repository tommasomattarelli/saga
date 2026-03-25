"""Tests for DMResponse Pydantic schema."""

from app.ai.schemas.dm_response import DiceRequest, DMResponse, SceneMood


class TestSceneMood:
    def test_valid_mood(self):
        r = DMResponse(narration="test", scene_mood="combat_fury")
        assert r.scene_mood == SceneMood.COMBAT_FURY

    def test_invalid_mood_falls_back_to_neutral(self):
        r = DMResponse(narration="test", scene_mood="nonexistent_mood")
        assert r.scene_mood == SceneMood.NEUTRAL

    def test_none_mood_falls_back_to_neutral(self):
        r = DMResponse(narration="test", scene_mood=None)
        assert r.scene_mood == SceneMood.NEUTRAL

    def test_mood_case_insensitive(self):
        r = DMResponse(narration="test", scene_mood="COMBAT_FURY")
        assert r.scene_mood == SceneMood.COMBAT_FURY

    def test_mood_strips_whitespace(self):
        r = DMResponse(narration="test", scene_mood="  calm_exploration  ")
        assert r.scene_mood == SceneMood.CALM_EXPLORATION


class TestDMResponseDefaults:
    def test_minimal_response(self):
        r = DMResponse()
        assert r.narration == ""
        assert r.invoke_npcs == []
        assert r.dice_required is None
        assert r.scene_mood == SceneMood.NEUTRAL
        assert r.time_passed_minutes == 5
        assert r.companion_actions is None
        assert r.world_updates is None
        assert r.suggested_actions is None
        assert r.ambient_detail is None
        assert r.character_generation is None

    def test_extra_fields_ignored(self):
        r = DMResponse.model_validate(
            {"narration": "test", "unknown_field": "value", "another": 42}
        )
        assert r.narration == "test"
        assert not hasattr(r, "unknown_field")

    def test_full_response(self):
        r = DMResponse.model_validate(
            {
                "narration": "You step into the darkness.",
                "invoke_npcs": ["Lyra", "Guard"],
                "dice_required": [{"name": "stealth", "dc": 15, "modifier": 3}],
                "scene_mood": "stealth_danger",
                "time_passed_minutes": 10,
                "companion_actions": {"Lyra": "hides behind you"},
                "world_updates": {"weather": "fog"},
                "suggested_actions": ["Sneak", "Fight"],
                "ambient_detail": "Fog rolls in.",
            }
        )
        assert r.narration == "You step into the darkness."
        assert len(r.invoke_npcs) == 2
        assert len(r.dice_required) == 1
        assert r.dice_required[0].name == "stealth"
        assert r.dice_required[0].dc == 15
        assert r.scene_mood == SceneMood.STEALTH_DANGER
        assert r.time_passed_minutes == 10
        assert r.ambient_detail == "Fog rolls in."


class TestDiceRequest:
    def test_defaults(self):
        dr = DiceRequest(name="athletics")
        assert dr.dc == 10
        assert dr.modifier == 0
        assert dr.advantage is False
        assert dr.disadvantage is False

    def test_full(self):
        dr = DiceRequest(name="stealth", dc=20, modifier=5, advantage=True)
        assert dr.name == "stealth"
        assert dr.dc == 20
        assert dr.modifier == 5
        assert dr.advantage is True


class TestCharacterGeneration:
    def test_character_generation_field(self):
        r = DMResponse.model_validate(
            {
                "narration": "Your character emerges.",
                "character_generation": {
                    "name": "Aria",
                    "level": 1,
                    "hp": 12,
                    "max_hp": 12,
                    "abilities": {"strength": 14, "dexterity": 16},
                },
            }
        )
        assert r.character_generation is not None
        assert r.character_generation["name"] == "Aria"
