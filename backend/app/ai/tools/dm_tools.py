"""DM tool definitions — typed actions the AI DM can call during a turn.

Each tool wraps an existing handler in memory/updater.py (1:1 mapping).
Special tools (request_dice, invoke_npc) are handled by the agent loop directly.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.memory.updater import apply_typed_updates


class SceneMood(StrEnum):
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


@dataclass
class ToolResult:
    """Result of executing a DM tool — fed back to the LLM as tool result."""

    description: str  # human-readable summary for the DM
    world_state: dict
    char_data: dict
    extra: dict = field(default_factory=dict)  # tool-specific data (dice result, NPC dialogue…)


class DmTool(BaseModel):
    """Base class for DM tools. Subclass fields define the tool parameters."""

    model_config = {"extra": "forbid"}

    @classmethod
    def tool_name(cls) -> str:
        raise NotImplementedError

    @classmethod
    def tool_description(cls) -> str:
        raise NotImplementedError

    @classmethod
    def visible(cls) -> bool:
        """Whether the frontend should display this tool call in real time."""
        return False

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        raise NotImplementedError

    @classmethod
    def to_openai_schema(cls) -> dict:
        """Return the OpenAI function-calling schema for this tool."""
        raw = cls.model_json_schema()
        props_raw = raw.get("properties", {})
        # Keep only type + description + enum + items per property (strip Pydantic noise)
        _allowed = {"type", "description", "enum", "items"}
        _items_allowed = {"type", "description", "enum"}

        def _clean_prop(v: dict) -> dict:
            cleaned = {kk: vv for kk, vv in v.items() if kk in _allowed}
            if "items" in cleaned and isinstance(cleaned["items"], dict):
                cleaned["items"] = {
                    kk: vv for kk, vv in cleaned["items"].items() if kk in _items_allowed
                }
            return cleaned

        props = {k: _clean_prop(v) for k, v in props_raw.items()}
        return {
            "type": "function",
            "function": {
                "name": cls.tool_name(),
                "description": cls.tool_description(),
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": raw.get("required", []),
                },
            },
        }


# ── Registry ─────────────────────────────────────────────────────────────────

_TOOLS: dict[str, type[DmTool]] = {}


def _register(cls: type[DmTool]) -> type[DmTool]:
    _TOOLS[cls.tool_name()] = cls
    return cls


def get_tool_schemas(allowed: set[str] | None = None) -> list[dict]:
    """Return tool schemas in OpenAI format, optionally filtered to `allowed` names."""
    return [
        cls.to_openai_schema()
        for name, cls in _TOOLS.items()
        if allowed is None or name in allowed
    ]


def get_tool(name: str) -> type[DmTool] | None:
    return _TOOLS.get(name)


def execute_tool(name: str, arguments: dict, world_state: dict, char_data: dict) -> ToolResult:
    tool_cls = _TOOLS.get(name)
    if not tool_cls:
        return ToolResult(
            description=f"Unknown tool: {name}",
            world_state=world_state,
            char_data=char_data,
        )
    try:
        instance = tool_cls(**arguments)
        return instance.execute(world_state, char_data)
    except Exception as exc:
        safe_msg = str(exc).replace("\n", " ").strip()[:120]
        return ToolResult(
            description=f"Tool {name} failed: {safe_msg}",
            world_state=world_state,
            char_data=char_data,
        )


# ── Helper ───────────────────────────────────────────────────────────────────


def _apply(world_state: dict, char_data: dict, update: dict) -> tuple[dict, dict]:
    new_state, new_char = apply_typed_updates(world_state, char_data, [update])
    return new_state, new_char


# ── Combat tools (visible) ────────────────────────────────────────────────────


@_register
class StartCombat(DmTool):
    enemies: list[dict[str, Any]] = Field(
        description='List of enemies to fight. Each enemy: {"name": "Goblin", "hp": 10, "max_hp": 10}'
    )

    @classmethod
    def tool_name(cls) -> str:
        return "start_combat"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Begin a combat encounter. Call this exactly once when combat starts. "
            "Provide all enemies. Rolls initiative automatically."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
            world_state, char_data, {"key": "combat_start", "change": {"enemies": self.enemies}}
        )
        order = new_state.get("combat_state", {}).get("initiative_order", [])
        order_str = ", ".join(f"{c['name']} ({c['initiative']})" for c in order)
        return ToolResult(
            description=f"Combat started. Initiative order: {order_str}",
            world_state=new_state,
            char_data=new_char,
            extra={"combat_state": new_state.get("combat_state", {})},
        )


@_register
class EndCombat(DmTool):
    @classmethod
    def tool_name(cls) -> str:
        return "end_combat"

    @classmethod
    def tool_description(cls) -> str:
        return "End the current combat encounter. Call when all enemies are defeated or combat is resolved."

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(world_state, char_data, {"key": "combat_end"})
        return ToolResult(
            description="Combat ended.",
            world_state=new_state,
            char_data=new_char,
        )


@_register
class ApplyDamage(DmTool):
    target: str = Field(
        description="Exact name of the combatant to damage (must match initiative order)"
    )
    amount: int = Field(description="Damage to deal (positive integer). Use negative for healing.")

    @classmethod
    def tool_name(cls) -> str:
        return "apply_damage"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Apply damage or healing to a combatant during combat. "
            "Positive amount = damage, negative = healing. "
            "Use 'Player' or the player's character name for the player."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
            world_state,
            char_data,
            {"key": "combat_damage", "target": self.target, "change": -self.amount},
        )
        # Find updated HP
        order = new_state.get("combat_state", {}).get("initiative_order", [])
        hp_info = next((c for c in order if c["name"].lower() == self.target.lower()), None)
        hp_str = f"HP: {hp_info['hp']}/{hp_info['max_hp']}" if hp_info else ""
        action = "dealt" if self.amount > 0 else "healed"
        return ToolResult(
            description=f"{abs(self.amount)} {action} to {self.target}. {hp_str}".strip(),
            world_state=new_state,
            char_data=new_char,
            extra={"target": self.target, "amount": self.amount, "hp_info": hp_info},
        )


# ── HP tool (visible) ─────────────────────────────────────────────────────────


@_register
class UpdateHp(DmTool):
    change: int = Field(
        description="HP change for the player. Negative = damage, positive = healing."
    )
    reason: str = Field(description="Brief reason (e.g. 'potion', 'trap', 'fall damage')")

    @classmethod
    def tool_name(cls) -> str:
        return "update_hp"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Change the player's HP outside of combat (traps, potions, environmental hazards). "
            "For combat damage use apply_damage instead."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        old_hp = char_data.get("hp", {}).get("current", 0)
        new_state, new_char = _apply(
            world_state, char_data, {"key": "hp_change", "change": self.change}
        )
        new_hp = new_char.get("hp", {}).get("current", 0)
        max_hp = new_char.get("hp", {}).get("max", new_hp)
        return ToolResult(
            description=f"Player HP: {old_hp} → {new_hp}/{max_hp} ({self.reason})",
            world_state=new_state,
            char_data=new_char,
            extra={"old_hp": old_hp, "new_hp": new_hp, "max_hp": max_hp},
        )


# ── Inventory tools (visible) ─────────────────────────────────────────────────


@_register
class AddItem(DmTool):
    name: str = Field(description="Item name")
    description: str = Field(default="", description="Brief item description")
    quantity: int = Field(default=1, description="Quantity to add")

    @classmethod
    def tool_name(cls) -> str:
        return "add_item"

    @classmethod
    def tool_description(cls) -> str:
        return "Add an item to the player's inventory."

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
            world_state,
            char_data,
            {
                "key": "inventory_change",
                "target": self.name,
                "change": "add",
                "description": self.description,
            },
        )
        return ToolResult(
            description=f"Added '{self.name}' to inventory.",
            world_state=new_state,
            char_data=new_char,
            extra={"item": self.name},
        )


@_register
class RemoveItem(DmTool):
    name: str = Field(description="Exact item name to remove from inventory")

    @classmethod
    def tool_name(cls) -> str:
        return "remove_item"

    @classmethod
    def tool_description(cls) -> str:
        return "Remove an item from the player's inventory (used, lost, sold, destroyed)."

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
            world_state,
            char_data,
            {"key": "inventory_change", "target": self.name, "change": "remove"},
        )
        return ToolResult(
            description=f"Removed '{self.name}' from inventory.",
            world_state=new_state,
            char_data=new_char,
            extra={"item": self.name},
        )


# ── Silent world tools ────────────────────────────────────────────────────────


@_register
class MoveTo(DmTool):
    location: str = Field(description="Name of the new location")

    @classmethod
    def tool_name(cls) -> str:
        return "move_to"

    @classmethod
    def tool_description(cls) -> str:
        return "Update the player's current location when they move to a new area."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
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


@_register
class UpdateQuest(DmTool):
    name: str = Field(description="Quest name")
    status: str = Field(description="'active' to start/update a quest, 'completed' to finish it")
    description: str = Field(default="", description="Quest description or update notes")

    @classmethod
    def tool_name(cls) -> str:
        return "update_quest"

    @classmethod
    def tool_description(cls) -> str:
        return "Add, update, or complete a quest in the player's quest log."

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        new_state, new_char = _apply(
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


@_register
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
        new_state, new_char = _apply(
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


@_register
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
        new_state, new_char = _apply(
            world_state, char_data, {"key": "event_log_entry", "description": self.description}
        )
        return ToolResult(
            description=f"Event logged: {self.description}",
            world_state=new_state,
            char_data=new_char,
        )


@_register
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


@_register
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


# ── Special tools (handled by agent loop, not execute()) ─────────────────────


@_register
class RequestDice(DmTool):
    check: str = Field(description="Type of check (e.g. 'stealth', 'persuasion', 'attack')")
    dc: int = Field(description="Difficulty class (target number)")
    stat: str = Field(description="Ability stat to use: STR, DEX, CON, INT, WIS, or CHA")
    reason: str = Field(default="", description="Brief reason this check is needed")

    @classmethod
    def tool_name(cls) -> str:
        return "request_dice"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Request a dice roll from the player. Use ONLY for actions with uncertain outcome AND meaningful stakes. "
            "Trivial actions (walking, talking) do not need a roll. "
            "Impossible actions should be narrated as failures without a roll."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        # Handled by agent loop — this should never be called directly
        return ToolResult(
            description="(dice handled by agent loop)",
            world_state=world_state,
            char_data=char_data,
        )


@_register
class InvokeNpc(DmTool):
    name: str = Field(description="NPC name to speak")
    context: str = Field(
        default="", description="Brief context for what this NPC should respond to"
    )

    @classmethod
    def tool_name(cls) -> str:
        return "invoke_npc"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Make an NPC speak or act. The NPC will generate dialogue in character. "
            "You will receive the dialogue and can react to it in your next narration."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        # Handled by agent loop
        return ToolResult(
            description="(NPC handled by agent loop)",
            world_state=world_state,
            char_data=char_data,
        )


# ── Visible tool names (for frontend dispatch) ────────────────────────────────

VISIBLE_TOOLS: frozenset[str] = frozenset(
    cls.tool_name() for cls in _TOOLS.values() if cls.visible()
)
