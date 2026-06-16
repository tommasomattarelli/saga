"""DM tool infrastructure — base class, registry, dispatcher, schema generation.

Concrete tools live in tools_combat / tools_inventory / tools_world / tools_special
and register themselves here via @register on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel

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


def register(cls: type[DmTool]) -> type[DmTool]:
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


def visible_tool_names() -> frozenset[str]:
    """Names of all registered tools the frontend should display in real time."""
    return frozenset(cls.tool_name() for cls in _TOOLS.values() if cls.visible())


def apply(world_state: dict, char_data: dict, update: dict) -> tuple[dict, dict]:
    new_state, new_char = apply_typed_updates(world_state, char_data, [update])
    return new_state, new_char
