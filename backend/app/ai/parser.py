"""Parse structured DM output from AI responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

import structlog

logger = structlog.get_logger()




class SceneMood(StrEnum):
    """Closed set of scene moods the DM may emit."""

    CALM_EXPLORATION = "calm_exploration"
    TENSE_ANTICIPATION = "tense_anticipation"
    COMBAT_FURY = "combat_fury"
    STEALTH_DANGER = "stealth_danger"
    SOCIAL_INTRIGUE = "social_intrigue"
    MELANCHOLIC_REFLECTION = "melancholic_reflection"
    TRIUMPHANT_VICTORY = "triumphant_victory"
    DREAD_HORROR = "dread_horror"
    WONDER_DISCOVERY = "wonder_discovery"
    MOURNING_LOSS = "mourning_loss"
    NEUTRAL = "neutral"

    @classmethod
    def from_string(cls, value: str | None) -> SceneMood:
        """Coerce a raw string to a SceneMood, falling back to NEUTRAL.

        This is the single safe entry point when handling AI output.
        Unknown or None values silently fall back to NEUTRAL — the frontend
        never crashes on unexpected moods and the DM is never rejected over
        a typo.
        """
        if value is None:
            return cls.NEUTRAL
        try:
            return cls(value.lower().strip())
        except ValueError:
            logger.warning("unknown_scene_mood", received=value, fallback="neutral")
            return cls.NEUTRAL


@dataclass
class ParsedDMResponse:
    """Structured DM response."""

    narration: str = ""
    dice_required: list[dict] | None = None
    companion_actions: dict | None = None
    world_updates: dict | None = None
    scene_mood: SceneMood = SceneMood.NEUTRAL
    suggested_actions: list[str] | None = None


def parse_dm_response(raw: str) -> ParsedDMResponse:
    """Parse the DM's raw response into structured data.

    Expected JSON format:
    {
        "narration": "...",
        "dice_required": [{"name": "stealth", "dc": 15, "modifier": 3}],
        "companion_actions": {"Lyra": "draws her sword"},
        "world_updates": {"time": "dusk", "weather": "rain"},
        "scene_mood": "tense_anticipation",
        "suggested_actions": ["Sneak past", "Attack", "Negotiate"]
    }

    scene_mood must be one of the 11 valid SceneMood values; any other value
    (or None) is silently mapped to SceneMood.NEUTRAL.

    Falls back to treating the entire response as narration if JSON parsing fails.
    """
    # Try to extract JSON from the response (handles markdown code fences too)
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return ParsedDMResponse(
                narration=data.get("narration", raw),
                dice_required=data.get("dice_required"),
                companion_actions=data.get("companion_actions"),
                world_updates=data.get("world_updates"),
                scene_mood=SceneMood.from_string(data.get("scene_mood")),
                suggested_actions=data.get("suggested_actions"),
            )
        except json.JSONDecodeError:
            logger.warning("dm_response_json_parse_failed", raw_length=len(raw))

    # Fallback: treat everything as narration
    return ParsedDMResponse(narration=raw.strip())
