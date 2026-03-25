"""Tests for DM response parser with JSON healing."""

import json

from app.ai.parser import parse_dm_response


class TestStripFences:
    def test_strips_json_fence(self):
        raw = '```json\n{"narration": "Hello"}\n```'
        result = parse_dm_response(raw)
        assert result.narration == "Hello"

    def test_strips_plain_fence(self):
        raw = '```\n{"narration": "Hello"}\n```'
        result = parse_dm_response(raw)
        assert result.narration == "Hello"

    def test_handles_no_fence(self):
        raw = '{"narration": "Hello"}'
        result = parse_dm_response(raw)
        assert result.narration == "Hello"


class TestJsonRepair:
    def test_repairs_trailing_comma(self):
        raw = '{"narration": "You walk in.", "scene_mood": "neutral",}'
        result = parse_dm_response(raw)
        assert result.narration == "You walk in."

    def test_repairs_missing_quotes(self):
        raw = '{narration: "You walk in."}'
        result = parse_dm_response(raw)
        assert result.narration == "You walk in."

    def test_repairs_single_quotes(self):
        raw = "{'narration': 'You walk in.'}"
        result = parse_dm_response(raw)
        assert result.narration == "You walk in."


class TestFallback:
    def test_plain_text_fallback(self):
        raw = "The moonlight shines through the window."
        result = parse_dm_response(raw)
        assert result.narration == raw

    def test_completely_broken_json(self):
        raw = "{{{invalid garbage"
        result = parse_dm_response(raw)
        assert len(result.narration) > 0

    def test_narration_extracted_on_validation_failure(self):
        raw = json.dumps({"narration": "Some text", "dice_required": "not_a_list"})
        result = parse_dm_response(raw)
        assert "Some text" in result.narration


class TestParsedSchema:
    def test_full_response_parsed(self):
        raw = json.dumps(
            {
                "narration": "A dragon appears!",
                "invoke_npcs": ["Dragon"],
                "dice_required": [{"name": "initiative", "dc": 12}],
                "scene_mood": "combat_fury",
                "time_passed_minutes": 1,
                "companion_actions": {"Lyra": "draws sword"},
                "suggested_actions": ["Fight", "Flee"],
                "ambient_detail": "Heat radiates from the beast.",
            }
        )
        result = parse_dm_response(raw)
        assert result.narration == "A dragon appears!"
        assert result.invoke_npcs == ["Dragon"]
        assert len(result.dice_required) == 1
        assert result.dice_required[0].name == "initiative"
        assert result.scene_mood == "combat_fury"
        assert result.time_passed_minutes == 1
        assert result.ambient_detail == "Heat radiates from the beast."

    def test_extra_fields_ignored(self):
        raw = json.dumps({"narration": "Test", "some_future_field": True, "another_field": [1, 2]})
        result = parse_dm_response(raw)
        assert result.narration == "Test"

    def test_surrounding_text_with_json(self):
        raw = 'Here is my response:\n```json\n{"narration": "You enter."}\n```\nEnd.'
        result = parse_dm_response(raw)
        assert result.narration == "You enter."
