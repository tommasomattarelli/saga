"""Resolution tools — server-computed HP changes (ADR 0003 B7/B7b).

The LLM names a class and a healer; the engine draws the number. `attack` joins this
module with the combat engine (ADR 0003 S2b).
"""

from __future__ import annotations

from pydantic import Field

from app.ai.tools.tools_base import DmTool, ToolResult, apply, register
from app.core.attack import resolve_attack
from app.core.health import HealClass, consume_dm_heal, dm_heal_budget_left, draw_heal_amount
from app.core.npc_resolver import npcs_at_current_location
from app.models.npc_class import DamageClass


@register
class Attack(DmTool):
    attacker: str = Field(description="Who strikes — the player, or any NPC in the scene")
    target: str = Field(description="Who is struck — the player, or any NPC in the scene")
    weapon_class: DamageClass | None = Field(
        default=None,
        description=(
            "Only when the PLAYER attacks: how heavy the weapon they described is. "
            "unarmed (fists), light (dagger, bow), medium (sword, axe), heavy (greatsword, "
            "maul). NPCs carry their own — leave this out for them."
        ),
    )
    advantage: bool = Field(
        default=False,
        description="The situation favours the attacker (flanked, asleep, cornered).",
    )
    disadvantage: bool = Field(
        default=False, description="The situation hinders the attacker (blind, prone, restrained)."
    )
    reason: str = Field(default="", description="Brief reason (e.g. 'lunges with the boar spear')")

    @classmethod
    def tool_name(cls) -> str:
        return "attack"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Resolve one act of contested violence between any two combatants — player to NPC, "
            "NPC to player, or NPC to NPC. The engine rolls, decides whether it lands, and "
            "computes the damage. Never state a number yourself. For an uncontested on-screen "
            "death (an execution, a poisoning) use kill_npc instead."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        return self.execute_with_baseline(world_state, char_data, None)

    def execute_with_baseline(
        self, world_state: dict, char_data: dict, baseline: dict | None
    ) -> ToolResult:
        result = resolve_attack(
            world_state,
            char_data,
            attacker=self.attacker,
            target=self.target,
            weapon_class=self.weapon_class.value if self.weapon_class else None,
            advantage=self.advantage,
            disadvantage=self.disadvantage,
            taxonomy=(baseline or {}).get("taxonomy"),
        )
        if result.error:
            return ToolResult(
                description=result.error, world_state=world_state, char_data=char_data
            )

        if result.damage:
            summary = (
                f"{result.attacker} hits {result.target} ({result.outcome.value}): "
                f"{result.damage} damage — {result.target_hp}/{result.target_max_hp} HP left."
            )
        else:
            summary = f"{result.attacker} misses {result.target} ({result.outcome.value})."
        if result.target_died:
            summary += f" {result.target} falls."

        return ToolResult(
            description=summary,
            world_state=result.world_state,
            char_data=result.char_data,
            extra={
                "attacker": result.attacker,
                "target": result.target,
                "outcome": result.outcome.value,
                "damage": result.damage,
                "hp": result.target_hp,
                "max_hp": result.target_max_hp,
                "died": result.target_died,
            },
        )


@register
class Heal(DmTool):
    healer: str = Field(
        description="Who performs the healing — an NPC in the scene, or the player"
    )
    target: str = Field(description="Who is healed")
    heal_class: HealClass = Field(
        description=(
            "How much the care is worth: minor (a poultice, a swig), strong (a real remedy, "
            "a prayer that lands), full (a miracle). Never a number."
        )
    )
    reason: str = Field(
        default="", description="Brief reason (e.g. 'healing draught', 'blessing')"
    )

    @classmethod
    def tool_name(cls) -> str:
        return "heal"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Restore health to the target. The healer must be present in the scene, and the "
            "amount is computed by the engine from the class you choose."
        )

    @classmethod
    def visible(cls) -> bool:
        return True

    def execute(self, world_state: dict, char_data: dict) -> ToolResult:
        player_name = str(char_data.get("name", "Player"))
        if self.target.casefold() != player_name.casefold():
            return ToolResult(
                description=f"{self.target} has no health the engine can track yet.",
                world_state=world_state,
                char_data=char_data,
            )

        if not self._healer_is_in_scene(world_state, player_name):
            return ToolResult(
                description=f"{self.healer} is not present in this scene and cannot heal.",
                world_state=world_state,
                char_data=char_data,
            )

        if dm_heal_budget_left(world_state) <= 0:
            return ToolResult(
                description="No more healing can be given today — narrate the wound instead.",
                world_state=world_state,
                char_data=char_data,
            )

        hp = char_data.get("hp", {})
        max_hp = int(hp.get("max", 10))
        amount = draw_heal_amount(self.heal_class, max_hp)
        new_state, new_char = apply(world_state, char_data, {"key": "hp_change", "change": amount})
        new_state = consume_dm_heal(new_state)
        healed_to = new_char.get("hp", {}).get("current", 0)

        return ToolResult(
            description=f"{self.healer} heals {self.target}: {healed_to}/{max_hp} HP"
            + (f" ({self.reason})" if self.reason else ""),
            world_state=new_state,
            char_data=new_char,
            extra={"target": self.target, "healed": amount, "hp": healed_to, "max_hp": max_hp},
        )

    def _healer_is_in_scene(self, world_state: dict, player_name: str) -> bool:
        wanted = self.healer.casefold()
        if wanted == player_name.casefold():
            return True
        present = npcs_at_current_location(world_state).values()
        return any(wanted == str(npc.get("name", "")).casefold() for npc in present)
