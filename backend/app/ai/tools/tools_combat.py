"""Combat & HP tools — visible to the frontend."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, apply, register


@register
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
        new_state, new_char = apply(
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


@register
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
        new_state, new_char = apply(world_state, char_data, {"key": "combat_end"})
        return ToolResult(
            description="Combat ended.",
            world_state=new_state,
            char_data=new_char,
        )


@register
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
        new_state, new_char = apply(
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


@register
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
        new_state, new_char = apply(
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
