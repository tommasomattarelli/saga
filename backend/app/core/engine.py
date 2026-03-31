"""Game engine shared types and constants."""

from dataclasses import dataclass, field
from typing import Literal

CONTENT_POLICY_NARRATION = (
    "The DM refuses to narrate this scene as described. Try rephrasing your action."
)

DICE_RE_PROMPT_TEMPLATE = (
    'The player attempted "{check}". They rolled {roll} + {modifier} = {total} vs DC {dc}. '
    "Outcome: {outcome}. Narrate the result in 2-3 sentences."
)


@dataclass
class ProcessedTurn:
    """The fully processed result of a game turn."""

    narration: str
    dice_rolls: dict | None
    companion_actions: dict[str, str] | None
    world_updates: dict | None
    scene_mood: str | None
    suggested_actions: list[str] | None
    model_used: str
    importance_score: int
    invoke_npcs: list[str] = field(default_factory=list)
    time_passed_minutes: int = 5
    ambient_detail: str | None = None
    requires_player_action: bool = True


@dataclass
class StreamEvent:
    """An event yielded during streaming turn processing."""

    type: Literal[
        "narration_chunk",
        "dice_roll",
        "dice_narration_chunk",
        "scene_mood",
        "npc_dialogue",
        "combat_start",
        "combat_end",
        "death_event",
        "turn_result",
        "error",
    ]
    data: str | dict
