"""DM tools — public facade.

Tool infrastructure lives in tools_base; concrete tools are split by domain across
tools_combat / tools_inventory / tools_world / tools_special. Importing this module
registers every tool and exposes the stable public surface used across the app.
"""

from __future__ import annotations

from app.ai.tools.tools_base import (
    DmTool,
    SceneMood,
    ToolResult,
    execute_tool,
    get_tool,
    get_tool_schemas,
    visible_tool_names,
)
from app.ai.tools.tools_combat import ApplyDamage, EndCombat, StartCombat, UpdateHp
from app.ai.tools.tools_inventory import AddItem, RemoveItem
from app.ai.tools.tools_special import InvokeNpc, RequestDice
from app.ai.tools.tools_world import (
    AdvanceTime,
    ChangeNpcPsychology,
    LogEvent,
    MoveTo,
    SetSceneMood,
    UpdateQuest,
)

# Computed after all tool modules above have registered themselves.
VISIBLE_TOOLS: frozenset[str] = visible_tool_names()

MEANINGFUL_TOOLS: frozenset[str] = frozenset(
    {"invoke_npc", "request_dice", "start_combat", "end_combat"}
)

__all__ = [
    "AddItem",
    "AdvanceTime",
    "ApplyDamage",
    "ChangeNpcPsychology",
    "DmTool",
    "EndCombat",
    "InvokeNpc",
    "LogEvent",
    "MEANINGFUL_TOOLS",
    "MoveTo",
    "RemoveItem",
    "RequestDice",
    "SceneMood",
    "SetSceneMood",
    "StartCombat",
    "ToolResult",
    "UpdateHp",
    "UpdateQuest",
    "VISIBLE_TOOLS",
    "execute_tool",
    "get_tool",
    "get_tool_schemas",
]
