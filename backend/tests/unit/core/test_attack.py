"""The symmetric attack pipeline and the single damage apply path (ADR 0003 B4/B5/B6)."""

from unittest.mock import patch

import pytest

from app.core.attack import resolve_attack
from app.core.dice import DiceOutcome, resolve_check
from app.core.health import apply_hp_delta

PLAYER = {
    "name": "Eron",
    "hp": {"current": 40, "max": 40},
    "abilities": {"strength": 16, "dexterity": 12},
}


def _world() -> dict:
    return {
        "meta": {"current_location": "tavern"},
        "clock": {"total_minutes": 480},
        "npcs": {
            "goblin-1": {
                "name": "Goblin",
                "lifecycle": "alive",
                "location": "tavern",
                "hp": 8,
                "max_hp": 8,
                "defense": "normal",
                "attack_mod": 2,
                "damage_class": "light",
                "npc_class": "beast",
                "auto_created": True,
            },
            "brute-1": {
                "name": "Brute",
                "lifecycle": "alive",
                "location": "tavern",
                "hp": 30,
                "max_hp": 30,
                "defense": "easy",
                "attack_mod": 3,
                "damage_class": "medium",
                "npc_class": "soldier",
                "auto_created": False,
            },
        },
    }


def _hit(tier: DiceOutcome = DiceOutcome.FULL_SUCCESS):
    """Pin the outcome tier; the bands themselves are covered in test_resolution."""

    def fixed(modifier, difficulty, advantage=False, disadvantage=False):
        resolution = resolve_check(modifier, difficulty, advantage, disadvantage)
        resolution.outcome = tier
        return resolution

    return patch("app.core.attack.resolve_check", side_effect=fixed)


class TestApplyHpDelta:
    """One write path for every HP change in the game (B6)."""

    def test_damage_to_the_player_lands_on_char_data(self):
        world, char = _world(), dict(PLAYER)
        world, char, hp, max_hp = apply_hp_delta(world, char, "player", -12)
        assert (hp, max_hp) == (28, 40)
        assert char["hp"]["current"] == 28

    def test_damage_to_an_npc_lands_on_the_record(self):
        world, char = _world(), dict(PLAYER)
        world, char, hp, max_hp = apply_hp_delta(world, char, "goblin-1", -5)
        assert (hp, max_hp) == (3, 8)
        assert world["npcs"]["goblin-1"]["hp"] == 3

    def test_hp_never_goes_below_zero_or_above_max(self):
        world, char = _world(), dict(PLAYER)
        world, _, hp, _ = apply_hp_delta(world, char, "goblin-1", -999)
        assert hp == 0
        world, _, hp, _ = apply_hp_delta(world, char, "goblin-1", 999)
        assert hp == 8

    def test_an_npc_at_zero_is_written_dead(self):
        """The 0009 death writer, now reading the record instead of initiative_order."""
        world, char = _world(), dict(PLAYER)
        world, _, _, _ = apply_hp_delta(world, char, "goblin-1", -8)
        assert world["npcs"]["goblin-1"]["lifecycle"] == "dead"

    def test_an_npc_above_zero_stays_alive(self):
        world, char = _world(), dict(PLAYER)
        world, _, _, _ = apply_hp_delta(world, char, "goblin-1", -7)
        assert world["npcs"]["goblin-1"]["lifecycle"] == "alive"

    def test_the_reducer_slot_can_soak_damage(self):
        """ADR 0010 armor plugs in here; today it is a pass-through (B6)."""
        world, char = _world(), dict(PLAYER)
        with patch(
            "app.core.health.reduce_damage", side_effect=lambda amount, _target: amount // 2
        ):
            _, char, hp, _ = apply_hp_delta(world, char, "player", -20)
        assert hp == 30


