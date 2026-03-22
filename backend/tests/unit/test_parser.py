"""Tests for the DM response parser."""

import json

from app.ai.parser import parse_dm_response


class TestParseDMResponse:
    """Test DM response parsing."""

    def test_valid_json(self):
        raw = json.dumps(
            {
                "narration": "You enter the tavern.",
                "dice_required": None,
                "scene_mood": "calm_exploration",
                "suggested_actions": ["Talk to barkeep", "Look around"],
            }
        )
        result = parse_dm_response(raw)
        assert result.narration == "You enter the tavern."
        assert result.scene_mood == "calm_exploration"
        assert len(result.suggested_actions) == 2

    def test_json_with_surrounding_text(self):
        raw = 'Here is my response:\n{"narration": "A dragon appears!", "scene_mood": "urgent"}\n'
        result = parse_dm_response(raw)
        assert result.narration == "A dragon appears!"

    def test_fallback_to_plain_text(self):
        raw = "The moonlight bathes the forest in silver light."
        result = parse_dm_response(raw)
        assert result.narration == raw

    def test_malformed_json_fallback(self):
        raw = '{"narration": "broken json'
        result = parse_dm_response(raw)
        assert "broken" in result.narration
