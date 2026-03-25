import random
import re
from dataclasses import dataclass
from enum import StrEnum


class DiceOutcome(StrEnum):
    CRITICAL_FAILURE = "critical_failure"
    HARD_FAILURE = "hard_failure"
    SOFT_FAILURE = "soft_failure"
    PARTIAL_SUCCESS = "partial_success"
    FULL_SUCCESS = "full_success"
    CRITICAL_SUCCESS = "critical_success"


@dataclass
class DiceResult:
    """Result of a dice roll."""

    expression: str
    rolls: list[int]
    modifier: int
    total: int
    natural_20: bool = False
    natural_1: bool = False


def roll_dice(expression: str) -> DiceResult:
    """Roll dice from an expression."""
    expr = expression.strip().lower()
    match = re.match(r"^(\d*)d(\d+)([+-]\d+)?$", expr)
    if not match:
        raise ValueError(f"Invalid dice expression: {expression}")

    num_dice = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)

    if num_dice < 1 or num_dice > 100 or sides < 1 or sides > 100:
        raise ValueError(f"Dice out of range: {expression}")

    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    return DiceResult(
        expression=expression,
        rolls=rolls,
        modifier=modifier,
        total=total,
        natural_20=(sides == 20 and num_dice == 1 and rolls[0] == 20),
        natural_1=(sides == 20 and num_dice == 1 and rolls[0] == 1),
    )


def roll_with_advantage(sides: int = 20, modifier: int = 0) -> DiceResult:
    r1 = random.randint(1, sides)
    r2 = random.randint(1, sides)
    best = max(r1, r2)
    return DiceResult(
        expression=f"2d{sides}kh1+{modifier}" if modifier else f"2d{sides}kh1",
        rolls=[r1, r2],
        modifier=modifier,
        total=best + modifier,
        natural_20=(sides == 20 and best == 20),
        natural_1=(sides == 20 and best == 1),
    )


def roll_with_disadvantage(sides: int = 20, modifier: int = 0) -> DiceResult:
    r1 = random.randint(1, sides)
    r2 = random.randint(1, sides)
    worst = min(r1, r2)
    return DiceResult(
        expression=f"2d{sides}kl1+{modifier}" if modifier else f"2d{sides}kl1",
        rolls=[r1, r2],
        modifier=modifier,
        total=worst + modifier,
        natural_20=(sides == 20 and worst == 20),
        natural_1=(sides == 20 and worst == 1),
    )


def _determine_outcome(result: DiceResult, dc: int) -> tuple[DiceOutcome, bool]:
    """Determine 6-level outcome and criticality from a d20 check."""
    if result.natural_1:
        return DiceOutcome.CRITICAL_FAILURE, True
    if result.natural_20:
        return DiceOutcome.CRITICAL_SUCCESS, True

    diff = result.total - dc
    if diff <= -5:
        return DiceOutcome.HARD_FAILURE, False
    if diff < 0:
        return DiceOutcome.SOFT_FAILURE, False
    if diff < 4:
        return DiceOutcome.PARTIAL_SUCCESS, False
    return DiceOutcome.FULL_SUCCESS, False


def ability_check(
    modifier: int, dc: int, advantage: bool = False, disadvantage: bool = False
) -> dict:
    """Perform a d20 ability check against a DC with 6-level outcome."""
    if advantage and not disadvantage:
        result = roll_with_advantage(modifier=modifier)
    elif disadvantage and not advantage:
        result = roll_with_disadvantage(modifier=modifier)
    else:
        result = roll_dice(f"1d20+{modifier}" if modifier >= 0 else f"1d20{modifier}")

    outcome, is_critical = _determine_outcome(result, dc)

    return {
        "roll": result,
        "dc": dc,
        "success": result.total >= dc,
        "critical_success": result.natural_20,
        "critical_failure": result.natural_1,
        "outcome": outcome.value,
        "is_critical": is_critical,
    }
