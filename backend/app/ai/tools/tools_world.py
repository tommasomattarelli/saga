"""Silent world-state tools — location, quests, NPC disposition, events, mood, time."""

from __future__ import annotations

import copy

from pydantic import Field

from app.ai.tools.tools_base import DmTool, SceneMood, ToolResult, apply, register


@register
class MoveTo(DmTool):
    location: str = Field(description="Name of the new location")

    @classmethod
    def tool_name(cls) -> str:
        return "move_to"

    @classmethod
    def tool_description(cls) -> str:
        return "Update the player's current location when they move to a new area."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = apply(
            world_state, char_data, {"key": "location", "change": self.location}
        )
        # Also sync meta.current_location for context builder
        new_state.setdefault("meta", {})["current_location"] = self.location

        loc_data = new_state.get("locations", {}).get(self.location)
        if loc_data:
            desc = loc_data.get("description", "")
            connections = ", ".join(loc_data.get("connections", []))
            detail = f"Player moved to: {self.location}"
            if desc:
                detail += f"\nDescription: {desc}"
            if connections:
                detail += f"\nConnected to: {connections}"
        else:
            detail = f"Player moved to: {self.location}"

        return ToolResult(
            description=detail,
            world_state=new_state,
            char_data=new_char,
        )


@register
class UpdateQuest(DmTool):
    name: str = Field(description="Quest name")
    status: str = Field(
        description=(
            "Quest status. Valid values: "
            "'active' (start or update progress), "
            "'completed' (finished successfully), "
            "'failed' (failed permanently), "
            "'abandoned' (player gave up)."
        )
    )
    description: str = Field(default="", description="Quest description or update notes")

    @classmethod
    def tool_name(cls) -> str:
        return "update_quest"

    @classmethod
    def tool_description(cls) -> str:
        return "Add, update, or complete a quest in the player's quest log."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = apply(
            world_state,
            char_data,
            {
                "key": "quest_update",
                "target": self.name,
                "change": self.status,
                "description": self.description,
            },
        )
        return ToolResult(
            description=f"Quest '{self.name}' → {self.status}",
            world_state=new_state,
            char_data=new_char,
        )


@register
class ChangeNpcDisposition(DmTool):
    npc: str = Field(description="NPC name")
    delta: int = Field(
        description="Disposition change: positive = friendlier, negative = more hostile. Range: -100 to 100."
    )
    reason: str = Field(default="", description="Brief reason for the change")

    @classmethod
    def tool_name(cls) -> str:
        return "change_npc_disposition"

    @classmethod
    def tool_description(cls) -> str:
        return "Update an NPC's disposition toward the player after a meaningful interaction."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = apply(
            world_state,
            char_data,
            {"key": "npc_disposition", "target": self.npc, "change": self.delta},
        )
        npcs = new_state.get("npcs", {})
        new_disp = npcs.get(self.npc, {}).get("disposition_toward_player", 0)
        return ToolResult(
            description=f"{self.npc} disposition: {new_disp:+d} ({self.reason})",
            world_state=new_state,
            char_data=new_char,
        )


@register
class LogEvent(DmTool):
    description: str = Field(
        description="A short, factual description of the event to record in the world history"
    )

    @classmethod
    def tool_name(cls) -> str:
        return "log_event"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Record a significant world event in the narrative log. "
            "Use for events that should be remembered long-term (discoveries, decisions, deaths, alliances)."
        )

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = apply(
            world_state, char_data, {"key": "event_log_entry", "description": self.description}
        )
        return ToolResult(
            description=f"Event logged: {self.description}",
            world_state=new_state,
            char_data=new_char,
        )


@register
class SetSceneMood(DmTool):
    mood: str = Field(
        description=(
            "Scene mood. One of: calm_exploration, tense_anticipation, combat_fury, "
            "stealth_danger, social_intrigue, melancholic_reflection, triumphant_victory, "
            "dread_horror, wonder_discovery, mourning_loss, neutral"
        )
    )

    @classmethod
    def tool_name(cls) -> str:
        return "set_scene_mood"

    @classmethod
    def tool_description(cls) -> str:
        return "Set the emotional atmosphere of the current scene. Affects music, lighting, and UI mood."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        # Validate mood, fallback to neutral
        try:
            mood_value = SceneMood(self.mood)
        except ValueError:
            mood_value = SceneMood.NEUTRAL
        new_state = copy.deepcopy(world_state)
        new_state["scene_mood"] = mood_value.value
        return ToolResult(
            description=f"Scene mood: {mood_value.value}",
            world_state=new_state,
            char_data=char_data,
            extra={"mood": mood_value.value},
        )


@register
class AdvanceTime(DmTool):
    minutes: int = Field(
        description=(
            "Minutes of in-game time to advance. "
            "Guide: dialogue 1-5, room exploration 10-30, local travel 30-60, "
            "long travel 120-480, short rest 60, long rest 480."
        )
    )

    @classmethod
    def tool_name(cls) -> str:
        return "advance_time"

    @classmethod
    def tool_description(cls) -> str:
        return "Advance the in-game clock by a number of minutes."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        from app.memory.world_state import advance_game_clock

        new_state = advance_game_clock(copy.deepcopy(world_state), self.minutes)
        meta = new_state.get("meta", {})
        clock = meta.get("clock", {})
        time_str = f"Day {clock.get('current_day', 1)}, {clock.get('time_of_day', 'morning')}"
        return ToolResult(
            description=f"Time advanced {self.minutes}m → {time_str}",
            world_state=new_state,
            char_data=char_data,
        )
