"""Silent world-state tools — location, quests, NPC psychology, events, mood, time."""

from __future__ import annotations

import copy

from pydantic import Field

from app.ai.tools.tools_base import DmTool, SceneMood, ToolResult, apply, register
from app.core.npc_resolver import resolve_npc
from app.core.psychology import DEFAULT_PSYCHOLOGY, band_label
from app.models.psychology import PsychologyDef


@register
class MoveTo(DmTool):
    location: str = Field(description="Name of the destination (place name or slug)")

    @classmethod
    def tool_name(cls) -> str:
        return "move_to"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Move the player to another place. Travel is validated against the world's "
            "routes, costs game time, and may trigger a travel encounter. On ambiguity "
            "the tool lists candidates — re-call with the full name."
        )

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return ToolResult(
            description="Movement unavailable: this campaign has no world map.",
            world_state=world_state,
            char_data=char_data,
        )

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        from app.config_loader import load_saga_config
        from app.core.travel import TravelConfig, attempt_move
        from app.core.world_access import WorldView
        from app.memory.world_state import advance_game_clock

        view = WorldView(baseline or {}, world_state)
        if not view.has_world:
            return self.execute(world_state, char_data)

        travel_cfg = (load_saga_config().get("world") or {}).get("travel") or {}
        config = TravelConfig(
            elevation_coeff=float(travel_cfg.get("elevation_coeff", 7.92)),
            local_move_minutes=int(travel_cfg.get("local_move_minutes", 5)),
        )
        outcome = attempt_move(view, self.location, config)
        if not outcome.ok:
            return ToolResult(
                description=f"Move rejected: {outcome.reason}",
                world_state=world_state,
                char_data=char_data,
            )

        new_state = copy.deepcopy(world_state)
        pending = new_state.pop("pending_travel", None)
        minutes = outcome.minutes
        if pending and pending.get("destination") == outcome.destination:
            minutes = int(pending.get("minutes_remaining", minutes))

        destination_name = view.require(outcome.destination or "")["name"]
        if outcome.consumed_key and outcome.encounter and outcome.encounter.get("once"):
            new_state.setdefault("consumed_encounters", {}).setdefault(
                outcome.consumed_key, []
            ).append(outcome.encounter["index"])

        if outcome.encounter and outcome.encounter["type"] == "combat":
            # Journey interrupted mid-route (F13): hold position, store the rest.
            elapsed = max(1, minutes // 2)
            new_state["pending_travel"] = {
                "destination": outcome.destination,
                "minutes_remaining": minutes - elapsed,
            }
            new_state = advance_game_clock(new_state, elapsed)
            detail = (
                f"Travel toward {destination_name} INTERRUPTED after {elapsed} minutes: "
                f"{outcome.encounter['description']} (hostile). "
                f"Re-call move_to '{destination_name}' after the fight to continue."
            )
        else:
            new_state["player_position"] = outcome.destination
            new_state.setdefault("meta", {})["current_location"] = outcome.destination
            new_state = advance_game_clock(new_state, minutes)
            route = " → ".join(outcome.path)
            detail = f"Player moved to {destination_name} ({route}; {minutes} min of travel)."
            if outcome.encounter:
                detail += f"\nOn the way: {outcome.encounter['description']}"

        return ToolResult(
            description=detail,
            world_state=new_state,
            char_data=char_data,
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
class ChangeNpcPsychology(DmTool):
    npc: str = Field(description="NPC name")
    changes: dict[str, int] = Field(
        description='Per-axis integer deltas, e.g. {"trust": -5, "fear": 8}. '
        "Positive = more of that feeling toward the player."
    )
    reason: str = Field(default="", description="Brief reason for the change")

    @classmethod
    def tool_name(cls) -> str:
        return "change_npc_psychology"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Shift an NPC's psychology axes toward the player after a meaningful "
            "interaction. Axes are defined by the world (see the scene block)."
        )

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return self.execute_with_baseline(world_state, char_data, None)

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        config = ((baseline or {}).get("taxonomy") or {}).get("psychology")
        pdef = PsychologyDef(**config) if config else DEFAULT_PSYCHOLOGY
        unknown = [axis for axis in self.changes if axis not in pdef.axes]
        if unknown:
            # Reject-with-candidates (0008 F7): the DM loop can retry.
            return ToolResult(
                description=(
                    f"Unknown axis '{unknown[0]}'. This world's axes: {', '.join(pdef.axes)}."
                ),
                world_state=world_state,
                char_data=char_data,
            )
        resolution = resolve_npc(self.npc, world_state)
        if resolution.npc_id is None:
            return ToolResult(
                description=resolution.error,
                world_state=world_state,
                char_data=char_data,
            )
        update: dict = {
            "key": "npc_psychology",
            "target": resolution.npc_id,
            "changes": dict(self.changes),
        }
        if config:
            update["config"] = config
        new_state, new_char = apply(world_state, char_data, update)
        values = new_state.get("npcs", {}).get(resolution.npc_id, {}).get("psychology", {})
        parts = [
            f"{axis}: {values.get(axis, 0)} ({band_label(pdef.axes[axis], values.get(axis, 0))})"
            for axis in self.changes
        ]
        suffix = f" ({self.reason})" if self.reason else ""
        return ToolResult(
            description=f"{self.npc} psychology → {', '.join(parts)}{suffix}",
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
