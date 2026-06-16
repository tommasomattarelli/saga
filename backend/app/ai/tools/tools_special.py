"""Special tools — resolved by the agent loop (tools_node), not by execute()."""

from __future__ import annotations

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, register


@register
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


@register
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
