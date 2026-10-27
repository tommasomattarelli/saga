"""DM tool infrastructure — base class, registry, dispatcher, schema generation.

Concrete tools live in tools_combat / tools_inventory / tools_world / tools_special
and register themselves here via @register on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel

from app.ai.prompts.loader import template
from app.memory.updater import apply_typed_updates
from app.models.quest import QuestRegistry


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
    quests: QuestRegistry | None = None


class DmTool(BaseModel):
    """Base class for DM tools. Subclass fields define the tool parameters."""

    model_config = {"extra": "forbid"}
    obligation: ClassVar[str]
    terminal_safe: ClassVar[bool]

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

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        """Override for tools that read the frozen world tree (ADR 0008 C11)."""
        return self.execute(world_state, char_data)

    def execute_with_context(
        self,
        world_state: dict,
        char_data: dict,
        baseline: dict | None,
        quests: QuestRegistry | None,
    ) -> ToolResult:
        """Entry point for tools that also read or write the campaign quest registry."""
        return self.execute_with_baseline(world_state, char_data, baseline)

    @classmethod
    def to_openai_schema(cls) -> dict:
        """Return the OpenAI function-calling schema for this tool."""
        raw = cls.model_json_schema()
        props_raw = raw.get("properties", {})
        defs = raw.get("$defs", {})
        # Keep only type + description + enum + items per property (strip Pydantic noise)
        _allowed = {"type", "description", "enum", "items"}
        _items_allowed = {"type", "description", "enum"}

        def _inline_enum(v: dict) -> dict:
            """Pydantic hoists enums into $defs; the LLM needs them spelled out inline."""
            ref = v.get("$ref") or next(
                (m["$ref"] for m in v.get("anyOf", []) if "$ref" in m), None
            )
            if not ref:
                return v
            target = defs.get(ref.rsplit("/", 1)[-1], {})
            return {**target, **{k: val for k, val in v.items() if k not in ("$ref", "anyOf")}}

        def _collapse_nullable(v: dict) -> dict:
            """A nullable primitive is an anyOf with one non-null branch; keep it typed."""
            branches = v.get("anyOf")
            if not branches:
                return v
            non_null = [branch for branch in branches if branch.get("type") != "null"]
            if len(non_null) != 1:
                return v
            return {
                **non_null[0],
                **{k: value for k, value in v.items() if k != "anyOf"},
            }

        def _clean_prop(v: dict) -> dict:
            resolved = _inline_enum(_collapse_nullable(v))
            cleaned = {kk: vv for kk, vv in resolved.items() if kk in _allowed}
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
    if not isinstance(cls.__dict__.get("terminal_safe"), bool):
        raise ValueError(f"Tool {cls.tool_name()} must declare its loop policy.")
    template("tool_obligations", cls.obligation)
    _TOOLS[cls.tool_name()] = cls
    return cls


def get_tool_schemas(allowed: set[str] | None = None) -> list[dict]:
    """Return tool schemas in OpenAI format, optionally filtered to `allowed` names."""
    return [
        cls.to_openai_schema()
        for name, cls in sorted(_TOOLS.items())
        if allowed is None or name in allowed
    ]


def get_tool(name: str) -> type[DmTool] | None:
    return _TOOLS.get(name)


def execute_tool(
    name: str,
    arguments: dict,
    world_state: dict,
    char_data: dict,
    baseline: dict | None = None,
    quests: QuestRegistry | None = None,
) -> ToolResult:
    tool_cls = _TOOLS.get(name)
    if not tool_cls:
        return ToolResult(
            description=f"Unknown tool: {name}",
            world_state=world_state,
            char_data=char_data,
        )
    try:
        instance = tool_cls(**arguments)
        return instance.execute_with_context(world_state, char_data, baseline, quests)
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
