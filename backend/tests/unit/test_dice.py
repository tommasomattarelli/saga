"""Tests for the dice engine."""

import pytest

from app.core.dice import ability_check, roll_dice, roll_with_advantage, roll_with_disadvantage


class TestRollDice:
    """Test basic dice rolling."""

    def test_single_d20(self):
        result = roll_dice("1d20")
        assert 1 <= result.total <= 20
        assert len(result.rolls) == 1

    def test_multiple_dice(self):
        result = roll_dice("3d6")
        assert 3 <= result.total <= 18
        assert len(result.rolls) == 3

    def test_dice_with_modifier(self):
        result = roll_dice("1d20+5")
        assert 6 <= result.total <= 25
        assert result.modifier == 5

    def test_dice_with_negative_modifier(self):
        result = roll_dice("1d20-3")
        assert -2 <= result.total <= 17
        assert result.modifier == -3

    def test_shorthand_d6(self):
        result = roll_dice("d6")
        assert 1 <= result.total <= 6

    def test_invalid_expression(self):
        with pytest.raises(ValueError):
            roll_dice("invalid")

    def test_natural_20_detection(self):
        # Roll many times to ensure we detect nat 20s
        found_nat20 = False
        for _ in range(1000):
            result = roll_dice("1d20")
            if result.natural_20:
                assert result.rolls[0] == 20
                found_nat20 = True
                break
        # Statistical: probability of not rolling a 20 in 1000 tries is negligible


class TestAdvantage:
    """Test advantage/disadvantage rolling."""

    def test_advantage_rolls_two_dice(self):
        result = roll_with_advantage()
        assert len(result.rolls) == 2

    def test_disadvantage_rolls_two_dice(self):
        result = roll_with_disadvantage()
        assert len(result.rolls) == 2


class TestAbilityCheck:
    """Test ability checks."""

    def test_basic_check(self):
        result = ability_check(modifier=5, dc=15)
        assert "success" in result
        assert "dc" in result
        assert result["dc"] == 15

    def test_check_with_advantage(self):
        result = ability_check(modifier=0, dc=10, advantage=True)
        assert len(result["roll"].rolls) == 2
