"""Tests for 6-level dice outcome system."""

from unittest.mock import patch

from app.core.dice import (
    DiceOutcome,
    DiceResult,
    _determine_outcome,
    ability_check,
)


class TestDetermineOutcome:
    def _make_result(self, total: int, nat1: bool = False, nat20: bool = False) -> DiceResult:
        return DiceResult(
            expression="1d20",
            rolls=[total],
            modifier=0,
            total=total,
            natural_1=nat1,
            natural_20=nat20,
        )

    def test_natural_1_always_critical_failure(self):
        result = self._make_result(total=15, nat1=True)
        outcome, is_crit = _determine_outcome(result, dc=10)
        assert outcome == DiceOutcome.CRITICAL_FAILURE
        assert is_crit is True

    def test_natural_20_always_critical_success(self):
        result = self._make_result(total=20, nat20=True)
        outcome, is_crit = _determine_outcome(result, dc=25)
        assert outcome == DiceOutcome.CRITICAL_SUCCESS
        assert is_crit is True

    def test_hard_failure(self):
        # Total 5 vs DC 15 → diff = -10 (≤ -5)
        result = self._make_result(total=5)
        outcome, is_crit = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.HARD_FAILURE
        assert is_crit is False

    def test_soft_failure(self):
        # Total 12 vs DC 15 → diff = -3 (between -4 and -1)
        result = self._make_result(total=12)
        outcome, is_crit = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.SOFT_FAILURE
        assert is_crit is False

    def test_soft_failure_boundary(self):
        # Total 11 vs DC 15 → diff = -4
        result = self._make_result(total=11)
        outcome, _ = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.SOFT_FAILURE

    def test_hard_failure_boundary(self):
        # Total 10 vs DC 15 → diff = -5
        result = self._make_result(total=10)
        outcome, _ = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.HARD_FAILURE

    def test_partial_success(self):
        # Total 15 vs DC 15 → diff = 0
        result = self._make_result(total=15)
        outcome, is_crit = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.PARTIAL_SUCCESS
        assert is_crit is False

    def test_partial_success_upper_bound(self):
        # Total 18 vs DC 15 → diff = 3
        result = self._make_result(total=18)
        outcome, _ = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.PARTIAL_SUCCESS

    def test_full_success(self):
        # Total 19 vs DC 15 → diff = 4
        result = self._make_result(total=19)
        outcome, is_crit = _determine_outcome(result, dc=15)
        assert outcome == DiceOutcome.FULL_SUCCESS
        assert is_crit is False

    def test_full_success_large_margin(self):
        # Total 25 vs DC 10 → diff = 15
        result = self._make_result(total=25)
        outcome, _ = _determine_outcome(result, dc=10)
        assert outcome == DiceOutcome.FULL_SUCCESS


class TestAbilityCheckOutcome:
    @patch("app.core.dice.random.randint", return_value=1)
    def test_natural_1(self, mock_randint):
        result = ability_check(modifier=10, dc=5)
        assert result["outcome"] == "critical_failure"
        assert result["is_critical"] is True
        assert result["critical_failure"] is True

    @patch("app.core.dice.random.randint", return_value=20)
    def test_natural_20(self, mock_randint):
        result = ability_check(modifier=0, dc=25)
        assert result["outcome"] == "critical_success"
        assert result["is_critical"] is True
        assert result["critical_success"] is True

    @patch("app.core.dice.random.randint", return_value=10)
    def test_partial_success_from_check(self, mock_randint):
        result = ability_check(modifier=3, dc=13)
        # total = 10 + 3 = 13, dc = 13, diff = 0 → partial_success
        assert result["outcome"] == "partial_success"
        assert result["success"] is True

    @patch("app.core.dice.random.randint", return_value=5)
    def test_hard_failure_from_check(self, mock_randint):
        result = ability_check(modifier=0, dc=15)
        # total = 5, dc = 15, diff = -10 → hard_failure
        assert result["outcome"] == "hard_failure"
        assert result["success"] is False


class TestAdvantageOutcome:
    def test_advantage_returns_outcome(self):
        result = ability_check(modifier=0, dc=10, advantage=True)
        assert "outcome" in result
        assert result["outcome"] in [o.value for o in DiceOutcome]

    def test_disadvantage_returns_outcome(self):
        result = ability_check(modifier=0, dc=10, disadvantage=True)
        assert "outcome" in result
        assert "is_critical" in result