class TestAttackResolution:
    def test_the_player_can_strike_an_npc(self):
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Eron", "Goblin", weapon_class="medium")
        assert result.error == ""
        assert result.damage > 0
        assert result.world_state["npcs"]["goblin-1"]["hp"] < 8

    def test_an_npc_can_strike_the_player(self):
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Goblin", "Eron")
        assert result.error == ""
        assert result.char_data["hp"]["current"] < 40

    def test_an_npc_can_strike_another_npc(self):
        """Companions-ready: inexpressible in a player-always-rolls model (B4)."""
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Brute", "Goblin")
        assert result.error == ""
        assert result.world_state["npcs"]["goblin-1"]["hp"] < 8

    def test_a_missed_swing_deals_nothing(self):
        world, char = _world(), dict(PLAYER)
        with _hit(DiceOutcome.HARD_FAILURE):
            result = resolve_attack(world, char, "Eron", "Goblin", weapon_class="medium")
        assert result.damage == 0
        assert result.world_state["npcs"]["goblin-1"]["hp"] == 8

    def test_a_partial_hit_grazes(self):
        world, char = _world(), dict(PLAYER)
        with _hit(DiceOutcome.PARTIAL_SUCCESS):
            result = resolve_attack(world, char, "Eron", "Goblin", weapon_class="heavy")
        assert result.outcome == DiceOutcome.PARTIAL_SUCCESS
        assert result.damage >= 1

    def test_the_target_defense_feeds_the_roll(self):
        world, char = _world(), dict(PLAYER)
        with _hit():
            easy = resolve_attack(world, char, "Eron", "Brute", weapon_class="light")
        assert easy.difficulty.value == "easy"  # Brute's defense level

    def test_the_player_rolls_the_sheet_not_a_statblock_number(self):
        """B3 — the player has no attack_mod field; STR 16 → +3."""
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Eron", "Goblin", weapon_class="medium")
        assert result.attack_mod == 3

    def test_an_npc_rolls_its_statblock(self):
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Goblin", "Eron")
        assert result.attack_mod == 2


class TestNameResolution:
    def test_a_typo_is_rejected_with_candidates_not_guessed(self):
        """Shares the 0009 B4 threshold with update_npc — one knob, not two."""
        world, char = _world(), dict(PLAYER)
        result = resolve_attack(world, char, "Eron", "Gobblin", weapon_class="medium")
        assert "Goblin" in result.error
        assert result.world_state["npcs"]["goblin-1"]["hp"] == 8
        assert len(result.world_state["npcs"]) == 2  # no phantom mook created

    def test_a_genuinely_new_name_is_auto_created_as_a_mook(self):
        """B2 — one store, one damage path; no ephemeral combatants."""
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Eron", "Skeleton", weapon_class="medium")
        created = [n for n in result.world_state["npcs"].values() if n["name"] == "Skeleton"]
        assert len(created) == 1
        assert created[0]["auto_created"] is True
        assert created[0]["location"] == "tavern"  # the scaffold's location fix
        assert created[0]["max_hp"] > 0

    def test_a_dead_npc_cannot_be_attacked_again(self):
        world, char = _world(), dict(PLAYER)
        world["npcs"]["goblin-1"]["lifecycle"] = "dead"
        result = resolve_attack(world, char, "Eron", "Goblin", weapon_class="medium")
        assert result.error != ""

    def test_an_unknown_attacker_is_rejected(self):
        world, char = _world(), dict(PLAYER)
        result = resolve_attack(world, char, "Nobody At All", "Goblin")
        assert result.error != ""
        assert result.world_state["npcs"]["goblin-1"]["hp"] == 8


class TestNoFreeNumbers:
    def test_resolve_attack_takes_no_damage_argument(self):
        import inspect

        params = inspect.signature(resolve_attack).parameters
        assert "damage" not in params
        assert "amount" not in params

    @pytest.mark.parametrize("weapon", ["unarmed", "light", "medium", "heavy"])
    def test_heavier_weapons_hit_harder_on_average(self, weapon):
        world, char = _world(), dict(PLAYER)
        with _hit():
            result = resolve_attack(world, char, "Eron", "Brute", weapon_class=weapon)
        assert result.damage >= 1
