"""Unified resolver — absolute bands, difficulty draws, clamp (ADR 0003 A1-A6)."""

from unittest.mock import patch

import pytest

from app.core.dice import (
    DiceOutcome,
    DiceResult,
    DifficultyLevel,
    _determine_outcome,
    clamp_character_modifier,
    draw_difficulty_modifier,
    resolve_check,
)


def _roll(total: int, nat1: bool = False, nat20: bool = False) -> DiceResult:
    return DiceResult(
        expression="1d20",
        rolls=[total],
        modifier=0,
        total=total,
        natural_1=nat1,
        natural_20=nat20,
    )


class TestOutcomeBands:
    """Bands are absolute now — no DC, the total alone decides (A3)."""

    @pytest.mark.parametrize(
        ("total", "expected"),
        [
            (-3, DiceOutcome.HARD_FAILURE),
            (5, DiceOutcome.HARD_FAILURE),
            (6, DiceOutcome.SOFT_FAILURE),
            (9, DiceOutcome.SOFT_FAILURE),
            (10, DiceOutcome.PARTIAL_SUCCESS),
            (14, DiceOutcome.PARTIAL_SUCCESS),
            (15, DiceOutcome.FULL_SUCCESS),
            (31, DiceOutcome.FULL_SUCCESS),
        ],
    )
    def test_band_edges(self, total, expected):
        outcome, is_critical = _determine_outcome(_roll(total))
        assert outcome == expected
        assert is_critical is False

    def test_natural_1_beats_a_winning_total(self):
        outcome, is_critical = _determine_outcome(_roll(21, nat1=True))
        assert outcome == DiceOutcome.CRITICAL_FAILURE
        assert is_critical is True

    def test_natural_20_beats_a_losing_total(self):
        outcome, is_critical = _determine_outcome(_roll(4, nat20=True))
        assert outcome == DiceOutcome.CRITICAL_SUCCESS
        assert is_critical is True


class TestDifficultyDraw:
    """The LLM names a level; the engine draws the number from its range (A2)."""

    @pytest.mark.parametrize(
        ("level", "low", "high"),
        [
            (DifficultyLevel.TRIVIAL, 2, 6),
            (DifficultyLevel.EASY, 0, 4),
            (DifficultyLevel.NORMAL, -2, 2),
            (DifficultyLevel.HARD, -5, -1),
            (DifficultyLevel.VERY_HARD, -8, -4),
            (DifficultyLevel.NEAR_IMPOSSIBLE, -13, -9),
        ],
    )
    def test_draw_stays_inside_the_configured_range(self, level, low, high):
        draws = {draw_difficulty_modifier(level) for _ in range(200)}
        assert draws
        assert min(draws) >= low
        assert max(draws) <= high

    def test_the_ladder_is_monotonic(self):
        with patch("app.core.dice.random.randint", side_effect=lambda a, b: (a + b) // 2):
            means = [draw_difficulty_modifier(level) for level in DifficultyLevel]
        assert means == sorted(means, reverse=True)


class TestCharacterModifierClamp:
    """A6 — whatever ADR 0010 invents for progression, the bands stay calibrated."""

    @pytest.mark.parametrize(
        ("raw", "expected"), [(-40, -5), (-5, -5), (0, 0), (11, 11), (99, 11)]
    )
    def test_clamp(self, raw, expected):
        assert clamp_character_modifier(raw) == expected


class TestResolveCheck:
    def test_total_is_die_plus_clamped_modifier_plus_draw(self):
        with (
            patch("app.core.dice.random.randint", return_value=10),
            patch("app.core.dice.draw_difficulty_modifier", return_value=-6),
        ):
            resolution = resolve_check(modifier=99, difficulty=DifficultyLevel.VERY_HARD)

        assert resolution.modifier == 11  # clamped from 99
        assert resolution.difficulty_draw == -6
        assert resolution.total == 15
        assert resolution.outcome == DiceOutcome.FULL_SUCCESS

    def test_advantage_keeps_the_better_die(self):
        with (
            patch("app.core.dice.random.randint", side_effect=[3, 17]),
            patch("app.core.dice.draw_difficulty_modifier", return_value=0),
        ):
            resolution = resolve_check(
                modifier=0, difficulty=DifficultyLevel.NORMAL, advantage=True
            )
        assert resolution.roll.rolls == [3, 17]
        assert resolution.total == 17

    def test_disadvantage_keeps_the_worse_die(self):
        with (
            patch("app.core.dice.random.randint", side_effect=[3, 17]),
            patch("app.core.dice.draw_difficulty_modifier", return_value=0),
        ):
            resolution = resolve_check(
                modifier=0, difficulty=DifficultyLevel.NORMAL, disadvantage=True
            )
        assert resolution.total == 3

    def test_advantage_and_disadvantage_cancel(self):
        """A5 — the D&D rule, and it keeps the pair from being a numeric lever."""
        with (
            patch("app.core.dice.random.randint", return_value=12),
            patch("app.core.dice.draw_difficulty_modifier", return_value=0),
        ):
            resolution = resolve_check(
                modifier=0,
                difficulty=DifficultyLevel.NORMAL,
                advantage=True,
                disadvantage=True,
            )
        assert resolution.roll.rolls == [12]


class TestVerifiedSpreads:
    """The three spreads ADR 0003 A3 declares verified, recomputed from the config.

    A natural 1 and a natural 20 are always criticals (A4), so they are counted into
    the failure and success families the ADR's own percentages group them under.
    """

    def _spread(self, modifier: int, draw: int) -> dict[str, int]:
        families = {"failure_hard": 0, "failure_soft": 0, "partial": 0, "full": 0}
        for die in range(1, 21):
            with (
                patch("app.core.dice.random.randint", return_value=die),
                patch("app.core.dice.draw_difficulty_modifier", return_value=draw),
            ):
                outcome = resolve_check(
                    modifier=modifier, difficulty=DifficultyLevel.NORMAL
                ).outcome
            if outcome in (DiceOutcome.HARD_FAILURE, DiceOutcome.CRITICAL_FAILURE):
                families["failure_hard"] += 1
            elif outcome == DiceOutcome.SOFT_FAILURE:
                families["failure_soft"] += 1
            elif outcome == DiceOutcome.PARTIAL_SUCCESS:
                families["partial"] += 1
            else:
                families["full"] += 1
        return {k: v * 5 for k, v in families.items()}  # 20 faces → percent

    def test_level_1_vs_normal(self):
        assert self._spread(modifier=2, draw=0) == {
            "failure_hard": 15,
            "failure_soft": 20,
            "partial": 25,
            "full": 40,
        }

    def test_level_1_vs_very_hard(self):
        assert self._spread(modifier=2, draw=-6) == {
            "failure_hard": 45,
            "failure_soft": 20,
            "partial": 25,
            "full": 10,
        }

    def test_level_1_vs_near_impossible_succeeds_only_on_a_natural_20(self):
        assert self._spread(modifier=2, draw=-11)["full"] == 5

    def test_endgame_vs_near_impossible(self):
        """The clamp ceiling ADR 0010 will produce, against the hardest level."""
        assert self._spread(modifier=11, draw=-11)["full"] == 30
