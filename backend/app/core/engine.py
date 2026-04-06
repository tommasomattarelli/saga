"""Game engine shared types and constants."""

from dataclasses import dataclass, field
from typing import Literal

CONTENT_POLICY_NARRATION = (
    "The DM refuses to narrate this scene as described. Try rephrasing your action."
)


@dataclass
class ProcessedTurn:
    """The fully processed result of a game turn (used by non-streaming pipeline)."""

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
    """An event yielded during the agentic turn loop."""

    type: Literal[
        "narration_chunk",  # DM narration text token
        "dice_roll",  # Dice roll result (player must reveal)
        "await_player",  # Loop paused — waiting for player interaction
        "scene_mood",  # Scene mood changed
        "npc_dialogue",  # NPC spoke
        "tool_executed",  # Visible tool was executed (HP change, item, etc.)
        "death_event",  # Player death or near-death
        "turn_result",  # Final turn result with full state
        "error",
    ]
    data: str | dict
