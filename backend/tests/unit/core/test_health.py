"""Hazard and heal percentage draws, and the DM heal budget (ADR 0003 B7/B7b)."""

from unittest.mock import patch

import pytest

from app.core.dice import DiceOutcome
from app.core.health import (
    HazardClass,
    HealClass,
    consume_dm_heal,
    dm_heal_budget_left,
    draw_hazard_damage,
    draw_heal_amount,
)


def _world(total_minutes: int = 480, used: int = 0, day: int = 1) -> dict:
    return {
        "clock": {"total_minutes": total_minutes},
        "dm_heals": {"day": day, "used": used},
    }


class TestHazardDamage:
    """Percentages of max HP, not dice — a trap must still bite at level 20 (B7)."""

    @pytest.mark.parametrize(
        ("hazard", "low", "high"),
        [
            (HazardClass.MINOR, 0.05, 0.15),
            (HazardClass.SERIOUS, 0.20, 0.35),
            (HazardClass.DEADLY, 0.45, 0.70),
        ],
    )
    def test_draw_stays_inside_the_configured_band(self, hazard, low, high):
        damages = {
            draw_hazard_damage(hazard, DiceOutcome.HARD_FAILURE, max_hp=100) for _ in range(200)
        }
        assert min(damages) >= round(low * 100)
        assert max(damages) <= round(high * 100)

    def test_full_success_dodges_outright(self):
        assert draw_hazard_damage(HazardClass.DEADLY, DiceOutcome.FULL_SUCCESS, max_hp=100) == 0

    def test_critical_success_dodges_outright(self):
        assert (
            draw_hazard_damage(HazardClass.DEADLY, DiceOutcome.CRITICAL_SUCCESS, max_hp=100) == 0
        )

    def test_the_tier_doses_the_same_draw(self):
        with patch("app.core.health.random.uniform", return_value=0.50):
            partial = draw_hazard_damage(HazardClass.DEADLY, DiceOutcome.PARTIAL_SUCCESS, 100)
            failure = draw_hazard_damage(HazardClass.DEADLY, DiceOutcome.HARD_FAILURE, 100)
            fumble = draw_hazard_damage(HazardClass.DEADLY, DiceOutcome.CRITICAL_FAILURE, 100)
        assert (partial, failure, fumble) == (25, 50, 75)

    def test_a_damaging_tier_never_rounds_down_to_nothing(self):
        with patch("app.core.health.random.uniform", return_value=0.05):
            assert (
                draw_hazard_damage(HazardClass.MINOR, DiceOutcome.PARTIAL_SUCCESS, max_hp=4) == 1
            )


class TestHealAmount:
    @pytest.mark.parametrize(
        ("heal", "low", "high"),
        [
            (HealClass.MINOR, 0.10, 0.20),
            (HealClass.STRONG, 0.30, 0.50),
            (HealClass.FULL, 1.00, 1.00),
        ],
    )
    def test_draw_stays_inside_the_configured_band(self, heal, low, high):
        amounts = {draw_heal_amount(heal, max_hp=100) for _ in range(200)}
        assert min(amounts) >= round(low * 100)
        assert max(amounts) <= round(high * 100)

    def test_full_restores_the_whole_pool(self):
        assert draw_heal_amount(HealClass.FULL, max_hp=37) == 37

    def test_a_heal_is_never_nothing(self):
        assert draw_heal_amount(HealClass.MINOR, max_hp=3) >= 1


class TestDmHealBudget:
    """No resource economy until 0010/0012, so the cap is the backstop (B7b)."""

    def test_budget_starts_at_the_configured_cap(self):
        assert dm_heal_budget_left(_world()) == 3

    def test_consuming_spends_the_budget(self):
        world = _world()
        for expected in (2, 1, 0):
            world = consume_dm_heal(world)
            assert dm_heal_budget_left(world) == expected

    def test_a_jailbroken_heal_spam_hits_the_wall(self):
        world = _world(used=3)
        assert dm_heal_budget_left(world) == 0

    def test_the_budget_resets_on_a_new_game_day(self):
        spent = _world(used=3, day=1)
        next_day = {**spent, "clock": {"total_minutes": 480 + 24 * 60}}
        assert dm_heal_budget_left(next_day) == 3

    def test_consuming_on_a_new_day_rebases_the_counter(self):
        world = consume_dm_heal({**_world(used=3, day=1), "clock": {"total_minutes": 24 * 60}})
        assert world["dm_heals"] == {"day": 2, "used": 1}
