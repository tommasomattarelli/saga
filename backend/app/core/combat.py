

from dataclasses import dataclass, field

from app.core.dice import DiceResult, roll_dice


@dataclass
class Combatant:
    """A participant in combat."""

    name: str
    initiative: int = 0
    hp: int = 10
    max_hp: int = 10
    ac: int = 10
    is_player: bool = False
    conditions: list[str] = field(default_factory=list)


@dataclass
class CombatState:
    """Current state of a combat encounter."""

    combatants: list[Combatant] = field(default_factory=list)
    current_turn_index: int = 0
    round_number: int = 1
    is_active: bool = True

    @property
    def current_combatant(self) -> Combatant | None:
        """Get the combatant whose turn it is."""
        if not self.combatants:
            return None
        return self.combatants[self.current_turn_index]

    def advance_turn(self) -> None:
        """Move to the next combatant in initiative order."""
        self.current_turn_index += 1
        if self.current_turn_index >= len(self.combatants):
            self.current_turn_index = 0
            self.round_number += 1


def roll_initiative(combatants: list[Combatant]) -> list[Combatant]:
    for c in combatants:
        result = roll_dice("1d20")
        c.initiative = result.total
    return sorted(combatants, key=lambda c: c.initiative, reverse=True)


def attack_roll(attacker_modifier: int, target_ac: int) -> dict:
    result = roll_dice(
        f"1d20+{attacker_modifier}" if attacker_modifier >= 0 else f"1d20{attacker_modifier}"
    )
    return {
        "roll": result.total,
        "rolls": result.rolls,
        "hits": result.total >= target_ac or result.natural_20,
        "critical": result.natural_20,
        "fumble": result.natural_1,
    }


def damage_roll(expression: str) -> DiceResult:
    return roll_dice(expression)
