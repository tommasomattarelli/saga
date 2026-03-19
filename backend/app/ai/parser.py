"""Parse structured DM output from AI responses."""

import json
import re
import structlog
from dataclasses import dataclass, field

logger = structlog.get_logger()


@dataclass
class ParsedDMResponse:
    """Structured DM response."""

    narration: str = ""
    dice_required: list[dict] | None = None
    companion_actions: dict | None = None
    world_updates: dict | None = None
    scene_mood: str | None = None
    suggested_actions: list[str] | None = None


def parse_dm_response(raw: str) -> ParsedDMResponse:
    """Parse the DM's raw response into structured data.

    Expected JSON format:
    {
        "narration": "...",
        "dice_required": [{"name": "stealth", "dc": 15, "modifier": 3}],
        "companion_actions": {"Lyra": "draws her sword"},
        "world_updates": {"time": "dusk", "weather": "rain"},
        "scene_mood": "tense",
        "suggested_actions": ["Sneak past", "Attack", "Negotiate"]
    }

    Falls back to treating the entire response as narration if JSON parsing fails.
    """
    # Try to extract JSON from the response
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return ParsedDMResponse(
                narration=data.get("narration", raw),
                dice_required=data.get("dice_required"),
                companion_actions=data.get("companion_actions"),
                world_updates=data.get("world_updates"),
                scene_mood=data.get("scene_mood"),
                suggested_actions=data.get("suggested_actions"),
            )
        except json.JSONDecodeError:
            logger.warning("dm_response_json_parse_failed", raw_length=len(raw))

    # Fallback: treat everything as narration
    return ParsedDMResponse(narration=raw.strip())
