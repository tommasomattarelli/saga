"""Inventory tools — visible to the frontend."""

from __future__ import annotations

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, apply, register


@register
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
        new_state, new_char = apply(
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


@register
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
        new_state, new_char = apply(
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
