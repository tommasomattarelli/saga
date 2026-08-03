import random
import re
from dataclasses import dataclass
from enum import StrEnum

from app.config_loader import load_saga_config


class DiceOutcome(StrEnum):
    CRITICAL_FAILURE = "critical_failure"
    HARD_FAILURE = "hard_failure"
    SOFT_FAILURE = "soft_failure"
    PARTIAL_SUCCESS = "partial_success"
    FULL_SUCCESS = "full_success"
    CRITICAL_SUCCESS = "critical_success"


class DifficultyLevel(StrEnum):
    """What the LLM classifies a task into. It never emits a number (ADR 0003 A2)."""

    TRIVIAL = "trivial"
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    VERY_HARD = "very_hard"
    NEAR_IMPOSSIBLE = "near_impossible"


SUCCESS_OUTCOMES = frozenset(
    {DiceOutcome.PARTIAL_SUCCESS, DiceOutcome.FULL_SUCCESS, DiceOutcome.CRITICAL_SUCCESS}
)


@dataclass
class DiceResult:
    """Result of a dice roll."""

    expression: str
    rolls: list[int]
    modifier: int
    total: int
    natural_20: bool = False
    natural_1: bool = False


@dataclass
class CheckResolution:
    """A resolved d20 check — every number in it computed server-side."""

    roll: DiceResult
    difficulty: DifficultyLevel
    difficulty_draw: int
    modifier: int
    total: int
    outcome: DiceOutcome
    is_critical: bool

    @property
    def success(self) -> bool:
        return self.outcome in SUCCESS_OUTCOMES


def _resolution_config() -> dict:
    return load_saga_config()["resolution"]


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


def draw_difficulty_modifier(level: DifficultyLevel) -> int:
    """Convert a classified level into a roll modifier by drawing from its range (A2)."""
    best, worst = _resolution_config()["difficulty_levels"][level.value]
    return random.randint(min(best, worst), max(best, worst))


def clamp_character_modifier(modifier: int) -> int:
    """Keep the sheet-produced modifier inside the envelope the bands are tuned for (A6)."""
    low, high = _resolution_config()["char_mod_clamp"]
    return max(low, min(high, modifier))


def _determine_outcome(result: DiceResult) -> tuple[DiceOutcome, bool]:
    """Read a total against the absolute bands. Naturals always win (A3/A4)."""
    if result.natural_1:
        return DiceOutcome.CRITICAL_FAILURE, True
    if result.natural_20:
        return DiceOutcome.CRITICAL_SUCCESS, True

    hard_max, partial_floor, full_floor = _resolution_config()["outcome_bands"]
    if result.total <= hard_max:
        return DiceOutcome.HARD_FAILURE, False
    if result.total < partial_floor:
        return DiceOutcome.SOFT_FAILURE, False
    if result.total < full_floor:
        return DiceOutcome.PARTIAL_SUCCESS, False
    return DiceOutcome.FULL_SUCCESS, False


def resolve_check(
    modifier: int,
    difficulty: DifficultyLevel,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResolution:
    """Resolve any d20 check: total = d20 + clamped modifier + difficulty draw (A1)."""
    char_modifier = clamp_character_modifier(modifier)
    draw = draw_difficulty_modifier(difficulty)
    total_modifier = char_modifier + draw

    if advantage and not disadvantage:
        roll = roll_with_advantage(modifier=total_modifier)
    elif disadvantage and not advantage:
        roll = roll_with_disadvantage(modifier=total_modifier)
    else:
        expression = f"1d20+{total_modifier}" if total_modifier >= 0 else f"1d20{total_modifier}"
        roll = roll_dice(expression)

    outcome, is_critical = _determine_outcome(roll)

    return CheckResolution(
        roll=roll,
        difficulty=difficulty,
        difficulty_draw=draw,
        modifier=char_modifier,
        total=roll.total,
        outcome=outcome,
        is_critical=is_critical,
    )
