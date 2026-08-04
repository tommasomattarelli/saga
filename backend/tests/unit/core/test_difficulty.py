"""Campaign difficulty and the death policy it selects (ADR 0003 B8)."""

import pytest

from app.core.death import check_player_death
from app.models.campaign import Difficulty


def _char(current: int = 0) -> dict:
    return {"name": "Eron", "hp": {"current": current, "max": 40}}


class TestTheEnum:
    def test_it_offers_exactly_three_difficulties(self):
        assert {d.value for d in Difficulty} == {"easy", "medium", "hard"}


class TestEasy:
    def test_the_player_never_dies(self):
        char = _char()
        result = check_player_death(char, "easy", {})
        assert result.is_dead is False
        assert result.action == "near_death"
        assert char["hp"]["current"] == 1


class TestMedium:
    def test_fate_intervenes_while_lives_remain(self):
        result = check_player_death(_char(), "medium", {"fate_interventions_left": 3})
        assert result.is_dead is False
        assert result.action == "fate_intervention"
        assert result.fate_interventions_remaining == 2

    def test_the_cost_rises_with_each_intervention(self):
        first = check_player_death(_char(), "medium", {"fate_interventions_left": 3})
        last = check_player_death(_char(), "medium", {"fate_interventions_left": 1})
        assert first.narrative_instruction != last.narrative_instruction

    def test_death_is_final_once_they_are_spent(self):
        result = check_player_death(_char(), "medium", {"fate_interventions_left": 0})
        assert result.is_dead is True
        assert result.action == "dead"


class TestHard:
    def test_death_is_permanent_from_the_first_fall(self):
        result = check_player_death(_char(), "hard", {"fate_interventions_left": 3})
        assert result.is_dead is True
        assert result.action == "dead"


class TestAliveIsUntouched:
    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_a_standing_player_triggers_nothing(self, difficulty):
        result = check_player_death(_char(current=7), difficulty, {})
        assert result.action == "alive"
        assert result.narrative_instruction == ""


class TestTheDefaultIsNotSilentlyForgiving:
    """The bug this sprint closes: the mode was read from a key nothing ever wrote,
    so every campaign silently resolved as cronista and no player could die."""

    def test_an_unknown_difficulty_does_not_fall_back_to_immortality(self):
        result = check_player_death(_char(), "nonsense", {"fate_interventions_left": 0})
        assert result.is_dead is True
