"""Tests for the death system — all 3 death modes."""

import pytest
from app.core.death import DeathCheckResult, check_player_death


def _char(current: int, max_hp: int = 10) -> dict:
    return {"name": "Hero", "hp": {"current": current, "max": max_hp}}


class TestAlive:
    def test_alive_returns_alive_action(self):
        result = check_player_death(_char(5), "ironman", {})
        assert result.action == "alive"
        assert result.is_dead is False

    def test_alive_at_1_hp(self):
        result = check_player_death(_char(1), "cronista", {})
        assert result.action == "alive"

    def test_alive_does_not_modify_hp(self):
        char = _char(3)
        check_player_death(char, "ironman", {})
        assert char["hp"]["current"] == 3


class TestCronista:
    def test_near_death_at_zero_hp(self):
        char = _char(0)
        result = check_player_death(char, "cronista", {})
        assert result.action == "near_death"
        assert result.is_dead is False

    def test_hp_reset_to_1(self):
        char = _char(0)
        check_player_death(char, "cronista", {})
        assert char["hp"]["current"] == 1

    def test_narrative_instruction_non_empty(self):
        result = check_player_death(_char(0), "cronista", {})
        assert len(result.narrative_instruction) > 0

    def test_negative_hp_also_triggers_near_death(self):
        char = _char(-5)
        result = check_player_death(char, "cronista", {})
        assert result.action == "near_death"
        assert char["hp"]["current"] == 1


class TestDestino:
    def test_fate_intervention_when_lives_remain(self):
        char = _char(0)
        result = check_player_death(char, "destino", {"destino_lives": 3})
        assert result.action == "fate_intervention"
        assert result.is_dead is False
        assert result.destino_lives_remaining == 2

    def test_lives_decrement(self):
        result = check_player_death(_char(0), "destino", {"destino_lives": 2})
        assert result.destino_lives_remaining == 1

    def test_last_life_used(self):
        result = check_player_death(_char(0), "destino", {"destino_lives": 1})
        assert result.action == "fate_intervention"
        assert result.destino_lives_remaining == 0

    def test_no_lives_remaining_is_dead(self):
        result = check_player_death(_char(0), "destino", {"destino_lives": 0})
        assert result.is_dead is True
        assert result.action == "dead"

    def test_cost_hint_varies_by_intervention_number(self):
        r1 = check_player_death(_char(0), "destino", {"destino_lives": 3})
        r2 = check_player_death(_char(0), "destino", {"destino_lives": 2})
        r3 = check_player_death(_char(0), "destino", {"destino_lives": 1})
        assert "Minor" in r1.narrative_instruction
        assert "Major" in r2.narrative_instruction
        assert "Severe" in r3.narrative_instruction

    def test_missing_destino_lives_defaults_to_3(self):
        result = check_player_death(_char(0), "destino", {})
        assert result.action == "fate_intervention"
        assert result.destino_lives_remaining == 2


class TestIronman:
    def test_permanent_death_at_zero_hp(self):
        result = check_player_death(_char(0), "ironman", {})
        assert result.is_dead is True
        assert result.action == "dead"

    def test_death_mode_field(self):
        result = check_player_death(_char(0), "ironman", {})
        assert result.death_mode == "ironman"

    def test_narrative_instruction_non_empty(self):
        result = check_player_death(_char(0), "ironman", {})
        assert len(result.narrative_instruction) > 0
